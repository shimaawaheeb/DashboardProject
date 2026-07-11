#!/usr/bin/env python3
"""Dependency-free server for the Enterprise Projects & Workforce dashboard."""

from __future__ import annotations

import json
import re
import argparse
import os
from http.cookies import SimpleCookie
from datetime import datetime, timedelta, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path, PurePosixPath
from urllib.parse import urlencode, urlparse, parse_qs
import urllib.error
import urllib.request
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from admin_data import (
    AdminDataError,
    REQUIRED_FIELDS as ADMIN_REQUIRED_FIELDS,
    TABLES as ADMIN_TABLES,
    apply_record_action,
    restore_table_records,
)
from assistant import DashboardAssistant, GeminiError
from auth import AuthError, AuthStore, SESSION_COOKIE
from config import CLEANED_WORKBOOK, ensure_runtime_files

ROOT = Path(__file__).resolve().parent
ensure_runtime_files()
WORKBOOK = CLEANED_WORKBOOK
DEFAULT_PORT = 8000
EMPLOYEE_SIGNUP_ERROR = (
    "Sorry, you can not sign up because this email is not registered as a "
    "company employee."
)

MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def excel_date(value: int | float) -> str:
    moment = datetime(1899, 12, 30) + timedelta(days=float(value))
    if moment.time() == datetime.min.time():
        return moment.date().isoformat()
    return moment.isoformat(timespec="minutes")


def column_index(reference: str) -> int:
    letters = re.match(r"[A-Z]+", reference)
    if not letters:
        raise ValueError(f"Invalid cell reference: {reference}")
    result = 0
    for letter in letters.group():
        result = result * 26 + ord(letter) - 64
    return result - 1


def parse_workbook(path: Path) -> dict:
    with ZipFile(path) as archive:
        shared_strings: list[str] = []
        try:
            shared_root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
        except KeyError:
            shared_root = None
        if shared_root is not None:
            for item in shared_root.findall(f"{{{MAIN_NS}}}si"):
                shared_strings.append(
                    "".join(node.text or "" for node in item.iter(f"{{{MAIN_NS}}}t"))
                )

        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        relationships = ET.fromstring(
            archive.read("xl/_rels/workbook.xml.rels")
        )
        targets = {node.attrib["Id"]: node.attrib["Target"] for node in relationships}

        sheet_paths: dict[str, str] = {}
        sheets = workbook.find(f"{{{MAIN_NS}}}sheets")
        if sheets is None:
            raise ValueError("Workbook contains no worksheets")
        for sheet in sheets:
            relationship_id = sheet.attrib[f"{{{REL_NS}}}id"]
            target = targets[relationship_id]
            sheet_paths[sheet.attrib["name"]] = (
                target.lstrip("/")
                if target.startswith("/xl/")
                else str(PurePosixPath("xl") / target)
            )

        def cell_value(cell: ET.Element):
            value_node = cell.find(f"{{{MAIN_NS}}}v")
            inline_node = cell.find(f"{{{MAIN_NS}}}is")
            cell_type = cell.attrib.get("t")
            if inline_node is not None:
                return "".join(
                    node.text or "" for node in inline_node.iter(f"{{{MAIN_NS}}}t")
                )
            if value_node is None:
                return None
            raw = value_node.text
            if cell_type == "s":
                return shared_strings[int(raw)]
            if cell_type == "b":
                return raw == "1"
            if cell_type in {"str", "e"}:
                return raw
            try:
                return float(raw) if "." in raw else int(raw)
            except (TypeError, ValueError):
                return raw

        date_fields = {
            "Employees": {"Hire Date"},
            "Projects": {"Start Date", "Target End Date"},
            "Tasks": {"Due Date"},
            "Meetings": {"Date/Time"},
            "Weekly Updates": {"Week Starting"},
            "Activity Log": {"Timestamp"},
        }
        source_sheets = [
            "Departments",
            "Employees",
            "Projects",
            "Tasks",
            "Meetings",
            "Weekly Updates",
            "Activity Log",
            "Lists",
        ]
        result: dict[str, list[dict]] = {}

        for sheet_name in source_sheets:
            root = ET.fromstring(archive.read(sheet_paths[sheet_name]))
            rows: list[list] = []
            for row_node in root.findall(
                f".//{{{MAIN_NS}}}sheetData/{{{MAIN_NS}}}row"
            ):
                cells: dict[int, object] = {}
                for cell in row_node.findall(f"{{{MAIN_NS}}}c"):
                    cells[column_index(cell.attrib["r"])] = cell_value(cell)
                if cells:
                    row = [None] * (max(cells) + 1)
                    for index, value in cells.items():
                        row[index] = value
                    rows.append(row)

            if not rows:
                result[sheet_name] = []
                continue

            headers = rows[0]
            records = []
            for row in rows[1:]:
                if not row or row[0] in (None, ""):
                    continue
                padded = row + [None] * (len(headers) - len(row))
                record = dict(zip(headers, padded))
                for field in date_fields.get(sheet_name, set()):
                    if record.get(field) is not None:
                        record[field] = excel_date(record[field])
                records.append(record)
            result[sheet_name] = records

    modified = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
    return {
        "meta": {
            "source": path.name,
            "modifiedUtc": modified.isoformat(timespec="seconds"),
            "refreshedUtc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        },
        "tables": result,
    }


def company_employee_emails(workbook: dict) -> set[str]:
    return {
        str(row.get("Email", "")).strip().casefold()
        for row in workbook["tables"]["Employees"]
        if row.get("Email")
    }


def is_company_employee_email(email: str, workbook: dict | None = None) -> bool:
    workbook = workbook or parse_workbook(WORKBOOK)
    return email.strip().casefold() in company_employee_emails(workbook)


class DashboardHandler(SimpleHTTPRequestHandler):
    assistant = DashboardAssistant()
    auth_store = AuthStore()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def end_headers(self):
        # Development files must update together. Prevent stale CSS/JS from being
        # combined with newer HTML after watchfiles restarts the server.
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()

    def json_response(
        self,
        payload: dict,
        status: int = 200,
        extra_headers: dict[str, str] | None = None,
    ):
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        for key, value in (extra_headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(encoded)

    def redirect_response(
        self,
        location: str,
        extra_headers: dict[str, str] | None = None,
    ):
        self.send_response(302)
        self.send_header("Location", location)
        for key, value in (extra_headers or {}).items():
            self.send_header(key, value)
        self.end_headers()

    def read_json_body(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0 or length > 1_000_000:
            raise ValueError
        payload = json.loads(self.rfile.read(length).decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError
        return payload

    def session_token(self) -> str | None:
        cookie = SimpleCookie(self.headers.get("Cookie"))
        morsel = cookie.get(SESSION_COOKIE)
        return morsel.value if morsel else None

    def current_user(self):
        return self.auth_store.user_for_session(self.session_token())

    def current_admin(self):
        user = self.current_user()
        return user if user is not None and user.is_admin else None

    def session_cookie_header(self, token: str) -> str:
        secure = "; Secure" if self.headers.get("X-Forwarded-Proto") == "https" else ""
        return (
            f"{SESSION_COOKIE}={token}; Path=/; Max-Age={14 * 24 * 60 * 60}; "
            f"HttpOnly; SameSite=Lax{secure}"
        )

    def clear_session_cookie_header(self) -> str:
        return (
            f"{SESSION_COOKIE}=; Path=/; Max-Age=0; "
            "HttpOnly; SameSite=Lax"
        )

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/api/data":
            try:
                self.json_response(parse_workbook(WORKBOOK))
            except Exception as error:
                self.json_response({"error": str(error)}, 500)
            return
        if path == "/api/auth/google/start":
            self.handle_google_start()
            return
        if path == "/api/auth/google/callback":
            self.handle_google_callback(parsed.query)
            return
        if path == "/api/auth/me":
            user = self.current_user()
            self.json_response({"user": user.public() if user else None})
            return
        if path == "/api/auth/settings":
            user = self.current_user()
            if user is None:
                self.json_response({"error": "Authentication required."}, 401)
                return
            self.json_response({"user": user.public()})
            return
        if path == "/api/admin/data":
            user = self.current_admin()
            if user is None:
                self.json_response({"error": "Admin access required."}, 403)
                return
            workbook = parse_workbook(WORKBOOK)
            self.json_response(
                {
                    "tables": workbook["tables"],
                    "meta": workbook["meta"],
                    "adminTables": ADMIN_TABLES,
                    "requiredFields": {key: sorted(value) for key, value in ADMIN_REQUIRED_FIELDS.items()},
                    "users": self.auth_store.list_users(),
                }
            )
            return
        super().do_GET()

    def google_redirect_uri(self) -> str:
        return os.getenv(
            "GOOGLE_REDIRECT_URI",
            "http://127.0.0.1:8000/api/auth/google/callback",
        )

    def handle_google_start(self):
        client_id = os.getenv("GOOGLE_CLIENT_ID", "").strip()
        if not client_id:
            self.redirect_response("/?google_error=missing_google_client_id")
            return
        state = self.auth_store.create_google_state()
        query = urlencode(
            {
                "client_id": client_id,
                "redirect_uri": self.google_redirect_uri(),
                "response_type": "code",
                "scope": "openid email profile",
                "state": state,
                "access_type": "online",
                "prompt": "select_account",
            }
        )
        self.redirect_response(f"https://accounts.google.com/o/oauth2/v2/auth?{query}")

    def exchange_google_code(self, code: str) -> dict:
        client_id = os.getenv("GOOGLE_CLIENT_ID", "").strip()
        client_secret = os.getenv("GOOGLE_CLIENT_SECRET", "").strip()
        if not client_id or not client_secret:
            raise AuthError("Google sign-in is not configured.")
        body = urlencode(
            {
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": self.google_redirect_uri(),
                "grant_type": "authorization_code",
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            "https://oauth2.googleapis.com/token",
            data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))

    def fetch_google_userinfo(self, access_token: str) -> dict:
        request = urllib.request.Request(
            "https://openidconnect.googleapis.com/v1/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))

    def handle_google_callback(self, query: str):
        params = parse_qs(query)
        if params.get("error"):
            self.redirect_response("/?google_error=access_denied")
            return
        code = params.get("code", [""])[0]
        state = params.get("state", [""])[0]
        try:
            if not code or not state:
                raise AuthError("Google sign-in response was incomplete.")
            self.auth_store.consume_google_state(state)
            token_payload = self.exchange_google_code(code)
            access_token = token_payload.get("access_token")
            if not isinstance(access_token, str):
                raise AuthError("Google did not return an access token.")
            profile = self.fetch_google_userinfo(access_token)
            if not profile.get("email_verified", False):
                raise AuthError("Google email is not verified.")
            google_email = str(profile.get("email", ""))
            if not is_company_employee_email(google_email):
                raise AuthError(EMPLOYEE_SIGNUP_ERROR)
            user = self.auth_store.upsert_google_user(
                str(profile.get("sub", "")),
                google_email,
                str(profile.get("name") or google_email),
                str(profile.get("picture") or "") or None,
            )
            token = self.auth_store.create_session(user.id)
            self.redirect_response(
                "/",
                {"Set-Cookie": self.session_cookie_header(token)},
            )
        except (AuthError, urllib.error.URLError, json.JSONDecodeError) as error:
            print(f"[auth] Google sign-in failure: {error}", flush=True)
            if isinstance(error, AuthError) and str(error) == EMPLOYEE_SIGNUP_ERROR:
                self.redirect_response("/?google_error=employee_only")
            else:
                self.redirect_response("/?google_error=signin_failed")

    def do_POST(self):
        path = urlparse(self.path).path
        if path.startswith("/api/auth/"):
            self.handle_auth_post(path)
            return
        if path.startswith("/api/admin/"):
            self.handle_admin_post(path)
            return
        if path != "/api/chat":
            self.json_response({"error": "Not found"}, 404)
            return
        if self.current_user() is None:
            self.json_response(
                {
                    "error": "authentication_required",
                    "message": (
                        "Welcome! Please sign in to continue and use the "
                        "Dashboard Assistant with your dashboard data."
                    ),
                },
                401,
            )
            return
        try:
            payload = self.read_json_body()
            message = payload.get("message")
            history = payload.get("history", [])
            department = payload.get("department", "All")
            page = payload.get("page", "overview")
            if (
                not isinstance(message, str)
                or not isinstance(history, list)
                or not isinstance(department, str)
                or not isinstance(page, str)
                or department not in {
                    "All",
                    *(
                        row["Department Name"]
                        for row in parse_workbook(WORKBOOK)["tables"]["Departments"]
                    ),
                }
                or page not in {"overview", "delivery", "workforce", "governance"}
                or not all(
                    isinstance(item, dict)
                    and item.get("role") in {"user", "assistant"}
                    and isinstance(item.get("content"), str)
                    for item in history
                )
            ):
                raise ValueError
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
            self.json_response({"error": "Invalid chat request."}, 400)
            return

        try:
            response, status = self.assistant.answer(
                message, history[-8:], parse_workbook(WORKBOOK), department, page
            )
        except GeminiError as error:
            print(
                f"[assistant] Gemini failure [{error.kind}]: {error}",
                flush=True,
            )
            response, status = {
                "error": "gemini_unavailable",
                "message": error.user_message,
            }, 503
        self.json_response(response, status)

    def handle_auth_post(self, path: str):
        try:
            payload = self.read_json_body()
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
            self.json_response({"error": "Invalid auth request."}, 400)
            return

        try:
            if path == "/api/auth/signup":
                email = str(payload.get("email", ""))
                if not is_company_employee_email(email):
                    raise AuthError(EMPLOYEE_SIGNUP_ERROR)
                self.auth_store.begin_signup(
                    str(payload.get("username", "")),
                    email,
                    str(payload.get("displayName", "")),
                    str(payload.get("avatar", "")),
                    str(payload.get("password", "")),
                    str(payload.get("confirmPassword", "")),
                )
                self.json_response(
                    {
                        "otpRequired": True,
                        "email": email,
                        "message": "We sent a verification code to your email.",
                    },
                    200,
                )
                return

            if path == "/api/auth/verify-signup":
                user = self.auth_store.verify_signup_otp(
                    str(payload.get("email", "")),
                    str(payload.get("otp", "")),
                )
                token = self.auth_store.create_session(user.id)
                self.json_response(
                    {"user": user.public()},
                    201,
                    {"Set-Cookie": self.session_cookie_header(token)},
                )
                return

            if path == "/api/auth/login":
                user = self.auth_store.authenticate(
                    str(payload.get("identifier", payload.get("username", ""))),
                    str(payload.get("password", "")),
                )
                token = self.auth_store.create_session(user.id)
                self.json_response(
                    {"user": user.public()},
                    200,
                    {"Set-Cookie": self.session_cookie_header(token)},
                )
                return

            if path == "/api/auth/logout":
                self.auth_store.delete_session(self.session_token())
                self.json_response(
                    {"ok": True},
                    200,
                    {"Set-Cookie": self.clear_session_cookie_header()},
                )
                return

            if path == "/api/auth/forgot-password":
                identifier = str(payload.get("identifier", ""))
                self.auth_store.request_password_reset(identifier)
                self.json_response(
                    {
                        "ok": True,
                        "message": (
                            "If an account matches that username or email, "
                            "a password reset email has been sent."
                        ),
                    }
                )
                return

            if path == "/api/auth/reset-password":
                user = self.auth_store.reset_password(
                    str(payload.get("token", "")),
                    str(payload.get("password", "")),
                    str(payload.get("confirmPassword", "")),
                )
                self.json_response({"user": user.public()})
                return

            if path == "/api/auth/settings/profile":
                user = self.current_user()
                if user is None:
                    self.json_response({"error": "Authentication required."}, 401)
                    return
                email = str(payload.get("email", ""))
                if not is_company_employee_email(email):
                    raise AuthError(EMPLOYEE_SIGNUP_ERROR)
                updated = self.auth_store.update_profile(
                    user.id,
                    str(payload.get("username", "")),
                    email,
                    str(payload.get("avatar", "")),
                )
                self.json_response({"user": updated.public()})
                return

            if path == "/api/auth/settings/password":
                user = self.current_user()
                if user is None:
                    self.json_response({"error": "Authentication required."}, 401)
                    return
                self.auth_store.change_password(
                    user.id,
                    str(payload.get("currentPassword", "")),
                    str(payload.get("password", "")),
                    str(payload.get("confirmPassword", "")),
                )
                self.json_response({"ok": True, "message": "Password updated."})
                return

        except AuthError as error:
            self.json_response({"error": str(error)}, 400)
            return
        except Exception as error:
            print(f"[auth] failure: {error}", flush=True)
            self.json_response({"error": "Authentication service error."}, 500)
            return

    def handle_admin_post(self, path: str):
        user = self.current_admin()
        if user is None:
            self.json_response({"error": "Admin access required."}, 403)
            return
        try:
            payload = self.read_json_body()
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
            self.json_response({"error": "Invalid admin request."}, 400)
            return

        try:
            if path == "/api/admin/record":
                result = apply_record_action(
                    str(payload.get("table", "")),
                    str(payload.get("action", "")),
                    payload.get("record") if isinstance(payload.get("record"), dict) else {},
                )
                workbook = parse_workbook(WORKBOOK)
                self.json_response(
                    {
                        "ok": True,
                        "result": result,
                        "tables": workbook["tables"],
                        "meta": workbook["meta"],
                    }
                )
                return

            if path == "/api/admin/restore-table":
                records = payload.get("records")
                result = restore_table_records(
                    str(payload.get("table", "")),
                    records if isinstance(records, list) else [],
                )
                workbook = parse_workbook(WORKBOOK)
                self.json_response(
                    {
                        "ok": True,
                        "result": result,
                        "tables": workbook["tables"],
                        "meta": workbook["meta"],
                    }
                )
                return

            if path == "/api/admin/set-admin":
                updated = self.auth_store.set_admin(
                    str(payload.get("email", "")),
                    bool(payload.get("isAdmin", True)),
                )
                self.json_response(
                    {
                        "ok": True,
                        "user": updated.public(),
                        "users": self.auth_store.list_users(),
                    }
                )
                return

            self.json_response({"error": "Not found"}, 404)
        except (AdminDataError, AuthError) as error:
            self.json_response({"error": str(error)}, 400)
        except Exception as error:
            print(f"[admin] failure: {error}", flush=True)
            self.json_response({"error": "Admin service error."}, 500)

        self.json_response({"error": "Not found"}, 404)

    def log_message(self, message, *args):
        print(f"[dashboard] {message % args}")


def create_server(
    host: str,
    port: int,
) -> tuple[ThreadingHTTPServer, int]:
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
    print(f"Dashboard running at http://127.0.0.1:{selected_port}")
    print(f"Reading {WORKBOOK}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
    finally:
        server.server_close()
