"""Shared dashboard API routing for local HTTP and Vercel functions."""

from __future__ import annotations

from dataclasses import dataclass, field
from http.cookies import SimpleCookie
import json
from urllib.parse import parse_qs, urlencode
import urllib.error

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
from server_data import EMPLOYEE_SIGNUP_ERROR, is_company_employee_email, parse_workbook

ensure_runtime_files()


@dataclass
class ApiResponse:
    status: int = 200
    payload: dict | None = None
    headers: dict[str, str] = field(default_factory=dict)
    redirect: str | None = None


class DashboardAPI:
    def __init__(self) -> None:
        self.assistant = DashboardAssistant()
        self.auth_store = AuthStore()

    def log(self, message: str) -> None:
        print(f"[api] {message}", flush=True)

    def session_token(self, headers: dict[str, str]) -> str | None:
        cookie = SimpleCookie(headers.get("cookie") or headers.get("Cookie"))
        morsel = cookie.get(SESSION_COOKIE)
        return morsel.value if morsel else None

    def current_user(self, headers: dict[str, str]):
        return self.auth_store.user_for_session(self.session_token(headers))

    def current_admin(self, headers: dict[str, str]):
        user = self.current_user(headers)
        return user if user is not None and user.is_admin else None

    def session_cookie_header(self, headers: dict[str, str], token: str) -> str:
        proto = headers.get("x-forwarded-proto") or headers.get("X-Forwarded-Proto")
        secure = "; Secure" if proto == "https" else ""
        return (
            f"{SESSION_COOKIE}={token}; Path=/; Max-Age={14 * 24 * 60 * 60}; "
            f"HttpOnly; SameSite=Lax{secure}"
        )

    def clear_session_cookie_header(self) -> str:
        return f"{SESSION_COOKIE}=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax"

    def google_redirect_uri(self) -> str:
        import os

        return os.getenv(
            "GOOGLE_REDIRECT_URI",
            "http://127.0.0.1:8000/api/auth/google/callback",
        )

    def handle_get(self, path: str, query: str, headers: dict[str, str]) -> ApiResponse:
        self.log(f"GET {path}")
        if path == "/api/data":
            try:
                return ApiResponse(payload=parse_workbook(CLEANED_WORKBOOK))
            except Exception as error:
                self.log(f"data failure: {error}")
                return ApiResponse(500, {"error": str(error)})

        if path == "/api/auth/google/start":
            return self.handle_google_start()

        if path == "/api/auth/google/callback":
            return self.handle_google_callback(query, headers)

        if path == "/api/auth/me":
            user = self.current_user(headers)
            return ApiResponse(payload={"user": user.public() if user else None})

        if path == "/api/auth/settings":
            user = self.current_user(headers)
            if user is None:
                return ApiResponse(401, {"error": "Authentication required."})
            return ApiResponse(payload={"user": user.public()})

        if path == "/api/admin/data":
            user = self.current_admin(headers)
            if user is None:
                return ApiResponse(403, {"error": "Admin access required."})
            workbook = parse_workbook(CLEANED_WORKBOOK)
            return ApiResponse(
                payload={
                    "tables": workbook["tables"],
                    "meta": workbook["meta"],
                    "adminTables": ADMIN_TABLES,
                    "requiredFields": {
                        key: sorted(value)
                        for key, value in ADMIN_REQUIRED_FIELDS.items()
                    },
                    "users": self.auth_store.list_users(),
                }
            )

        return ApiResponse(404, {"error": "Not found"})

    def handle_google_start(self) -> ApiResponse:
        import os

        client_id = os.getenv("GOOGLE_CLIENT_ID", "").strip()
        if not client_id:
            return ApiResponse(302, redirect="/?google_error=missing_google_client_id")
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
        return ApiResponse(
            302,
            redirect=f"https://accounts.google.com/o/oauth2/v2/auth?{query}",
        )

    def exchange_google_code(self, code: str) -> dict:
        import os
        import urllib.request

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
        import urllib.request

        request = urllib.request.Request(
            "https://openidconnect.googleapis.com/v1/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))

    def handle_google_callback(self, query: str, headers: dict[str, str]) -> ApiResponse:
        params = parse_qs(query)
        if params.get("error"):
            return ApiResponse(302, redirect="/?google_error=access_denied")
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
            return ApiResponse(
                302,
                headers={"Set-Cookie": self.session_cookie_header(headers, token)},
                redirect="/",
            )
        except (AuthError, urllib.error.URLError, json.JSONDecodeError) as error:
            self.log(f"Google sign-in failure: {error}")
            if isinstance(error, AuthError) and str(error) == EMPLOYEE_SIGNUP_ERROR:
                return ApiResponse(302, redirect="/?google_error=employee_only")
            return ApiResponse(302, redirect="/?google_error=signin_failed")

    def handle_post(
        self,
        path: str,
        payload: dict,
        headers: dict[str, str],
    ) -> ApiResponse:
        self.log(f"POST {path}")
        if path.startswith("/api/auth/"):
            return self.handle_auth_post(path, payload, headers)
        if path.startswith("/api/admin/"):
            return self.handle_admin_post(path, payload, headers)
        if path == "/api/chat":
            return self.handle_chat(payload, headers)
        return ApiResponse(404, {"error": "Not found"})

    def handle_chat(self, payload: dict, headers: dict[str, str]) -> ApiResponse:
        if self.current_user(headers) is None:
            return ApiResponse(
                401,
                {
                    "error": "authentication_required",
                    "message": (
                        "Welcome! Please sign in to continue and use the "
                        "Dashboard Assistant with your dashboard data."
                    ),
                },
            )
        try:
            message = payload.get("message")
            history = payload.get("history", [])
            department = payload.get("department", "All")
            page = payload.get("page", "overview")
            departments = {
                "All",
                *(
                    row["Department Name"]
                    for row in parse_workbook(CLEANED_WORKBOOK)["tables"]["Departments"]
                ),
            }
            if (
                not isinstance(message, str)
                or not isinstance(history, list)
                or not isinstance(department, str)
                or not isinstance(page, str)
                or department not in departments
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
            return ApiResponse(400, {"error": "Invalid chat request."})

        try:
            response, status = self.assistant.answer(
                message,
                history[-8:],
                parse_workbook(CLEANED_WORKBOOK),
                department,
                page,
            )
        except GeminiError as error:
            self.log(f"Gemini failure [{error.kind}]: {error}")
            response, status = {
                "error": "gemini_unavailable",
                "message": error.user_message,
            }, 503
        return ApiResponse(status, response)

    def handle_auth_post(
        self,
        path: str,
        payload: dict,
        headers: dict[str, str],
    ) -> ApiResponse:
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
                return ApiResponse(
                    payload={
                        "otpRequired": True,
                        "email": email,
                        "message": "We sent a verification code to your email.",
                    }
                )

            if path == "/api/auth/verify-signup":
                user = self.auth_store.verify_signup_otp(
                    str(payload.get("email", "")),
                    str(payload.get("otp", "")),
                )
                token = self.auth_store.create_session(user.id)
                return ApiResponse(
                    201,
                    {"user": user.public()},
                    {"Set-Cookie": self.session_cookie_header(headers, token)},
                )

            if path == "/api/auth/login":
                user = self.auth_store.authenticate(
                    str(payload.get("identifier", payload.get("username", ""))),
                    str(payload.get("password", "")),
                )
                token = self.auth_store.create_session(user.id)
                return ApiResponse(
                    payload={"user": user.public()},
                    headers={"Set-Cookie": self.session_cookie_header(headers, token)},
                )

            if path == "/api/auth/logout":
                self.auth_store.delete_session(self.session_token(headers))
                return ApiResponse(
                    payload={"ok": True},
                    headers={"Set-Cookie": self.clear_session_cookie_header()},
                )

            if path == "/api/auth/forgot-password":
                self.auth_store.request_password_reset(str(payload.get("identifier", "")))
                return ApiResponse(
                    payload={
                        "ok": True,
                        "message": (
                            "If an account matches that username or email, "
                            "a password reset email has been sent."
                        ),
                    }
                )

            if path == "/api/auth/reset-password":
                user = self.auth_store.reset_password(
                    str(payload.get("token", "")),
                    str(payload.get("password", "")),
                    str(payload.get("confirmPassword", "")),
                )
                return ApiResponse(payload={"user": user.public()})

            if path == "/api/auth/settings/profile":
                user = self.current_user(headers)
                if user is None:
                    return ApiResponse(401, {"error": "Authentication required."})
                email = str(payload.get("email", ""))
                if not is_company_employee_email(email):
                    raise AuthError(EMPLOYEE_SIGNUP_ERROR)
                updated = self.auth_store.update_profile(
                    user.id,
                    str(payload.get("username", "")),
                    email,
                    str(payload.get("avatar", "")),
                )
                return ApiResponse(payload={"user": updated.public()})

            if path == "/api/auth/settings/password":
                user = self.current_user(headers)
                if user is None:
                    return ApiResponse(401, {"error": "Authentication required."})
                self.auth_store.change_password(
                    user.id,
                    str(payload.get("currentPassword", "")),
                    str(payload.get("password", "")),
                    str(payload.get("confirmPassword", "")),
                )
                return ApiResponse(payload={"ok": True, "message": "Password updated."})

            return ApiResponse(404, {"error": "Not found"})
        except AuthError as error:
            return ApiResponse(400, {"error": str(error)})
        except Exception as error:
            self.log(f"auth failure: {error}")
            return ApiResponse(500, {"error": "Authentication service error."})

    def handle_admin_post(
        self,
        path: str,
        payload: dict,
        headers: dict[str, str],
    ) -> ApiResponse:
        user = self.current_admin(headers)
        if user is None:
            return ApiResponse(403, {"error": "Admin access required."})
        try:
            if path == "/api/admin/record":
                result = apply_record_action(
                    str(payload.get("table", "")),
                    str(payload.get("action", "")),
                    payload.get("record") if isinstance(payload.get("record"), dict) else {},
                )
                workbook = parse_workbook(CLEANED_WORKBOOK)
                return ApiResponse(
                    payload={
                        "ok": True,
                        "result": result,
                        "tables": workbook["tables"],
                        "meta": workbook["meta"],
                    }
                )

            if path == "/api/admin/restore-table":
                records = payload.get("records")
                result = restore_table_records(
                    str(payload.get("table", "")),
                    records if isinstance(records, list) else [],
                )
                workbook = parse_workbook(CLEANED_WORKBOOK)
                return ApiResponse(
                    payload={
                        "ok": True,
                        "result": result,
                        "tables": workbook["tables"],
                        "meta": workbook["meta"],
                    }
                )

            if path == "/api/admin/set-admin":
                updated = self.auth_store.set_admin(
                    str(payload.get("email", "")),
                    bool(payload.get("isAdmin", True)),
                )
                return ApiResponse(
                    payload={
                        "ok": True,
                        "user": updated.public(),
                        "users": self.auth_store.list_users(),
                    }
                )

            return ApiResponse(404, {"error": "Not found"})
        except (AdminDataError, AuthError) as error:
            return ApiResponse(400, {"error": str(error)})
        except Exception as error:
            self.log(f"admin failure: {error}")
            return ApiResponse(500, {"error": "Admin service error."})
