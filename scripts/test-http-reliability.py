#!/usr/bin/env python3
"""Check HTTP range handling, recovery, retry policy, and origin scheduling on loopback."""

import argparse
from base64 import b64encode
from dataclasses import dataclass, field
from email.utils import formatdate
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import re
import subprocess
import tempfile
from threading import Condition, Lock, Thread
import time
from typing import Optional


MIB = 1024 * 1024
PAYLOAD = hashlib.shake_256(b"aria2 HTTP reliability fixture").digest(10 * MIB)
RANGE = re.compile(r"bytes=(\d+)-(\d*)")
LAST_MODIFIED = "Wed, 01 Nov 2023 12:00:00 GMT"


@dataclass
class Request:
    method: str
    path: str
    range_header: Optional[str]
    if_range: Optional[str]
    seen: float = field(default_factory=time.monotonic)
    status: int = 200


@dataclass
class Transfer:
    payload: bytes = PAYLOAD
    payloads: dict = field(default_factory=dict)
    status: int = 200
    failures: int = 1
    retry_after: str = ""
    retry_after_date: bool = False
    drop_first: bool = False
    slow_first: bool = False
    chunked_range: str = ""
    content_disposition: str = ""
    etag: str = ""
    last_modified: str = ""
    ignore_if_range: bool = False
    chunked_if_range_mismatch: bool = False
    ignore_ranges: bool = False
    body_delay: float = 0
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

    def send_validators(self, transfer):
        if transfer.etag:
            self.send_header("ETag", transfer.etag)
        if transfer.last_modified:
            self.send_header("Last-Modified", transfer.last_modified)

    def do_HEAD(self):
        transfer = self.server.transfer
        with transfer.condition:
            transfer.requests.append(Request("HEAD", self.path, self.headers.get("Range"),
                                             self.headers.get("If-Range")))
        self.send_response(200)
        self.send_header("Content-Length", str(len(transfer.payload)))
        self.send_header("Accept-Ranges", "bytes")
        self.send_validators(transfer)
        self.end_headers()

    def do_GET(self):
        transfer = self.server.transfer
        payload = transfer.payloads.get(self.path, transfer.payload)
        range_header = self.headers.get("Range")
        if_range = self.headers.get("If-Range")
        request = Request("GET", self.path, range_header, if_range)
        match = RANGE.fullmatch(range_header or "")
        if range_header and not match:
            self.send_error(416)
            return
        start = 0
        end = len(payload) - 1
        validator_mismatch = (
            if_range is not None and not transfer.ignore_if_range and
            if_range not in (transfer.etag, transfer.last_modified)
        )
        if transfer.ignore_ranges:
            match = None
        elif validator_mismatch:
            # A changed representation returns the complete current entity.
            match = None
        elif match:
            start = int(match[1])
            if match[2]:
                end = min(end, int(match[2]))
        if not 0 <= start <= end:
            self.send_error(416)
            return

        with transfer.condition:
            transfer.requests.append(request)
            attempt = len(transfer.requests)
            transfer.active += 1
            transfer.peak = max(transfer.peak, transfer.active)
            transfer.condition.notify_all()

        try:
            if transfer.status != 200 and attempt <= transfer.failures:
                request.status = transfer.status
                self.send_response(request.status)
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
            chunked_response = bool(chunked_range) or (
                validator_mismatch and transfer.chunked_if_range_mismatch
            )
            request.status = 206 if match and chunked_range != "ignored" else 200
            self.send_response(request.status)
            body_start = start
            if match and chunked_range not in ("missing", "ignored"):
                body_start = start + 1 if chunked_range == "mismatch" else start
                self.send_header("Content-Range", f"bytes {body_start}-{end}/{len(payload)}")
            if chunked_range == "ignored":
                body_start = 0
            self.send_header("Accept-Ranges", "bytes")
            self.send_validators(transfer)
            if transfer.content_disposition:
                self.send_header("Content-Disposition", transfer.content_disposition)
            if chunked_response:
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
            elif chunked_response:
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
            elif transfer.body_delay:
                for offset in range(0, len(body), 64 * 1024):
                    time.sleep(transfer.body_delay)
                    self.wfile.write(body[offset : offset + 64 * 1024])
            else:
                self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            # A client can stop reading when its assigned range completes or when it retries.
            pass
        finally:
            with transfer.condition:
                transfer.active -= 1


def run_download(server, command, directory, *paths, options=()):
    return subprocess.run(
        [
            *command, "--no-conf", "--all-proxy=", "--no-proxy=127.0.0.1",
            "--file-allocation=none", "--split=1", "--max-connection-per-server=1",
            "--enable-http-keep-alive=false", "--timeout=15", "--connect-timeout=8",
            "--max-tries=2", "--retry-wait=0", "--console-log-level=warn",
            "--summary-interval=0", "--enable-color=false", *options,
            *(f"http://127.0.0.1:{server.server_port}/{path}" for path in paths),
        ],
        cwd=directory, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, errors="replace", timeout=55,
    )


def check_downloaded_file(target, payload, name):
    if not target.is_file() or hashlib.sha256(target.read_bytes()).digest() != hashlib.sha256(payload).digest():
        raise AssertionError(f"{name}: {target.name} differs from SHA-256 fixture")


def check_transfer(server, command, name, transfer, *, options=(), returncode=0,
                   attempts=None, min_delay=0, max_delay=None, resume_offset=0,
                   continued=False, request_sequence=()):
    server.transfer = transfer
    with tempfile.TemporaryDirectory() as directory:
        target = Path(directory) / "file.bin"
        if resume_offset:
            target.write_bytes(transfer.payload[:resume_offset])
        result = run_download(server, command, directory, "file.bin", options=("--out=file.bin", *options))
        requests = [request for request in transfer.requests if request.method == "GET"]
        starts = [int(RANGE.fullmatch(request.range_header)[1]) if request.range_header else None
                  for request in requests]
        if request_sequence:
            sequence = tuple((request.method, request.range_header) for request in transfer.requests)
            if sequence != request_sequence:
                raise AssertionError(f"{name}: expected {request_sequence}, received {sequence}")
        if result.returncode != returncode:
            raise AssertionError(f"{name}: expected exit {returncode}, got {result.returncode}; "
                                 f"request offsets={starts}\n{result.stdout}")
        if returncode == 0:
            check_downloaded_file(target, transfer.payload, name)
        elif resume_offset and target.read_bytes() != transfer.payload[:resume_offset]:
            raise AssertionError(f"{name}: rejected response changed the partial file")

    if attempts is not None and len(starts) != attempts:
        raise AssertionError(f"{name}: expected {attempts} requests, got offsets {starts}")
    if min_delay or max_delay is not None:
        delay = requests[1].seen - requests[0].seen
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


def check_verified_resume(server, command, name, initial, current, expected_if_range,
                          *, expected_status=206, fail_progress_save=False):
    initial.drop_first = True
    options = (
        "--continue=true", "--http-user=fixture-user", "--http-passwd=fixture-password",
        "--header=Cookie: fixture-session=fixture-cookie",
    )
    with tempfile.TemporaryDirectory() as directory:
        target = Path(directory) / "file.bin"
        control = target.with_name(target.name + ".aria2")
        server.transfer = initial
        result = run_download(server, command, directory, target.name, options=(*options, "--max-tries=1"))
        if not result.returncode or not control.is_file() or not target.is_file():
            raise AssertionError(f"{name}: interrupted download failed to leave a partial file and progress file\n"
                                 f"{result.stdout}")
        partial = target.read_bytes()
        saved_progress = control.read_bytes()
        if not 0 < len(partial) < len(initial.payload):
            raise AssertionError(f"{name}: expected an incomplete transfer, got {len(partial)} bytes")
        secrets = (b"fixture-user", b"fixture-password", b"fixture-cookie",
                   b64encode(b"fixture-user:fixture-password"))
        if any(secret in saved_progress for secret in secrets):
            raise AssertionError(f"{name}: credentials or cookies were saved in {control.name}")
        temporary_control = control.with_name(control.name + "__temp")
        if fail_progress_save:
            temporary_control.mkdir()

        server.transfer = current
        result = run_download(server, command, directory, target.name, options=options)
        resumed = [request for request in current.requests if request.range_header
                   and int(RANGE.fullmatch(request.range_header)[1]) > 0]
        if expected_status is not None and (
            not resumed or (resumed[0].if_range, resumed[0].status) != (expected_if_range, expected_status)
        ):
            raise AssertionError(f"{name}: expected If-Range={expected_if_range!r}, HTTP {expected_status}\n"
                                 f"{current.requests}\n{result.stdout}")
        if expected_if_range is None and any(request.if_range for request in current.requests):
            raise AssertionError(f"{name}: sent If-Range without a usable validator\n{current.requests}")
        if expected_status == 206 and initial.payload == current.payload:
            after_resume = current.requests[current.requests.index(resumed[0]) + 1:]
            if any(request.method == "GET" and (
                request.range_header is None or RANGE.fullmatch(request.range_header)[1] == "0"
            ) for request in after_resume):
                raise AssertionError(f"{name}: restarted after receiving the expected HTTP 206\n{current.requests}")
        if fail_progress_save:
            if not result.returncode or target.read_bytes() != partial or control.read_bytes() != saved_progress:
                raise AssertionError(f"{name}: failed progress save changed persisted state\n{result.stdout}")
            temporary_control.rmdir()
            result = run_download(server, command, directory, target.name, options=options)
        if result.returncode:
            raise AssertionError(f"{name}: download exited {result.returncode}\n{result.stdout}")
        check_downloaded_file(target, current.payload, name)

    print(f"PASS {name}", flush=True)


def check_verified_resumes(server, command):
    old_etag = '"fixture-v1"'
    new_etag = '"fixture-v2"'
    changed_payload = hashlib.shake_256(b"updated aria2 HTTP reliability fixture").digest(len(PAYLOAD))
    check_verified_resume(server, command, "unchanged strong ETag resumes with HTTP 206",
                          Transfer(etag=old_etag, last_modified=LAST_MODIFIED),
                          Transfer(etag=old_etag, last_modified=LAST_MODIFIED), old_etag)
    check_verified_resume(server, command, "changed strong ETag restarts after HTTP 200",
                          Transfer(etag=old_etag), Transfer(etag=new_etag, payload=changed_payload),
                          old_etag, expected_status=200)
    check_verified_resume(server, command, "chunked If-Range mismatch restarts with a known length",
                          Transfer(etag=old_etag),
                          Transfer(etag=new_etag, payload=changed_payload, chunked_if_range_mismatch=True),
                          old_etag, expected_status=200)
    check_verified_resume(server, command, "changed ETag and length restart the download",
                          Transfer(etag=old_etag), Transfer(etag=new_etag, payload=changed_payload[:-MIB]),
                          old_etag, expected_status=None)
    check_verified_resume(server, command, "failed progress save preserves the partial download",
                          Transfer(etag=old_etag), Transfer(etag=new_etag, payload=changed_payload),
                          old_etag, expected_status=200, fail_progress_save=True)
    check_verified_resume(server, command, "server ignoring If-Range can still return HTTP 206",
                          Transfer(etag=old_etag), Transfer(ignore_if_range=True), old_etag)
    check_verified_resume(server, command, "contradictory HTTP 206 ETag cannot append changed bytes",
                          Transfer(etag=old_etag),
                          Transfer(etag=new_etag, payload=changed_payload, ignore_if_range=True), old_etag)
    check_verified_resume(server, command, "weak HTTP 206 ETag cannot match a saved strong ETag",
                          Transfer(etag=old_etag),
                          Transfer(etag=f"W/{old_etag}", payload=changed_payload, ignore_if_range=True), old_etag)
    check_verified_resume(server, command, "weak ETag resumes without If-Range",
                          Transfer(etag=f"W/{old_etag}", last_modified=LAST_MODIFIED),
                          Transfer(etag=f"W/{old_etag}", last_modified=LAST_MODIFIED), None)
    check_verified_resume(server, command, "missing validators resume without If-Range", Transfer(), Transfer(), None)
    check_verified_resume(server, command, "strong Last-Modified resumes with HTTP 206",
                          Transfer(last_modified=LAST_MODIFIED), Transfer(last_modified=LAST_MODIFIED), LAST_MODIFIED)
    recent_date = formatdate(time.time(), usegmt=True)
    check_verified_resume(server, command, "recent Last-Modified resumes without If-Range",
                          Transfer(last_modified=recent_date), Transfer(last_modified=recent_date), None)


def check_duplicate_output(command):
    name = "unknown-length response preserves an active task's output"
    first_body = PAYLOAD[: 2 * MIB]
    second_body = b"another response for the same URL"
    with tempfile.TemporaryDirectory() as directory:
        folder = Path(directory)
        checkpoint = folder / "duplicate.bin.aria2"
        renamed = folder / "duplicate.1.bin"
        requests = []
        request_lock = Lock()

        def wait_for(predicate):
            deadline = time.monotonic() + 12
            while time.monotonic() < deadline:
                if predicate():
                    return True
                time.sleep(0.02)
            return False

        class DuplicateHandler(Handler):
            def do_GET(self):
                with request_lock:
                    requests.append(self.path)
                    first = len(requests) == 1
                if not first and not wait_for(checkpoint.is_file):
                    self.send_error(500)
                    return
                self.send_response(200)
                self.send_header("Connection", "close")
                self.send_header("ETag", '"duplicate-output"')
                if first:
                    self.send_header("Content-Length", str(len(first_body)))
                    self.end_headers()
                    self.wfile.write(first_body[:MIB])
                    if wait_for(checkpoint.is_file) and wait_for(
                        lambda: renamed.exists() or not checkpoint.exists()
                    ):
                        self.wfile.write(first_body[MIB:])
                else:
                    self.send_header("Transfer-Encoding", "chunked")
                    self.end_headers()
                    self.wfile.write(f"{len(second_body):x}\r\n".encode() + second_body + b"\r\n0\r\n\r\n")

        with Server(("127.0.0.1", 0), DuplicateHandler) as server:
            serving = Thread(target=server.serve_forever, daemon=True)
            serving.start()
            try:
                uri = f"http://127.0.0.1:{server.server_port}/duplicate.bin"
                (folder / "inputs.txt").write_text(f"{uri}\n{uri}\n", encoding="utf-8")
                result = run_download(server, command, directory, options=(
                    "--input-file=inputs.txt", "--max-concurrent-downloads=2",
                    "--max-tries=1", "--auto-file-renaming=true",
                ))
            finally:
                server.shutdown()
                serving.join()
        if result.returncode or len(requests) != 2:
            raise AssertionError(f"{name}: unexpected requests or exit {result.returncode}\n{result.stdout}")
        check_downloaded_file(folder / "duplicate.bin", first_body, name)
        check_downloaded_file(renamed, second_body, name)
    print(f"PASS {name}", flush=True)


def check_multiple_downloads(server, command, name, transfer, *, options=(), returncode=0, failed_path=None):
    server.transfer = transfer
    with tempfile.TemporaryDirectory() as directory:
        paths = [path[1:] for path in transfer.payloads]
        result = run_download(server, command, directory, *paths,
                              options=("--force-sequential=true", "--max-concurrent-downloads=4", *options))
        if result.returncode != returncode:
            raise AssertionError(f"{name}: expected exit {returncode}, got {result.returncode}\n"
                                 f"{transfer.requests}\n{result.stdout}")
        for path, payload in transfer.payloads.items():
            if path != failed_path:
                check_downloaded_file(Path(directory) / path[1:], payload, name)


def check_shared_cooldown(transfer, name, status):
    limited = transfer.requests[0]
    peers = [request for request in transfer.requests if request.path != limited.path]
    if limited.status != status or not peers or peers[0].seen - limited.seen < 1.9:
        raise AssertionError(f"{name}: sibling bypassed the shared cooldown\n{transfer.requests}")
    print(f"PASS {name}", flush=True)


def check_origin_scheduling(server, command):
    budget = "--max-overall-connection-per-origin"
    task_size = 64 * 1024
    files = {f"/task-{index}.bin": PAYLOAD[index * task_size : (index + 1) * task_size]
             for index in range(4)}
    for cap, peak in ((2, 2), (0, 4)):
        name = f"same-origin connection cap {cap} admits {peak} concurrent tasks"
        transfer = Transfer(payloads=files, concurrent=peak, body_delay=0.2)
        check_multiple_downloads(server, command, name, transfer, options=(f"{budget}={cap}",))
        if transfer.peak != peak:
            raise AssertionError(f"{name}: observed {transfer.peak} simultaneous responses")
        print(f"PASS {name}", flush=True)

    large, small = "/large.bin", "/small.bin"
    for ignore_ranges in (False, True):
        behavior = "ignores ranges" if ignore_ranges else "supports ranges"
        name = f"small same-origin task proceeds while a large download {behavior}"
        transfer = Transfer(payloads={large: PAYLOAD, small: b"small task"},
                            body_delay=0.01, ignore_ranges=ignore_ranges)
        check_multiple_downloads(server, command, name, transfer,
                                 options=(f"{budget}=1", "--piece-length=1M"))
        observed = [request.path for request in transfer.requests]
        if (not observed or observed[0] != large or small not in observed
                or large not in observed[observed.index(small) + 1:]):
            raise AssertionError(f"{name}: observed request order {observed}")
        if ignore_ranges:
            resumed = [request for request in transfer.requests if request.path == large and request.range_header]
            if len(resumed) != 1 or resumed[0].status != 200:
                raise AssertionError(f"{name}: expected one ignored range, got {resumed}")
        print(f"PASS {name}", flush=True)

    for status in (429, 503):
        name = f"HTTP {status} Retry-After is shared with a different same-origin task"
        transfer = Transfer(payloads=files, status=status, retry_after="2")
        check_multiple_downloads(server, command, name, transfer,
                                 options=(f"{budget}=1", "--retry-wait=1"))
        check_shared_cooldown(transfer, name, status)

    name = "host cooldown survives a failed task when the connection cap and request retry are disabled"
    transfer = Transfer(payloads=files, status=429, retry_after="2")
    check_multiple_downloads(server, command, name, transfer, returncode=29, failed_path=next(iter(files)),
                             options=(f"{budget}=0", "--max-concurrent-downloads=1"))
    check_shared_cooldown(transfer, name, 429)


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
            b"\x00\n" + f"http://127.0.0.1:{server.server_port}/nul-input.bin\n".encode()
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
        expected = Path(directory) / "nul-input.bin"
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
    parser.add_argument("--exclude-patches", default="", help="Comma-separated patch IDs")
    args = parser.parse_args()
    command = [str(args.binary.resolve())]
    if args.runner:
        command.insert(0, args.runner)

    excluded = set(args.exclude_patches.split(","))

    def patch_enabled(*patches):
        return args.patch_mode == "patched" and excluded.isdisjoint(patches)

    with Server(("127.0.0.1", 0), Handler) as server:
        serving = Thread(target=server.serve_forever, daemon=True)
        serving.start()
        try:
            check_transfer(server, command, "HTTP download and SHA-256", Transfer(), attempts=1)
            tuned_defaults = patch_enabled("0002")
            splits = 20 if tuned_defaults else 4
            split_size = "64K" if tuned_defaults else "1M"
            budget = (f"--max-overall-connection-per-origin={splits}",) if patch_enabled("0027") else ()
            check_transfer(server, command, f"{splits} simultaneous split requests", Transfer(concurrent=splits),
                           options=(f"--split={splits}", f"--max-connection-per-server={splits}",
                                    f"--min-split-size={split_size}", f"--piece-length={split_size}", *budget))
            check_transfer(server, command, "resume from a partial local file", Transfer(),
                           options=() if tuned_defaults else ("--continue=true",), resume_offset=MIB)
            check_transfer(server, command, "recover a truncated response", Transfer(drop_first=True),
                           attempts=2, continued=True)
            if patch_enabled("0012"):
                check_transfer(server, command, "resume with a matching chunked HTTP 206",
                               Transfer(chunked_range="valid"), options=("--continue=true",), resume_offset=MIB)
                for variant in ("missing", "mismatch", "ignored"):
                    check_transfer(server, command, f"reject chunked range response ({variant})",
                                   Transfer(chunked_range=variant), options=("--continue=true",),
                                   resume_offset=MIB, returncode=8)
                for variant in ("short-body", "oversized-chunk"):
                    check_transfer(server, command, f"reject mismatched chunked range body ({variant})",
                                   Transfer(chunked_range=variant), options=("--continue=true",),
                                   resume_offset=MIB, returncode=8)
            if patch_enabled("0012", "0016"):
                head_options = ("--use-head=true", "--enable-http-pipelining=true",
                                "--enable-http-keep-alive=true")
                head_range = (("HEAD", None), ("GET", "bytes=0-0"))
                check_transfer(server, command, "accept pipelined one-byte chunked range",
                               Transfer(payload=b"x", chunked_range="valid"), options=head_options,
                               request_sequence=head_range)
                check_transfer(server, command, "reject excess data in pipelined one-byte range",
                               Transfer(payload=b"x", chunked_range="overlong-body"),
                               options=head_options, returncode=8, request_sequence=head_range)
            if patch_enabled("0003"):
                check_transfer(server, command, "retry a slow transfer", Transfer(slow_first=True),
                               options=("--lowest-speed-limit=256K",), attempts=2, continued=True)
            if patch_enabled("0005", "0008"):
                check_retry_policy(server, command)
            if patch_enabled("0026"):
                check_verified_resumes(server, command)
                check_duplicate_output(command)
            if patch_enabled("0027"):
                check_origin_scheduling(server, command)
            if patch_enabled("0019"):
                check_content_disposition_trailing_semicolon(server, command)
            if patch_enabled("0018"):
                check_nul_prefixed_input_file(server, command)
        finally:
            server.shutdown()
            serving.join()


if __name__ == "__main__":
    main()
