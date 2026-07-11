#!/usr/bin/env python3
"""Local development server for the Enterprise dashboard."""

from __future__ import annotations

import argparse
import json
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from api_core import ApiResponse, DashboardAPI
from config import CLEANED_WORKBOOK, ensure_runtime_files
from server_data import is_company_employee_email, parse_workbook

ROOT = Path(__file__).resolve().parent
WORKBOOK = CLEANED_WORKBOOK
DEFAULT_PORT = 8000


def headers_dict(handler: SimpleHTTPRequestHandler) -> dict[str, str]:
    return {key: value for key, value in handler.headers.items()}


class DashboardHandler(SimpleHTTPRequestHandler):
    api = DashboardAPI()

    def __init__(self, *args, **kwargs):
        ensure_runtime_files()
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()

    def send_api_response(self, response: ApiResponse) -> None:
        if response.redirect:
            self.send_response(response.status)
            self.send_header("Location", response.redirect)
            for key, value in response.headers.items():
                self.send_header(key, value)
            self.end_headers()
            return

        payload = response.payload or {}
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(response.status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        for key, value in response.headers.items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(encoded)

    def read_json_body(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0 or length > 1_000_000:
            raise ValueError
        payload = json.loads(self.rfile.read(length).decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError
        return payload

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/"):
            response = self.api.handle_get(parsed.path, parsed.query, headers_dict(self))
            self.send_api_response(response)
            return
        super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        if not parsed.path.startswith("/api/"):
            self.send_api_response(ApiResponse(404, {"error": "Not found"}))
            return
        try:
            payload = self.read_json_body()
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
            self.send_api_response(ApiResponse(400, {"error": "Invalid request body."}))
            return
        response = self.api.handle_post(parsed.path, payload, headers_dict(self))
        self.send_api_response(response)

    def log_message(self, message, *args):
        print(f"[dashboard] {message % args}", flush=True)


def create_server(host: str, port: int) -> tuple[ThreadingHTTPServer, int]:
    """Bind exactly the requested port."""
    if not 0 <= port <= 65535:
        raise ValueError("Port must be between 0 and 65535")
    server = ThreadingHTTPServer((host, port), DashboardHandler)
    return server, server.server_address[1]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the Enterprise dashboard")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", default=DEFAULT_PORT, type=int)
    arguments = parser.parse_args()
    server, selected_port = create_server(arguments.host, arguments.port)
    print(f"Dashboard running at http://127.0.0.1:{selected_port}", flush=True)
    print(f"Reading {WORKBOOK}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.", flush=True)
    finally:
        server.server_close()
