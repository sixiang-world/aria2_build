#!/usr/bin/env python3
"""Exercise HTTP content decoding using a loopback server."""

import argparse
import gzip
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import subprocess
import tempfile
from threading import Thread
import zlib


PAYLOAD = b"aria2 HTTP content encoding test\n" * 4096
encoder = zlib.compressobj(wbits=-zlib.MAX_WBITS)
RAW = encoder.compress(PAYLOAD) + encoder.flush()
WRAPPED = zlib.compress(PAYLOAD)
RESPONSES = {
    "/gzip": ("gzip", gzip.compress(PAYLOAD), False),
    "/zlib": ("deflate", WRAPPED, False),
    "/raw": ("deflate", RAW, False),
    "/raw-chunked": ("deflate", RAW, True),
    "/zlib-chunked": ("deflate", WRAPPED, True),
    "/invalid-checksum": ("deflate", WRAPPED[:-1] + bytes([WRAPPED[-1] ^ 1]), True),
    "/raw-as-gzip": ("gzip", RAW, False),
}


class EncodingHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *_):
        pass

    def do_GET(self):
        coding, body, chunked = RESPONSES[self.path]
        self.send_response(200)
        self.send_header("Content-Encoding", coding)
        self.send_header("Connection", "close")
        if chunked:
            self.send_header("Transfer-Encoding", "chunked")
        else:
            self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            if chunked:
                # A separate chunk splits the framing bytes even if TCP coalesces them.
                self.wfile.write(b"1\r\n" + body[:1] + b"\r\n")
                self.wfile.write(
                    f"{len(body) - 1:x}\r\n".encode() + body[1:] + b"\r\n0\r\n\r\n"
                )
            else:
                self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("binary", type=Path)
    parser.add_argument("--runner", help="Executable prefix, such as qemu-aarch64 or wine")
    parser.add_argument("--baseline", action="store_true", help="Expect raw deflate to fail")
    args = parser.parse_args()

    command = [str(args.binary.resolve())]
    if args.runner:
        command.insert(0, args.runner)

    with ThreadingHTTPServer(("127.0.0.1", 0), EncodingHandler) as server:
        serving = Thread(target=server.serve_forever, daemon=True)
        serving.start()
        try:
            with tempfile.TemporaryDirectory() as directory:
                for route in RESPONSES:
                    name = route[1:]
                    success = name not in {"invalid-checksum", "raw-as-gzip"}
                    if args.baseline and name in {"raw", "raw-chunked"}:
                        success = False
                    result = subprocess.run(
                        [
                            *command, "--no-conf", "--all-proxy=",
                            "--http-accept-gzip=true", "--file-allocation=none",
                            "--max-tries=1", "--split=1", "--summary-interval=0",
                            "--timeout=5", "--connect-timeout=5", f"--out={name}",
                            f"http://127.0.0.1:{server.server_port}{route}",
                        ],
                        cwd=directory, capture_output=True, text=True, timeout=20,
                    )
                    if (result.returncode == 0) != success:
                        raise SystemExit(
                            f"{name}: unexpected exit {result.returncode}\n"
                            f"{result.stdout}{result.stderr}"
                        )
                    if success and (Path(directory) / name).read_bytes() != PAYLOAD:
                        raise SystemExit(f"{name}: decoded bytes differ from the fixture")
                    print(f"PASS {name}")
        finally:
            server.shutdown()
            serving.join()


if __name__ == "__main__":
    main()
