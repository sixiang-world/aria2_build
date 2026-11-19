#!/usr/bin/env python3
"""Verify BitTorrent downloads and piece selection using only loopback peers."""

import argparse
import contextlib
import functools
import hashlib
import http.server
import os
import pathlib
import socket
import socketserver
import struct
import subprocess
import tempfile
import threading


LOOPBACK = "127.0.0.1"
HANDSHAKE = b"\x13BitTorrent protocol" + b"\0" * 8
PIECE_SIZE = 16 * 1024
PIECE_COUNT = 33
PAYLOAD = b"".join(
    hashlib.sha256(str(index).encode()).digest() * (PIECE_SIZE // 32)
    for index in range(PIECE_COUNT)
)


def bencode(value):
    if isinstance(value, bytes):
        return str(len(value)).encode() + b":" + value
    if isinstance(value, int):
        return b"i" + str(value).encode() + b"e"
    return b"d" + b"".join(
        bencode(key) + bencode(value[key]) for key in sorted(value)
    ) + b"e"


@contextlib.contextmanager
def running(server):
    with server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield server.server_address[1]
        finally:
            server.shutdown()
            thread.join()


def receive(stream, length):
    data = stream.read(length)
    if len(data) != length:
        raise EOFError(f"peer disconnected while reading {length} bytes")
    return data


def message(identifier, payload=b""):
    return struct.pack("!IB", len(payload) + 1, identifier) + payload


class Tracker(http.server.BaseHTTPRequestHandler):
    def __init__(self, peer_ports, *args):
        self.peer_ports = peer_ports
        super().__init__(*args)

    def do_GET(self):
        peers = b"".join(
            socket.inet_aton(LOOPBACK) + struct.pack("!H", port)
            for port in self.peer_ports
        )
        response = bencode({b"interval": 3600, b"peers": peers})
        self.send_response(200)
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)

    def log_message(self, *_):
        pass


class Peer(socketserver.StreamRequestHandler):
    def __init__(self, payload, info_hash, requests, stalled, ready, *args):
        self.payload = payload
        self.info_hash = info_hash
        self.requests = requests
        self.stalled = stalled
        self.ready = ready
        super().__init__(*args)

    def handle(self):
        self.connection.settimeout(25)
        try:
            handshake = receive(self.rfile, 68)
            if handshake[:20] != HANDSHAKE[:20]:
                # aria2 may try an encrypted handshake before plain BitTorrent.
                return
            if handshake[28:48] != self.info_hash:
                raise ValueError("unexpected BitTorrent info hash")
            peer_id = b"-TST001-00000000000" + (b"1" if self.stalled else b"2")
            self.wfile.write(HANDSHAKE + self.info_hash + peer_id)
            if self.ready is not None and not self.stalled and not self.ready.wait(12):
                raise TimeoutError("the first peer did not receive every request")
            piece_count = len(self.payload) // PIECE_SIZE
            bits = ((1 << piece_count) - 1) << (-piece_count % 8)
            self.wfile.write(message(5, bits.to_bytes((piece_count + 7) // 8, "big")))
            self.wfile.write(message(1))  # Unchoke.

            while True:
                length = struct.unpack("!I", receive(self.rfile, 4))[0]
                if length == 0:
                    continue
                body = receive(self.rfile, length)
                if body[0] == 6:  # Block request.
                    piece, offset, size = struct.unpack("!III", body[1:])
                    if piece >= piece_count or not 0 < size <= PIECE_SIZE - offset:
                        raise ValueError("invalid BitTorrent block request")
                    self.requests.append(piece)
                    if self.stalled:
                        if len(set(self.requests)) == piece_count:
                            self.ready.set()
                        continue
                    start = piece * PIECE_SIZE + offset
                    block = self.payload[start : start + size]
                    self.wfile.write(message(7, body[1:9] + block))
        except (EOFError, ConnectionResetError, BrokenPipeError):
            # The client closes its peer connection after validating the payload.
            pass


def run_case(command, options, expected_order=None, *, endgame=False):
    piece_count = 4 if endgame else PIECE_COUNT
    payload = PAYLOAD[:piece_count * PIECE_SIZE]
    requests = []
    info = {
        b"length": len(payload),
        b"name": b"payload.bin",
        b"piece length": PIECE_SIZE,
        b"pieces": b"".join(
            hashlib.sha1(payload[offset : offset + PIECE_SIZE]).digest()
            for offset in range(0, len(payload), PIECE_SIZE)
        ),
        b"private": 1,
    }

    info_hash = hashlib.sha1(bencode(info)).digest()
    ready = threading.Event() if endgame else None
    peer = functools.partial(Peer, payload, info_hash, requests, False, ready)
    with contextlib.ExitStack() as stack:
        peer_ports = []
        if endgame:
            # With all pieces already assigned to this silent peer, aria2
            # enters endgame before requesting them from the responding peer.
            stalled = functools.partial(Peer, payload, info_hash, [], True, ready)
            peer_ports.append(stack.enter_context(
                running(socketserver.ThreadingTCPServer((LOOPBACK, 0), stalled))
            ))
        peer_ports.append(stack.enter_context(
            running(socketserver.ThreadingTCPServer((LOOPBACK, 0), peer))
        ))
        tracker = functools.partial(Tracker, peer_ports)
        with running(http.server.ThreadingHTTPServer((LOOPBACK, 0), tracker)) as tracker_port:
            with tempfile.TemporaryDirectory(prefix="aria2-bittorrent-") as directory:
                cwd = pathlib.Path(directory)
                (cwd / "test.torrent").write_bytes(bencode({
                    b"announce": f"http://{LOOPBACK}:{tracker_port}/announce".encode(),
                    b"info": info,
                }))
                # Input/output paths are relative so the same command works through Wine.
                result = subprocess.run(
                    command + [
                        "--no-conf", "--all-proxy=", f"--no-proxy={LOOPBACK}",
                        f"--interface={LOOPBACK}", "--disable-ipv6=true",
                        "--enable-dht=false", "--enable-dht6=false",
                        "--enable-peer-exchange=false", "--bt-enable-lpd=false",
                        "--listen-port=49152-65535", f"--bt-max-peers={len(peer_ports)}",
                        "--bt-tracker-connect-timeout=5", "--bt-tracker-timeout=5",
                        "--bt-stop-timeout=15", "--file-allocation=none",
                        "--seed-time=0", "--summary-interval=0",
                        "--show-console-readout=false",
                    ] + options + ["test.torrent"],
                    cwd=cwd, env={**os.environ, "LC_ALL": "C"},
                    capture_output=True, text=True, timeout=35, check=False,
                )
                if result.returncode != 0:
                    raise RuntimeError(
                        f"aria2 {options} exited with {result.returncode}\n"
                        f"{result.stdout}{result.stderr}"
                    )
                actual = hashlib.sha256((cwd / "payload.bin").read_bytes()).hexdigest()
                if actual != hashlib.sha256(payload).hexdigest():
                    raise RuntimeError(f"downloaded payload SHA-256 mismatch: {actual}")
    if expected_order is not None:
        actual_order = list(dict.fromkeys(requests))
        if actual_order != expected_order:
            raise RuntimeError(f"piece request order {actual_order}, expected {expected_order}")
    phase = "endgame" if endgame else "download"
    print(f"PASS BitTorrent loopback {phase} with {piece_count} pieces {options or '(default)'}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("binary", type=pathlib.Path)
    parser.add_argument("--runner", help="Optional emulator executable such as Wine or QEMU")
    parser.add_argument("--baseline", action="store_true", help="Test an unpatched aria2 binary")
    args = parser.parse_args()
    command = ([args.runner] if args.runner else []) + [str(args.binary.resolve())]

    run_case(command, [] if args.baseline else ["--bt-piece-selector=default"])
    if not args.baseline:
        sequential = ["--bt-piece-selector=inorder"]
        ordered = list(range(PIECE_COUNT))
        run_case(command, sequential, ordered)
        run_case(command, sequential + ["--bt-prioritize-piece=tail=16K"],
                 [ordered[-1]] + ordered[:-1])
        run_case(command, sequential, list(range(4)), endgame=True)


if __name__ == "__main__":
    main()
