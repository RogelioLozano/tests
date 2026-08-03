"""Minimal HTTPS server."""

import os
import ssl
import threading
from functools import partial
from http.server import (
    BaseHTTPRequestHandler,
    SimpleHTTPRequestHandler,
    ThreadingHTTPServer,
)

HOST = "127.0.0.1"
PORT = 9001
REDIRECT_PORT = 8080
CERT_FILE = os.environ.get("TLS_CERT_FILE", "cert.pem")
KEY_FILE = os.environ.get("TLS_KEY_FILE", "key.pem")
# Resolved from this file, not the CWD, so the served tree never depends on where
# the process was launched from.
SERVE_DIR = os.environ.get(
    "SERVE_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "public")
)
# Comma-separated origins allowed to read responses from scripts. Empty = none.
CORS_ALLOWED_ORIGINS = frozenset(
    o.strip() for o in os.environ.get("CORS_ALLOW_ORIGIN", "").split(",") if o.strip()
)
NOT_FOUND_PAGE = os.path.join(SERVE_DIR, "404.html")


class StaticHandler(SimpleHTTPRequestHandler):
    # The stdlib mapping defers to the platform mimetypes database, which varies
    # by machine and omits newer web types; pin the ones a frontend needs.
    extensions_map = {
        **SimpleHTTPRequestHandler.extensions_map,
        ".html": "text/html; charset=utf-8",
        ".css": "text/css; charset=utf-8",
        ".js": "text/javascript; charset=utf-8",
        ".mjs": "text/javascript; charset=utf-8",
        ".json": "application/json; charset=utf-8",
        ".map": "application/json; charset=utf-8",
        ".svg": "image/svg+xml",
        ".webmanifest": "application/manifest+json",
        ".woff2": "font/woff2",
    }

    def list_directory(self, path: str) -> None:
        # A directory with no index file is not content. Listing it would hand a
        # visitor a map of the tree, so it is indistinguishable from a missing path.
        self.send_error(404, "Not Found")
        return None

    def send_error(self, code: int, message=None, explain=None) -> None:
        if code == 404:
            try:
                with open(NOT_FOUND_PAGE, "rb") as page:
                    body = page.read()
            except OSError:
                pass  # No custom page installed; fall through to the stdlib one.
            else:
                self.send_response(404, message)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                if self.command != "HEAD":
                    self.wfile.write(body)
                return
        super().send_error(code, message, explain)

    def end_headers(self) -> None:
        origin = self.headers.get("Origin")
        # Exact match against the allowlist; echoing back an arbitrary Origin would
        # grant access to every site.
        if origin and origin in CORS_ALLOWED_ORIGINS:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        super().end_headers()


class RedirectHandler(BaseHTTPRequestHandler):
    """Answers every request with a 301 to the HTTPS equivalent."""

    protocol_version = "HTTP/1.1"

    def _redirect(self) -> None:
        # The target host is taken from configuration, never from the request,
        # so a forged Host header cannot turn this into an open redirect.
        path = self.path if self.path.startswith("/") else "/"
        self.send_response(301)
        self.send_header("Location", f"https://{HOST}:{PORT}{path}")
        self.send_header("Content-Length", "0")
        self.send_header("Connection", "close")
        self.end_headers()

    do_GET = _redirect
    do_HEAD = _redirect
    do_POST = _redirect
    do_PUT = _redirect
    do_DELETE = _redirect
    do_PATCH = _redirect
    do_OPTIONS = _redirect


def main() -> None:
    if not os.path.isdir(SERVE_DIR):
        raise SystemExit(f"Served directory not found: {SERVE_DIR}")

    handler = partial(StaticHandler, directory=SERVE_DIR)
    httpd = ThreadingHTTPServer((HOST, PORT), handler)

    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    try:
        context.load_cert_chain(certfile=CERT_FILE, keyfile=KEY_FILE)
    except FileNotFoundError:
        raise SystemExit(
            "TLS certificate files not found. "
            "Set TLS_CERT_FILE and TLS_KEY_FILE to existing files, "
            "or generate local dev certs (for example with openssl)."
        )
    httpd.socket = context.wrap_socket(httpd.socket, server_side=True)

    redirectd = ThreadingHTTPServer((HOST, REDIRECT_PORT), RedirectHandler)
    threading.Thread(target=redirectd.serve_forever, daemon=True).start()

    print(f"Redirecting http://{HOST}:{REDIRECT_PORT} -> https://{HOST}:{PORT}")
    print(f"Serving {SERVE_DIR} on https://{HOST}:{PORT}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        redirectd.shutdown()
        redirectd.server_close()
        httpd.server_close()


if __name__ == "__main__":
    main()
