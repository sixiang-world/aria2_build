#!/usr/bin/env python3
"""Compare aria2 binaries using identical, paced HTTP downloads on loopback."""

import argparse
from collections import defaultdict
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import re
import statistics
import subprocess
import tempfile
from threading import Lock, Thread
import time

try:
    import resource
except ImportError:
    resource = None  # Child CPU accounting is unavailable on Windows.


MIB = 1024 * 1024
CHUNK_SIZE = 64 * 1024


class BenchmarkServer(ThreadingHTTPServer):
    request_queue_size = 32

    def __init__(self, payload, delay):
        super().__init__(("127.0.0.1", 0), DownloadHandler)
        self.payload = memoryview(payload)
        self.delay = delay
        self.lock = Lock()
        self.active = 0
        self.peak = 0
        self.ranges = set()


class DownloadHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *_):
        pass

    def do_GET(self):
        if self.path != "/payload":
            self.send_error(404)
            return

        server = self.server
        size = len(server.payload)
        first, last = 0, size - 1
        requested_range = self.headers.get("Range")
        if requested_range is not None:
            match = re.fullmatch(r"bytes=(\d+)-(\d*)", requested_range)
            if match is None:
                self.send_error(400, "Expected one byte range")
                return
            first = int(match[1])
            if match[2]:
                last = min(last, int(match[2]))
            if first > last:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{size}")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return

        with server.lock:
            server.active += 1
            server.peak = max(server.peak, server.active)
            if requested_range is not None:
                server.ranges.add(first)

        try:
            self.send_response(206 if requested_range is not None else 200)
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(last - first + 1))
            self.send_header("Connection", "close")
            if requested_range is not None:
                self.send_header("Content-Range", f"bytes {first}-{last}/{size}")
            self.end_headers()

            next_chunk_at = time.perf_counter()
            for start in range(first, last + 1, CHUNK_SIZE):
                # Pace against fixed deadlines so incidental scheduling delays do not accumulate.
                next_chunk_at += server.delay
                wait = next_chunk_at - time.perf_counter()
                if wait > 0:
                    time.sleep(wait)
                self.wfile.write(server.payload[start : min(start + CHUNK_SIZE, last + 1)])
        except (BrokenPipeError, ConnectionResetError):
            # aria2 may close a request once another connection owns its remaining data.
            pass
        finally:
            with server.lock:
                server.active -= 1


def child_cpu_time():
    if resource is None:
        return 0.0
    usage = resource.getrusage(resource.RUSAGE_CHILDREN)
    return usage.ru_utime + usage.ru_stime


def run_trial(binary, connections, payload, digest, delay):
    with tempfile.TemporaryDirectory(prefix="aria2-benchmark-") as directory:
        with BenchmarkServer(payload, delay) as server:
            worker = Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05})
            worker.start()
            command = [
                str(binary), "--no-conf", "--no-proxy=127.0.0.1", "--continue=false",
                "--auto-file-renaming=false", "--file-allocation=none",
                "--enable-http-keep-alive=false", "--http-accept-gzip=false",
                "--min-split-size=1M", "--max-tries=1", "--summary-interval=0",
                "--console-log-level=warn", "--timeout=10", "--connect-timeout=5",
                f"--split={connections}", f"--max-connection-per-server={connections}",
                "--out=payload.bin", f"http://127.0.0.1:{server.server_port}/payload",
            ]
            try:
                cpu_start = child_cpu_time()
                start = time.perf_counter()
                result = subprocess.run(
                    command, cwd=directory, capture_output=True, text=True,
                    timeout=30 + 3 * (len(payload) / CHUNK_SIZE) * delay,
                )
                elapsed = time.perf_counter() - start
                cpu_time = child_cpu_time() - cpu_start
            finally:
                server.shutdown()
                worker.join()

            if result.returncode:
                raise RuntimeError(
                    f"{binary} exited {result.returncode}\n{result.stdout}{result.stderr}"
                )
            output = Path(directory) / "payload.bin"
            if not output.is_file() or hashlib.sha256(output.read_bytes()).digest() != digest:
                raise RuntimeError(f"{binary} produced incorrect bytes")
            with server.lock:
                peak = server.peak
                nonzero_ranges = len(server.ranges - {0})
            if connections == 1 and (peak != 1 or nonzero_ranges):
                raise RuntimeError(f"{binary} did not perform a single-stream transfer")
            if connections > 1 and (peak < 2 or nonzero_ranges == 0):
                raise RuntimeError(f"{binary} did not perform parallel Range transfers")
            return elapsed, peak, nonzero_ranges, cpu_time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("binaries", type=Path, nargs="+", help="Native aria2c binaries")
    parser.add_argument("--runs", type=int, default=5, help="Measured trials per scenario")
    parser.add_argument("--size-mib", type=int, default=12, help="Payload size in MiB")
    parser.add_argument("--parallel", type=int, default=4, help="Parallel connection limit")
    parser.add_argument("--delay-ms", type=float, default=4, help="Delay per 64 KiB per response")
    args = parser.parse_args()

    if args.runs < 1 or not 2 <= args.parallel <= 16:
        parser.error("--runs must be positive and --parallel must be between 2 and 16")
    if not args.parallel * 2 <= args.size_mib <= 128 or not 0 < args.delay_ms <= 100:
        parser.error("--size-mib must be between twice --parallel and 128, and --delay-ms in (0, 100]")

    binaries = [path.resolve() for path in args.binaries]
    if len(set(binaries)) != len(binaries):
        parser.error("pass each binary path at most once")
    for binary in binaries:
        if not binary.is_file():
            parser.error(f"not a binary file: {binary}")
    payload = hashlib.shake_256(b"aria2 benchmark payload").digest(args.size_mib * MIB)
    digest = hashlib.sha256(payload).digest()
    delay = args.delay_ms / 1000
    print(
        f"HTTP loopback: {args.size_mib} MiB, {args.delay_ms:g} ms per 64 KiB per response, "
        f"one warmup and {args.runs} measured trials per scenario; SHA-256 checked"
    )
    print(f"Payload SHA-256: {digest.hex()}")
    for binary in binaries:
        binary_digest = hashlib.sha256(binary.read_bytes()).hexdigest()
        print(f"Binary SHA-256 {binary_digest}  {binary}", flush=True)

    for connections in (1, args.parallel):
        measurements = defaultdict(list)
        # Rotate trial order to spread the effects of transient host load across binaries.
        for trial in range(args.runs + 1):
            offset = trial % len(binaries)
            for binary in binaries[offset:] + binaries[:offset]:
                result = run_trial(binary, connections, payload, digest, delay)
                if trial:
                    measurements[binary].append(result)

        print(f"\nConnection limit: {connections}")
        for binary in binaries:
            times, peaks, ranges, cpu_times = zip(*measurements[binary])
            median = statistics.median(times)
            cpu_summary = ""
            if resource is not None:
                cpu_summary = f"; {statistics.median(cpu_times) * 1000:.1f} ms median CPU"
            print(
                f"  {binary}\n"
                f"    {median:.3f} s median, {args.size_mib / median:.2f} MiB/s; "
                f"{min(times):.3f}–{max(times):.3f} s range; "
                f"peak concurrent responses {min(peaks)}–{max(peaks)}, "
                f"distinct nonzero Range starts {min(ranges)}–{max(ranges)}{cpu_summary}",
                flush=True,
            )


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, OSError, subprocess.TimeoutExpired) as error:
        raise SystemExit(str(error)) from error
