#!/usr/bin/env python3
"""Verify HTTPS certificate verification using a local loopback TLS server."""

import argparse
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import shutil
import ssl
import subprocess
import tempfile
from threading import Thread


PAYLOAD = b"aria2 loopback TLS verification payload\n" * 1024
DIGEST = hashlib.sha256(PAYLOAD).digest()


class TlsHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *_):
        pass

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Length", str(len(PAYLOAD)))
        self.send_header("Connection", "close")
        self.end_headers()
        try:
            self.wfile.write(PAYLOAD)
        except (BrokenPipeError, ConnectionResetError):
            pass


def generate_self_signed_cert(directory):
    cert = Path(directory) / "server.crt"
    key = Path(directory) / "server.key"
    cfg = Path(directory) / "openssl.cnf"
    cfg.write_text(
        "[req]\n"
        "distinguished_name=dn\n"
        "x509_extensions=v3_req\n"
        "prompt=no\n"
        "[dn]\n"
        "CN=127.0.0.1\n"
        "[v3_req]\n"
        "basicConstraints=critical,CA:TRUE\n"
        "keyUsage=critical,digitalSignature,keyEncipherment,keyCertSign\n"
        "extendedKeyUsage=serverAuth\n"
        "subjectAltName=IP:127.0.0.1,DNS:localhost\n",
        encoding="utf-8",
    )
    subprocess.run(
        [
            "openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
            "-keyout", str(key), "-out", str(cert), "-days", "2",
            "-config", str(cfg),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return cert, key


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("binary", type=Path)
    parser.add_argument("--runner", help="Optional emulator executable such as qemu-aarch64 or wine")
    parser.add_argument("--baseline", action="store_true", help="Unused compatibility flag")
    args = parser.parse_args()

    if shutil.which("openssl") is None:
        print("SKIP loopback TLS test (openssl CLI unavailable)")
        return

    command = ([args.runner] if args.runner else []) + [str(args.binary.resolve())]
    with tempfile.TemporaryDirectory(prefix="aria2-tls-") as directory:
        cert, key = generate_self_signed_cert(directory)
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(certfile=str(cert), keyfile=str(key))
        with ThreadingHTTPServer(("127.0.0.1", 0), TlsHandler) as server:
            server.socket = ctx.wrap_socket(server.socket, server_side=True)
            worker = Thread(target=server.serve_forever, daemon=True)
            worker.start()
            try:
                url = f"https://127.0.0.1:{server.server_port}/payload.bin"
                base_args = [
                    *command, "--no-conf", "--all-proxy=", "--no-proxy=127.0.0.1",
                    "--file-allocation=none", "--split=1", "--max-connection-per-server=1",
                    "--max-tries=1", "--timeout=10", "--connect-timeout=5",
                    "--summary-interval=0", "--console-log-level=warn",
                ]

                # 1. Valid trusted CA certificate must succeed with exact SHA-256.
                ok = subprocess.run(
                    [*base_args, "--check-certificate=true", "--ca-certificate=server.crt",
                     "--out=trusted.bin", url],
                    cwd=directory, capture_output=True, text=True, timeout=25,
                )
                if ok.returncode != 0:
                    raise SystemExit(
                        f"HTTPS trusted CA download failed (exit {ok.returncode}):\n{ok.stdout}{ok.stderr}"
                    )
                out_file = Path(directory) / "trusted.bin"
                if not out_file.is_file() or hashlib.sha256(out_file.read_bytes()).digest() != DIGEST:
                    raise SystemExit("HTTPS trusted CA payload SHA-256 mismatch")
                print("PASS HTTPS loopback trusted CA verification")

                # 2. Untrusted self-signed cert must be rejected when check-certificate=true.
                bad = subprocess.run(
                    [*base_args, "--check-certificate=true", "--out=untrusted.bin", url],
                    cwd=directory, capture_output=True, text=True, timeout=25,
                )
                if bad.returncode == 0:
                    raise SystemExit("HTTPS loopback unexpectedly accepted an untrusted self-signed cert")
                print("PASS HTTPS loopback rejects untrusted certificate")
            finally:
                server.shutdown()
                worker.join()


if __name__ == "__main__":
    main()
