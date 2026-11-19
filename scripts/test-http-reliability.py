#!/usr/bin/env python3
"""Check HTTP range handling, recovery, and retry policy against loopback."""

import argparse
from dataclasses import dataclass, field
from email.utils import formatdate
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import re
import subprocess
import tempfile
from threading import Condition, Thread
import time


MIB = 1024 * 1024
PAYLOAD = hashlib.shake_256(b"aria2 HTTP reliability fixture").digest(10 * MIB)
RANGE = re.compile(r"bytes=(\d+)-(\d*)")


@dataclass
class Transfer:
    payload: bytes = PAYLOAD
    status: int = 200
    failures: int = 1
    retry_after: str = ""
    retry_after_date: bool = False
    drop_first: bool = False
    slow_first: bool = False
    chunked_range: str = ""
    content_disposition: str = ""
    concurrent: int = 1
    condition: Condition = field(default_factory=Condition)
    requests: list = field(default_factory=list)
    active: int = 0
    peak: int = 0


class Server(ThreadingHTTPServer):
    request_queue_size = 64


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *_):
        pass

    def do_HEAD(self):
        transfer = self.server.transfer
        with transfer.condition:
            transfer.requests.append(("HEAD", self.headers.get("Range"), time.monotonic()))
        self.send_response(200)
        self.send_header("Content-Length", str(len(transfer.payload)))
        self.send_header("Accept-Ranges", "bytes")
        self.end_headers()

    def do_GET(self):
        transfer = self.server.transfer
        payload = transfer.payload
        range_header = self.headers.get("Range")
        match = RANGE.fullmatch(range_header or "")
        start = 0
        end = len(payload) - 1
        if match:
            start = int(match[1])
            if match[2]:
                end = min(end, int(match[2]))
        if (range_header and not match) or not 0 <= start <= end:
            self.send_error(416)
            return

        with transfer.condition:
            transfer.requests.append(("GET", range_header, time.monotonic()))
            attempt = len(transfer.requests)
            transfer.active += 1
            transfer.peak = max(transfer.peak, transfer.active)
            transfer.condition.notify_all()

        try:
            if transfer.status != 200 and attempt <= transfer.failures:
                self.send_response(transfer.status)
                self.send_header("Content-Length", "0")
                retry_after = transfer.retry_after
                if transfer.retry_after_date:
                    retry_after = formatdate(time.time() + 3, usegmt=True)
                if retry_after:
                    self.send_header("Retry-After", retry_after)
                self.send_header("Connection", "close")
                self.end_headers()
                return

            chunked_range = transfer.chunked_range if match else ""
            self.send_response(206 if match and chunked_range != "ignored" else 200)
            body_start = start
            if match and chunked_range not in ("missing", "ignored"):
                body_start = start + 1 if chunked_range == "mismatch" else start
                self.send_header("Content-Range", f"bytes {body_start}-{end}/{len(payload)}")
            if chunked_range == "ignored":
                body_start = 0
            self.send_header("Accept-Ranges", "bytes")
            if transfer.content_disposition:
                self.send_header("Content-Disposition", transfer.content_disposition)
            if chunked_range:
                self.send_header("Transfer-Encoding", "chunked")
            else:
                self.send_header("Content-Length", str(end - start + 1))
            self.send_header("Connection", "close")
            self.end_headers()

            with transfer.condition:
                # Send headers first so aria2 can learn the file size and start its splits.
                transfer.condition.wait_for(lambda: transfer.peak >= transfer.concurrent, timeout=12)

            body = memoryview(payload)[body_start : end + 1]
            if chunked_range == "short-body":
                self.wfile.write(b"0\r\n\r\n")
            elif chunked_range == "oversized-chunk":
                self.wfile.write(f"{len(body) + 1:x}\r\n".encode())
            elif chunked_range == "overlong-body":
                body = bytes(body) + b"!"
                self.wfile.write(f"{len(body):x}\r\n".encode() + body + b"\r\n0\r\n\r\n")
            elif chunked_range:
                for offset in range(0, len(body), 64 * 1024):
                    chunk = body[offset : offset + 64 * 1024]
                    self.wfile.write(f"{len(chunk):x}\r\n".encode())
                    self.wfile.write(chunk)
                    self.wfile.write(b"\r\n")
                self.wfile.write(b"0\r\n\r\n")
            elif attempt == 1 and transfer.drop_first:
                self.wfile.write(body[: MIB + 16 * 1024])
            elif attempt == 1 and transfer.slow_first:
                # Keep the socket active at 32 KiB/s through aria2's 10-second grace period.
                for offset in range(0, len(body), 8192):
                    self.wfile.write(body[offset : offset + 8192])
                    with transfer.condition:
                        if transfer.condition.wait_for(lambda: len(transfer.requests) > 1, timeout=0.25):
                            break
            else:
                self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            # A client can stop reading when its assigned range completes or when it retries.
            pass
        finally:
            with transfer.condition:
                transfer.active -= 1


def check_transfer(server, command, name, transfer, *, options=(), returncode=0,
                   attempts=None, min_delay=0, max_delay=None, resume_offset=0,
                   continued=False, request_sequence=()):
    server.transfer = transfer
    with tempfile.TemporaryDirectory() as directory:
        target = Path(directory) / "file.bin"
        if resume_offset:
            target.write_bytes(transfer.payload[:resume_offset])
        result = subprocess.run(
            [
                *command, "--no-conf", "--all-proxy=", "--no-proxy=127.0.0.1",
                "--file-allocation=none", "--split=1", "--max-connection-per-server=1",
                "--enable-http-keep-alive=false", "--timeout=15", "--connect-timeout=8",
                "--max-tries=2", "--retry-wait=0", "--console-log-level=warn",
                "--summary-interval=0", "--enable-color=false", "--out=file.bin", *options,
                f"http://127.0.0.1:{server.server_port}/file.bin",
            ],
            cwd=directory, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, errors="replace", timeout=55,
        )
        requests = [(header, seen) for method, header, seen in transfer.requests if method == "GET"]
        starts = [int(RANGE.fullmatch(header)[1]) if header else None for header, _ in requests]
        if request_sequence:
            sequence = tuple((method, header) for method, header, _ in transfer.requests)
            if sequence != request_sequence:
                raise AssertionError(f"{name}: expected {request_sequence}, received {sequence}")
        if result.returncode != returncode:
            raise AssertionError(f"{name}: expected exit {returncode}, got {result.returncode}; "
                                 f"request offsets={starts}\n{result.stdout}")
        if returncode == 0:
            expected_hash = hashlib.sha256(transfer.payload).digest()
            if not target.is_file() or hashlib.sha256(target.read_bytes()).digest() != expected_hash:
                raise AssertionError(f"{name}: downloaded file differs from SHA-256 fixture")
        elif resume_offset and target.read_bytes() != transfer.payload[:resume_offset]:
            raise AssertionError(f"{name}: rejected response changed the partial file")

    if attempts is not None and len(starts) != attempts:
        raise AssertionError(f"{name}: expected {attempts} requests, got offsets {starts}")
    if min_delay or max_delay is not None:
        delay = requests[1][1] - requests[0][1]
        if delay < min_delay:
            raise AssertionError(f"{name}: retry after {delay:.2f}s; expected at least {min_delay:.2f}s")
        if max_delay is not None and delay > max_delay:
            raise AssertionError(f"{name}: retry after {delay:.2f}s; expected at most {max_delay:.2f}s")
    if resume_offset and resume_offset not in starts:
        raise AssertionError(f"{name}: requested offsets {starts}, expected {resume_offset}")
    if continued and not any(start for start in starts[1:]):
        raise AssertionError(f"{name}: no nonzero range after the interrupted request; offsets={starts}")
    if transfer.concurrent > 1:
        nonzero_ranges = {start for start in starts if start}
        if transfer.peak < transfer.concurrent or len(nonzero_ranges) < transfer.concurrent - 1:
            raise AssertionError(f"{name}: only {transfer.peak} simultaneous requests and "
                                 f"{len(nonzero_ranges)} nonzero ranges; expected {transfer.concurrent} splits")

    print(f"PASS {name}", flush=True)


def check_retry_policy(server, command):
    for status, suffix in [(400, "400"), (403, "403"), (406, "406"), (418, "unknown")]:
        check_transfer(server, command, f"HTTP {status} rejected by default", Transfer(status=status),
                       options=("--retry-wait=1",), returncode=22, attempts=1)
        check_transfer(server, command, f"HTTP {status} opt-in retry", Transfer(status=status),
                       options=("--retry-wait=1", f"--retry-on-{suffix}=true"),
                       attempts=2, min_delay=0.9)

    check_transfer(server, command, "known HTTP 403 honors dedicated switch", Transfer(status=403),
                   options=("--retry-wait=1", "--retry-on-unknown=true", "--retry-on-403=false"),
                   returncode=22, attempts=1)
    check_transfer(server, command, "HTTP 429 honors Retry-After", Transfer(status=429, retry_after="2"),
                   options=("--retry-wait=1",), attempts=2, min_delay=1.9)
    check_transfer(server, command, "HTTP 503 honors Retry-After HTTP-date",
                   Transfer(status=503, retry_after_date=True), options=("--retry-wait=1",),
                   attempts=2, min_delay=1.9)
    check_transfer(server, command, "HTTP 503 malformed Retry-After uses configured wait",
                   Transfer(status=503, retry_after="8 garbage"), options=("--retry-wait=1",),
                   attempts=2, min_delay=0.9, max_delay=5)
    check_transfer(server, command, "HTTP 429 retry remains disabled with zero wait",
                   Transfer(status=429, retry_after="2"), returncode=29, attempts=1)
    check_transfer(server, command, "HTTP 403 retry remains disabled with zero wait",
                   Transfer(status=403), options=("--retry-on-403=true",), returncode=22, attempts=1)
    check_transfer(server, command, "HTTP 403 honors attempt limit", Transfer(status=403, failures=3),
                   options=("--retry-wait=1", "--retry-on-403=true"), returncode=22, attempts=2,
                   min_delay=0.9)
    check_transfer(server, command, "HTTP 503 honors attempt limit", Transfer(status=503, failures=3),
                   options=("--retry-wait=1",), returncode=29, attempts=2, min_delay=0.9)



def check_content_disposition_trailing_semicolon(server, command):
    server.transfer = Transfer(
        payload=b"trailing semicolon payload",
        content_disposition='attachment; filename="trail-test.bin";',
    )
    with tempfile.TemporaryDirectory() as directory:
        result = subprocess.run(
            [
                *command, "--no-conf", "--all-proxy=", "--no-proxy=127.0.0.1",
                "--file-allocation=none", "--split=1", "--max-connection-per-server=1",
                "--max-tries=1", "--timeout=10", "--connect-timeout=5",
                "--summary-interval=0", "--console-log-level=warn",
                "--content-disposition=true",
                f"http://127.0.0.1:{server.server_port}/download",
            ],
            cwd=directory, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, errors="replace", timeout=25,
        )
        expected = Path(directory) / "trail-test.bin"
        if result.returncode != 0 or not expected.is_file() or expected.read_bytes() != b"trailing semicolon payload":
            raise AssertionError(
                f"Content-Disposition trailing semicolon failed (exit {result.returncode}, "
                f"files={[p.name for p in Path(directory).iterdir()]}):\n{result.stdout}"
            )
    print("PASS Content-Disposition trailing semicolon filename", flush=True)


def check_nul_prefixed_input_file(server, command):
    server.transfer = Transfer(payload=b"nul-prefixed input list ok")
    with tempfile.TemporaryDirectory() as directory:
        uri_file = Path(directory) / "urls.txt"
        uri_file.write_bytes(
            b"\x00\n" + f"http://127.0.0.1:{server.server_port}/nul.bin\n".encode()
        )
        result = subprocess.run(
            [
                *command, "--no-conf", "--all-proxy=", "--no-proxy=127.0.0.1",
                "--file-allocation=none", "--split=1", "--max-connection-per-server=1",
                "--max-tries=1", "--timeout=10", "--connect-timeout=5",
                "--summary-interval=0", "--console-log-level=warn",
                "-i", "urls.txt",
            ],
            cwd=directory, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, errors="replace", timeout=25,
        )
        expected = Path(directory) / "nul.bin"
        if result.returncode != 0 or not expected.is_file() or expected.read_bytes() != b"nul-prefixed input list ok":
            raise AssertionError(
                f"NUL-prefixed input file failed (exit {result.returncode}):\n{result.stdout}"
            )
    print("PASS NUL-prefixed input file (CVE-2026-75421 regression)", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("binary", type=Path)
    parser.add_argument("--runner", help="Executable prefix, such as qemu-aarch64 or wine")
    parser.add_argument("--patch-mode", choices=("patched", "vanilla"), default="patched")
    args = parser.parse_args()
    command = [str(args.binary.resolve())]
    if args.runner:
        command.insert(0, args.runner)

    patched = args.patch_mode == "patched"
    with Server(("127.0.0.1", 0), Handler) as server:
        serving = Thread(target=server.serve_forever, daemon=True)
        serving.start()
        try:
            check_transfer(server, command, "HTTP download and SHA-256", Transfer(), attempts=1)
            splits = 20 if patched else 4
            split_size = "64K" if patched else "1M"
            check_transfer(server, command, f"{splits} simultaneous split requests", Transfer(concurrent=splits),
                           options=(f"--split={splits}", f"--max-connection-per-server={splits}",
                                    f"--min-split-size={split_size}", f"--piece-length={split_size}"))
            check_transfer(server, command, "resume from a partial local file", Transfer(),
                           options=() if patched else ("--continue=true",), resume_offset=MIB)
            check_transfer(server, command, "recover a truncated response", Transfer(drop_first=True),
                           attempts=2, continued=True)
            if patched:
                check_transfer(server, command, "resume with a matching chunked HTTP 206",
                               Transfer(chunked_range="valid"), resume_offset=MIB)
                for variant in ("missing", "mismatch", "ignored"):
                    check_transfer(server, command, f"reject chunked range response ({variant})",
                                   Transfer(chunked_range=variant), resume_offset=MIB, returncode=8)
                for variant in ("short-body", "oversized-chunk"):
                    check_transfer(server, command, f"reject mismatched chunked range body ({variant})",
                                   Transfer(chunked_range=variant), resume_offset=MIB, returncode=8)
                head_options = ("--use-head=true", "--enable-http-pipelining=true",
                                "--enable-http-keep-alive=true")
                head_range = (("HEAD", None), ("GET", "bytes=0-0"))
                check_transfer(server, command, "accept pipelined one-byte chunked range",
                               Transfer(payload=b"x", chunked_range="valid"), options=head_options,
                               request_sequence=head_range)
                check_transfer(server, command, "reject excess data in pipelined one-byte range",
                               Transfer(payload=b"x", chunked_range="overlong-body"),
                               options=head_options, returncode=8, request_sequence=head_range)
                check_transfer(server, command, "retry a slow transfer", Transfer(slow_first=True),
                               options=("--lowest-speed-limit=256K",), attempts=2, continued=True)
                check_retry_policy(server, command)
                check_content_disposition_trailing_semicolon(server, command)
                check_nul_prefixed_input_file(server, command)
        finally:
            server.shutdown()
            serving.join()


if __name__ == "__main__":
    main()
