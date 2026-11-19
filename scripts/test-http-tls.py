#!/usr/bin/env python3
"""Verify HTTPS certificate verification using a local loopback TLS server."""

import argparse
from contextlib import contextmanager
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
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


def openssl(*args):
    result = subprocess.run(["openssl", *args], capture_output=True, text=True, timeout=25)
    if result.returncode:
        raise SystemExit(f"openssl {args[0]} failed:\n{result.stdout}{result.stderr}")


def generate_ca(directory, name):
    cert = directory / f"{name}.crt"
    key = directory / f"{name}.key"
    config = directory / f"{name}.cnf"
    config.write_text(
        "[req]\n"
        "distinguished_name=dn\n"
        "x509_extensions=ca\n"
        "prompt=no\n"
        "[dn]\n"
        f"CN=aria2 loopback {name}\n"
        "[ca]\n"
        "basicConstraints=critical,CA:TRUE,pathlen:0\n"
        "keyUsage=critical,keyCertSign,cRLSign\n"
        "subjectKeyIdentifier=hash\n",
        encoding="utf-8",
    )
    openssl(
        "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "2",
        "-keyout", str(key), "-out", str(cert), "-config", str(config),
    )
    return cert, key


def generate_server_key(directory):
    key = directory / "server.key"
    request = directory / "server.csr"
    openssl(
        "req", "-new", "-newkey", "rsa:2048", "-nodes", "-subj", "/CN=aria2 loopback leaf",
        "-keyout", str(key), "-out", str(request),
    )
    return key, request


def issue_certificate(directory, ca_cert, ca_key, request, name, ip, eku):
    cert = directory / f"{name}.crt"
    extensions = directory / f"{name}.ext"
    extensions.write_text(
        "basicConstraints=critical,CA:FALSE\n"
        "keyUsage=critical,digitalSignature,keyEncipherment\n"
        f"extendedKeyUsage={eku}\n"
        f"subjectAltName=IP:{ip}\n",
        encoding="utf-8",
    )
    openssl(
        "x509", "-req", "-in", str(request), "-CA", str(ca_cert), "-CAkey", str(ca_key),
        "-CAcreateserial", "-days", "2", "-sha256", "-extfile", str(extensions),
        "-out", str(cert),
    )
    return cert


@contextmanager
def serve_tls(cert, key):
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(certfile=str(cert), keyfile=str(key))
    with ThreadingHTTPServer(("127.0.0.1", 0), TlsHandler) as server:
        server.socket = ctx.wrap_socket(server.socket, server_side=True)
        worker = Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            yield f"https://127.0.0.1:{server.server_port}/payload.bin"
        finally:
            server.shutdown()
            worker.join()


def check_download(command, directory, env, url, label, accepted, *options, verify=True, reason=None):
    output = directory / f"{label}.bin"
    result = subprocess.run(
        [
            *command, "--no-conf", "--all-proxy=", "--no-proxy=127.0.0.1",
            "--file-allocation=none", "--split=1", "--max-connection-per-server=1",
            "--max-tries=1", "--timeout=10", "--connect-timeout=5",
            "--summary-interval=0", "--console-log-level=warn",
            f"--check-certificate={'true' if verify else 'false'}",
            f"--out={output.name}", *options, url,
        ],
        cwd=directory, env=env, capture_output=True, text=True, timeout=25,
    )
    logs = result.stdout + result.stderr
    if accepted:
        if result.returncode:
            raise SystemExit(f"HTTPS {label} failed (exit {result.returncode}):\n{logs}")
        if not output.is_file() or hashlib.sha256(output.read_bytes()).digest() != DIGEST:
            raise SystemExit(f"HTTPS {label} payload SHA-256 mismatch")
    elif not result.returncode or "SSL/TLS handshake failure" not in logs:
        raise SystemExit(f"HTTPS {label} did not reject the certificate (exit {result.returncode}):\n{logs}")
    elif reason and reason not in logs:
        raise SystemExit(f"HTTPS {label} failed for an unexpected reason:\n{logs}")
    print(f"PASS HTTPS loopback {label}")


def check_windows_sidecar(command, directory, env, url, ca_cert):
    if len(command) > 1:
        # Wine must be able to decode the Unicode executable directory.
        env = dict(env, LC_ALL="C.UTF-8")
    exe_dir = directory / "aria2-证书"
    exe_dir.mkdir()
    exe = exe_dir / "aria2c.exe"
    shutil.copy2(command[-1], exe)
    sidecar_command = [*command[:-1], str(exe)]
    sidecar = exe_dir / "cacert.pem"
    other_ca, _ = generate_ca(directory, "other-ca")
    shutil.copyfile(ca_cert, sidecar)
    shutil.copyfile(other_ca, directory / "cacert.pem")
    check_download(sidecar_command, directory, env, url, "executable-directory-ca", True)
    check_download(
        sidecar_command, directory, dict(env, SSL_CERT_FILE="missing.crt"), url,
        "missing-environment-ca-fallback", True,
    )
    check_download(
        sidecar_command, directory, env, url, "missing-explicit-ca-fallback", True,
        "--ca-certificate=missing.crt",
    )
    check_download(
        sidecar_command, directory, dict(env, SSL_CERT_FILE=other_ca.name), url,
        "environment-ca-overrides-sidecar", False,
    )
    check_download(
        sidecar_command, directory, dict(env, SSL_CERT_FILE=ca_cert.name), url,
        "explicit-ca-overrides-environment-and-sidecar", False, f"--ca-certificate={other_ca.name}",
    )
    sidecar.unlink()
    shutil.copyfile(ca_cert, directory / "cacert.pem")
    check_download(sidecar_command, directory, env, url, "ignores-working-directory-ca", False)
    check_download(
        sidecar_command, directory, dict(env, SSL_CERT_FILE=ca_cert.name), url,
        "trusted-environment-ca", True,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("binary", type=Path)
    parser.add_argument("--runner", help="Optional emulator executable such as qemu-aarch64 or wine")
    parser.add_argument("--baseline", action="store_true", help="Test upstream behavior without repository patches")
    parser.add_argument("--exclude-patches", default="", help="Comma-separated patch numbers excluded from the build")
    args = parser.parse_args()

    if shutil.which("openssl") is None:
        raise SystemExit("Loopback TLS test requires the openssl CLI")

    binary = args.binary.resolve()
    command = ([args.runner] if args.runner else []) + [str(binary)]
    version = subprocess.run([*command, "--version"], check=True, capture_output=True, text=True, timeout=25)
    libraries = next((line.split()[1:] for line in version.stdout.splitlines() if line.startswith("Libraries:")), [])
    platform_backend = next((lib for lib in ("WinTLS", "AppleTLS") if lib in libraries), None)
    openssl_family = any(lib.startswith(("OpenSSL/", "LibreSSL/")) for lib in libraries)
    env = os.environ.copy()
    env.pop("SSL_CERT_FILE", None)
    env.pop("SSL_CERT_DIR", None)
    with tempfile.TemporaryDirectory(prefix="aria2-tls-") as directory_name:
        directory = Path(directory_name)
        ca_cert, ca_key = generate_ca(directory, "test-ca")
        key, request = generate_server_key(directory)
        cert = issue_certificate(directory, ca_cert, ca_key, request, "server", "127.0.0.1", "serverAuth")
        ca_option = f"--ca-certificate={ca_cert.name}"
        with serve_tls(cert, key) as url:
            check_download(command, directory, env, url, "rejects-untrusted-certificate", False)
            if platform_backend:
                check_download(command, directory, env, url, "without-verification", True, verify=False)
                print(f"SKIP HTTPS trusted CA, hostname and EKU cases ({platform_backend} uses the system trust store)")
                return
            check_download(command, directory, env, url, "trusted-ca-verification", True, ca_option)
            if (
                binary.suffix.lower() == ".exe" and not args.baseline
                and "0023" not in args.exclude_patches.split(",")
                and env.get("TLS_BACKEND", "openssl") == "openssl" and openssl_family
            ):
                check_windows_sidecar(command, directory, env, url, ca_cert)

        wrong_host = issue_certificate(directory, ca_cert, ca_key, request, "wrong-host", "127.0.0.2", "serverAuth")
        with serve_tls(wrong_host, key) as url:
            check_download(
                command, directory, env, url, "rejects-wrong-hostname", False, ca_option,
                reason="hostname does not match" if openssl_family else None,
            )

        client_only = issue_certificate(directory, ca_cert, ca_key, request, "client-only", "127.0.0.1", "clientAuth")
        with serve_tls(client_only, key) as url:
            check_download(
                command, directory, env, url, "rejects-clientAuth-only-EKU", False, ca_option,
                reason="certificate purpose" if openssl_family else None,
            )


if __name__ == "__main__":
    main()
