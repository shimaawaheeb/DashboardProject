"""Vercel Python Function entry point for dashboard API routes."""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler
import json
from pathlib import Path
import sys
from urllib.parse import parse_qs, urlencode, urlparse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api_core import ApiResponse, DashboardAPI  # noqa: E402

api = DashboardAPI()


def headers_dict(handler: BaseHTTPRequestHandler) -> dict[str, str]:
    return {key: value for key, value in handler.headers.items()}


def route_path(raw_path: str, query: str) -> tuple[str, str]:
    parsed = urlparse(raw_path)
    path = parsed.path
    query_string = parsed.query or query
    params = parse_qs(query_string)
    if path in {"/api", "/api/", "/api/index.py"} and params.get("path"):
        forwarded = params["path"][0].strip("/")
        path = f"/api/{forwarded}" if forwarded else "/api"
        query_string = urlencode(
            [
                (key, value)
                for key, values in params.items()
                if key != "path"
                for value in values
            ]
        )
    return path, query_string


class handler(BaseHTTPRequestHandler):
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
        path, query = route_path(self.path, "")
        response = api.handle_get(path, query, headers_dict(self))
        self.send_api_response(response)

    def do_POST(self):
        path, _query = route_path(self.path, "")
        try:
            payload = self.read_json_body()
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
            self.send_api_response(ApiResponse(400, {"error": "Invalid request body."}))
            return
        response = api.handle_post(path, payload, headers_dict(self))
        self.send_api_response(response)
