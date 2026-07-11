"""Local SQLite authentication for the dashboard."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
import hashlib
import hmac
import os
from pathlib import Path
import re
import secrets
import smtplib
import sqlite3
from contextlib import contextmanager
from collections.abc import Iterator

import bcrypt

ROOT = Path(__file__).resolve().parent
DEFAULT_DB = ROOT / "dashboard_auth.sqlite3"
SESSION_COOKIE = "dashboard_session"
USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{3,32}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
AVATAR_RE = re.compile(r"^avatar-(finance|it|cyber|data|marketing|customer|legal|procurement|hr|operations|training|executive)$")
USERNAME_SAFE_RE = re.compile(r"[^A-Za-z0-9_.-]+")
SESSION_DAYS = 14
RESET_MINUTES = 30
SIGNUP_OTP_MINUTES = 10
OAUTH_STATE_MINUTES = 10
DEFAULT_AVATAR = "avatar-executive"
DEFAULT_ADMIN_EMAILS = {"swaheeb0001@stu.kau.edu.sa"}


class AuthError(ValueError):
    """Validation or authentication failure safe to show to users."""


@dataclass(frozen=True)
class User:
    id: int
    username: str
    email: str
    display_name: str
    avatar: str
    created_at: str | None = None
    last_login_at: str | None = None
    is_admin: bool = False

    def public(self) -> dict[str, object]:
        return {
            "id": self.id,
            "username": self.username,
            "email": self.email,
            "displayName": self.display_name,
            "avatar": self.avatar,
            "dateJoined": self.created_at,
            "lastLogin": self.last_login_at,
            "isAdmin": self.is_admin,
        }


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat(timespec="seconds")


def parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def normalize_username(username: str) -> str:
    username = username.strip()
    if not USERNAME_RE.fullmatch(username):
        raise AuthError(
            "Username must be 3-32 characters and use only letters, numbers, dots, dashes, or underscores."
        )
    return username


def normalize_email(email: str) -> str:
    email = email.strip().casefold()
    if not EMAIL_RE.fullmatch(email):
        raise AuthError("Enter a valid email address.")
    return email


def normalize_display_name(display_name: str) -> str:
    display_name = " ".join(display_name.strip().split())
    if not 2 <= len(display_name) <= 80:
        raise AuthError("Name must be 2-80 characters.")
    return display_name


def normalize_google_display_name(display_name: str, email: str) -> str:
    try:
        return normalize_display_name(display_name)
    except AuthError:
        fallback = email.split("@", 1)[0].replace(".", " ").replace("_", " ").replace("-", " ")
        fallback = " ".join(fallback.split()) or "Google User"
        if len(fallback) == 1:
            fallback = f"{fallback} user"
        return normalize_display_name(fallback[:80])


def normalize_avatar(avatar: str | None) -> str:
    avatar = (avatar or DEFAULT_AVATAR).strip()
    if not AVATAR_RE.fullmatch(avatar):
        raise AuthError("Choose a valid avatar.")
    return avatar


def validate_password_pair(password: str, confirm_password: str | None = None) -> None:
    if len(password) < 8:
        raise AuthError("Password must be at least 8 characters.")
    if confirm_password is not None and password != confirm_password:
        raise AuthError("Passwords do not match.")


def user_from_row(row: sqlite3.Row) -> User:
    keys = set(row.keys())
    email = row["email"]
    return User(
        int(row["id"]),
        row["username"],
        email,
        row["display_name"] or row["username"],
        row["avatar_url"] or row["avatar"] or DEFAULT_AVATAR,
        row["created_at"] if "created_at" in keys else None,
        row["last_login_at"] if "last_login_at" in keys else None,
        bool(row["is_admin"]) if "is_admin" in keys else email.casefold() in DEFAULT_ADMIN_EMAILS,
    )


class AuthStore:
    def __init__(self, db_path: Path = DEFAULT_DB) -> None:
        self.db_path = Path(db_path)
        self.init_db()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def init_db(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL UNIQUE COLLATE NOCASE,
                    email TEXT NOT NULL UNIQUE COLLATE NOCASE,
                    display_name TEXT NOT NULL DEFAULT '',
                    avatar TEXT NOT NULL DEFAULT 'avatar-executive',
                    avatar_url TEXT,
                    google_sub TEXT UNIQUE,
                    auth_provider TEXT NOT NULL DEFAULT 'local',
                    password_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    last_login_at TEXT,
                    is_admin INTEGER NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    token_hash TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS password_resets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    token_hash TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    used_at TEXT
                );

                CREATE TABLE IF NOT EXISTS signup_otps (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL COLLATE NOCASE,
                    email TEXT NOT NULL COLLATE NOCASE,
                    display_name TEXT NOT NULL,
                    avatar TEXT NOT NULL,
                    password_hash TEXT NOT NULL,
                    otp_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS oauth_states (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    state_hash TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL
                );
                """
            )
            columns = {
                row["name"]
                for row in db.execute("PRAGMA table_info(users)").fetchall()
            }
            if "display_name" not in columns:
                db.execute(
                    "ALTER TABLE users ADD COLUMN display_name TEXT NOT NULL DEFAULT ''"
                )
            if "avatar" not in columns:
                db.execute(
                    "ALTER TABLE users ADD COLUMN avatar TEXT NOT NULL DEFAULT 'avatar-executive'"
                )
            if "avatar_url" not in columns:
                db.execute("ALTER TABLE users ADD COLUMN avatar_url TEXT")
            if "google_sub" not in columns:
                db.execute("ALTER TABLE users ADD COLUMN google_sub TEXT")
            if "auth_provider" not in columns:
                db.execute(
                    "ALTER TABLE users ADD COLUMN auth_provider TEXT NOT NULL DEFAULT 'local'"
                )
            if "last_login_at" not in columns:
                db.execute("ALTER TABLE users ADD COLUMN last_login_at TEXT")
            if "is_admin" not in columns:
                db.execute("ALTER TABLE users ADD COLUMN is_admin INTEGER NOT NULL DEFAULT 0")
            for email in DEFAULT_ADMIN_EMAILS:
                db.execute(
                    "UPDATE users SET is_admin = 1 WHERE email = ? COLLATE NOCASE",
                    (email,),
                )
            db.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_users_google_sub
                ON users(google_sub)
                WHERE google_sub IS NOT NULL
                """
            )
            pending_columns = {
                row["name"]
                for row in db.execute("PRAGMA table_info(signup_otps)").fetchall()
            }
            if "display_name" not in pending_columns:
                db.execute(
                    "ALTER TABLE signup_otps ADD COLUMN display_name TEXT NOT NULL DEFAULT ''"
                )
            if "avatar" not in pending_columns:
                db.execute(
                    "ALTER TABLE signup_otps ADD COLUMN avatar TEXT NOT NULL DEFAULT 'avatar-executive'"
                )

    def ensure_unique_signup(self, db: sqlite3.Connection, username: str, email: str) -> None:
        existing = db.execute(
            """
            SELECT username, email
            FROM users
            WHERE username = ? COLLATE NOCASE OR email = ? COLLATE NOCASE
            """,
            (username, email),
        ).fetchone()
        if existing is not None:
            if existing["username"].casefold() == username.casefold():
                raise AuthError("Username already exists.")
            raise AuthError("Email already exists.")

    def begin_signup(
        self,
        username: str,
        email: str,
        display_name: str,
        avatar: str | None,
        password: str,
        confirm_password: str,
    ) -> None:
        username = normalize_username(username)
        email = normalize_email(email)
        display_name = normalize_display_name(display_name)
        avatar = normalize_avatar(avatar)
        validate_password_pair(password, confirm_password)
        password_hash = hash_password(password)
        otp = f"{secrets.randbelow(1_000_000):06d}"
        now = utc_now()
        with self.connect() as db:
            self.ensure_unique_signup(db, username, email)
            db.execute(
                """
                DELETE FROM signup_otps
                WHERE username = ? COLLATE NOCASE OR email = ? COLLATE NOCASE
                """,
                (username, email),
            )
            db.execute(
                """
                INSERT INTO signup_otps
                    (username, email, display_name, avatar, password_hash,
                     otp_hash, created_at, expires_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    username,
                    email,
                    display_name,
                    avatar,
                    password_hash,
                    hash_token(otp),
                    iso(now),
                    iso(now + timedelta(minutes=SIGNUP_OTP_MINUTES)),
                ),
            )
        self.send_signup_otp_email(email, username, otp)

    def create_user(
        self,
        username: str,
        email: str,
        password: str,
        confirm_password: str,
        display_name: str = "",
        avatar: str | None = None,
    ) -> User:
        username = normalize_username(username)
        email = normalize_email(email)
        display_name = normalize_display_name(display_name or username)
        avatar = normalize_avatar(avatar)
        validate_password_pair(password, confirm_password)
        password_hash = hash_password(password)
        created_at = iso(utc_now())
        with self.connect() as db:
            self.ensure_unique_signup(db, username, email)
            cursor = db.execute(
                """
                INSERT INTO users
                    (username, email, display_name, avatar, password_hash, created_at, is_admin)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    username,
                    email,
                    display_name,
                    avatar,
                    password_hash,
                    created_at,
                    int(email.casefold() in DEFAULT_ADMIN_EMAILS),
                ),
            )
            user_id = int(cursor.lastrowid)
        return User(
            user_id,
            username,
            email,
            display_name,
            avatar,
            created_at,
            None,
            email.casefold() in DEFAULT_ADMIN_EMAILS,
        )

    def create_google_state(self) -> str:
        state = secrets.token_urlsafe(32)
        now = utc_now()
        with self.connect() as db:
            db.execute(
                "DELETE FROM oauth_states WHERE expires_at <= ?",
                (iso(now),),
            )
            db.execute(
                """
                INSERT INTO oauth_states (state_hash, created_at, expires_at)
                VALUES (?, ?, ?)
                """,
                (
                    hash_token(state),
                    iso(now),
                    iso(now + timedelta(minutes=OAUTH_STATE_MINUTES)),
                ),
            )
        return state

    def consume_google_state(self, state: str) -> None:
        digest = hash_token(state.strip())
        now = utc_now()
        with self.connect() as db:
            row = db.execute(
                "SELECT id, expires_at FROM oauth_states WHERE state_hash = ?",
                (digest,),
            ).fetchone()
            if row is None or parse_iso(row["expires_at"]) <= now:
                raise AuthError("Google sign-in session expired. Please try again.")
            db.execute("DELETE FROM oauth_states WHERE id = ?", (int(row["id"]),))

    def google_username(self, email: str, db: sqlite3.Connection) -> str:
        base = USERNAME_SAFE_RE.sub("", email.split("@", 1)[0])[:24] or "googleuser"
        candidate = base
        suffix = 1
        while db.execute(
            "SELECT 1 FROM users WHERE username = ? COLLATE NOCASE",
            (candidate,),
        ).fetchone():
            suffix += 1
            candidate = f"{base[:24 - len(str(suffix))]}{suffix}"
        return candidate

    def upsert_google_user(
        self,
        google_sub: str,
        email: str,
        display_name: str,
        avatar_url: str | None,
    ) -> User:
        email = normalize_email(email)
        display_name = normalize_google_display_name(display_name, email)
        google_sub = google_sub.strip()
        if not google_sub:
            raise AuthError("Google account identifier is missing.")
        with self.connect() as db:
            row = db.execute(
                """
                SELECT id, username, email, display_name, avatar, avatar_url,
                       created_at, last_login_at, is_admin
                FROM users
                WHERE google_sub = ? OR email = ? COLLATE NOCASE
                """,
                (google_sub, email),
            ).fetchone()
            if row is not None:
                db.execute(
                    """
                    UPDATE users
                    SET google_sub = ?, display_name = ?, avatar_url = ?,
                        auth_provider = CASE
                            WHEN auth_provider = 'local' THEN 'local_google'
                            ELSE auth_provider
                        END
                    WHERE id = ?
                    """,
                    (google_sub, display_name, avatar_url, int(row["id"])),
                )
                updated = db.execute(
                    """
                    SELECT id, username, email, display_name, avatar, avatar_url,
                           created_at, last_login_at, is_admin
                    FROM users
                    WHERE id = ?
                    """,
                    (int(row["id"]),),
                ).fetchone()
                return user_from_row(updated)

            username = self.google_username(email, db)
            password_hash = hash_password(secrets.token_urlsafe(32))
            created_at = iso(utc_now())
            cursor = db.execute(
                """
                INSERT INTO users
                    (username, email, display_name, avatar, avatar_url,
                     google_sub, auth_provider, password_hash, created_at, is_admin)
                VALUES (?, ?, ?, ?, ?, ?, 'google', ?, ?, ?)
                """,
                (
                    username,
                    email,
                    display_name,
                    DEFAULT_AVATAR,
                    avatar_url,
                    google_sub,
                    password_hash,
                    created_at,
                    int(email.casefold() in DEFAULT_ADMIN_EMAILS),
                ),
            )
            user_id = int(cursor.lastrowid)
        return User(
            user_id,
            username,
            email,
            display_name,
            avatar_url or DEFAULT_AVATAR,
            created_at,
            None,
            email.casefold() in DEFAULT_ADMIN_EMAILS,
        )

    def verify_signup_otp(self, email: str, otp: str) -> User:
        email = normalize_email(email)
        digest = hash_token(otp.strip())
        now = utc_now()
        with self.connect() as db:
            pending = db.execute(
                """
                SELECT id, username, email, display_name, avatar, password_hash,
                       otp_hash, expires_at
                FROM signup_otps
                WHERE email = ? COLLATE NOCASE
                ORDER BY id DESC
                LIMIT 1
                """,
                (email,),
            ).fetchone()
            if pending is None or parse_iso(pending["expires_at"]) <= now:
                raise AuthError("Signup code is invalid or expired.")
            if not secure_compare(pending["otp_hash"], digest):
                raise AuthError("Signup code is invalid or expired.")
            self.ensure_unique_signup(db, pending["username"], pending["email"])
            created_at = iso(now)
            cursor = db.execute(
                """
                INSERT INTO users
                    (username, email, display_name, avatar, password_hash, created_at, is_admin)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    pending["username"],
                    pending["email"],
                    pending["display_name"],
                    pending["avatar"],
                    pending["password_hash"],
                    created_at,
                    int(str(pending["email"]).casefold() in DEFAULT_ADMIN_EMAILS),
                ),
            )
            user_id = int(cursor.lastrowid)
            db.execute("DELETE FROM signup_otps WHERE email = ? COLLATE NOCASE", (email,))
        return User(
            user_id,
            pending["username"],
            pending["email"],
            pending["display_name"],
            pending["avatar"],
            created_at,
            None,
            str(pending["email"]).casefold() in DEFAULT_ADMIN_EMAILS,
        )

    def authenticate(self, identifier: str, password: str) -> User:
        identifier = identifier.strip()
        with self.connect() as db:
            row = db.execute(
                """
                SELECT id, username, email, display_name, avatar, avatar_url,
                       password_hash, created_at, last_login_at, is_admin
                FROM users
                WHERE username = ? COLLATE NOCASE OR email = ? COLLATE NOCASE
                """,
                (identifier, identifier),
            ).fetchone()
        if row is None or not verify_password(password, row["password_hash"]):
            raise AuthError("Invalid username/email or password.")
        return user_from_row(row)

    def create_session(self, user_id: int) -> str:
        token = secrets.token_urlsafe(32)
        now = utc_now()
        with self.connect() as db:
            db.execute(
                "UPDATE users SET last_login_at = ? WHERE id = ?",
                (iso(now), user_id),
            )
            db.execute(
                """
                INSERT INTO sessions (user_id, token_hash, created_at, expires_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    user_id,
                    hash_token(token),
                    iso(now),
                    iso(now + timedelta(days=SESSION_DAYS)),
                ),
            )
        return token

    def user_for_session(self, token: str | None) -> User | None:
        if not token:
            return None
        digest = hash_token(token)
        now = utc_now()
        with self.connect() as db:
            row = db.execute(
                """
                SELECT users.id, users.username, users.email, users.display_name,
                       users.avatar, users.avatar_url, users.created_at,
                       users.last_login_at, users.is_admin, sessions.expires_at
                FROM sessions
                JOIN users ON users.id = sessions.user_id
                WHERE sessions.token_hash = ?
                """,
                (digest,),
            ).fetchone()
            if row is None:
                return None
            if parse_iso(row["expires_at"]) <= now:
                db.execute("DELETE FROM sessions WHERE token_hash = ?", (digest,))
                return None
        return user_from_row(row)

    def delete_session(self, token: str | None) -> None:
        if not token:
            return
        with self.connect() as db:
            db.execute("DELETE FROM sessions WHERE token_hash = ?", (hash_token(token),))

    def request_password_reset(self, identifier: str) -> bool:
        identifier = identifier.strip()
        with self.connect() as db:
            row = db.execute(
                """
                SELECT id, username, email
                FROM users
                WHERE username = ? COLLATE NOCASE OR email = ? COLLATE NOCASE
                """,
                (identifier, identifier),
            ).fetchone()
            if row is None:
                return False
            token = secrets.token_urlsafe(32)
            now = utc_now()
            db.execute(
                """
                INSERT INTO password_resets
                    (user_id, token_hash, created_at, expires_at, used_at)
                VALUES (?, ?, ?, ?, NULL)
                """,
                (
                    int(row["id"]),
                    hash_token(token),
                    iso(now),
                    iso(now + timedelta(minutes=RESET_MINUTES)),
                ),
            )
        self.send_password_reset_email(row["email"], row["username"], token)
        return True

    def reset_password(
        self,
        token: str,
        password: str,
        confirm_password: str,
    ) -> User:
        validate_password_pair(password, confirm_password)
        digest = hash_token(token.strip())
        now = utc_now()
        with self.connect() as db:
            row = db.execute(
                """
                SELECT password_resets.id, password_resets.user_id,
                       password_resets.expires_at, password_resets.used_at,
                       users.username, users.email, users.display_name, users.avatar,
                       users.avatar_url, users.created_at, users.last_login_at,
                       users.is_admin
                FROM password_resets
                JOIN users ON users.id = password_resets.user_id
                WHERE password_resets.token_hash = ?
                """,
                (digest,),
            ).fetchone()
            if row is None or row["used_at"] is not None or parse_iso(row["expires_at"]) <= now:
                raise AuthError("Password reset link is invalid or expired.")
            db.execute(
                "UPDATE users SET password_hash = ? WHERE id = ?",
                (hash_password(password), int(row["user_id"])),
            )
            db.execute(
                "UPDATE password_resets SET used_at = ? WHERE id = ?",
                (iso(now), int(row["id"])),
            )
            db.execute("DELETE FROM sessions WHERE user_id = ?", (int(row["user_id"]),))
        return User(
            int(row["user_id"]),
            row["username"],
            row["email"],
            row["display_name"] or row["username"],
            row["avatar_url"] or row["avatar"] or DEFAULT_AVATAR,
            row["created_at"],
            row["last_login_at"],
            bool(row["is_admin"]),
        )

    def get_user(self, user_id: int) -> User | None:
        with self.connect() as db:
            row = db.execute(
                """
                SELECT id, username, email, display_name, avatar, avatar_url,
                       created_at, last_login_at, is_admin
                FROM users
                WHERE id = ?
                """,
                (user_id,),
            ).fetchone()
        return user_from_row(row) if row is not None else None

    def update_profile(
        self,
        user_id: int,
        username: str,
        email: str,
        avatar: str | None,
    ) -> User:
        username = normalize_username(username)
        email = normalize_email(email)
        avatar = normalize_avatar(avatar)
        with self.connect() as db:
            existing = db.execute(
                """
                SELECT username, email
                FROM users
                WHERE id != ?
                  AND (username = ? COLLATE NOCASE OR email = ? COLLATE NOCASE)
                """,
                (user_id, username, email),
            ).fetchone()
            if existing is not None:
                if existing["username"].casefold() == username.casefold():
                    raise AuthError("Username already exists.")
                raise AuthError("Email already exists.")
            db.execute(
                """
                UPDATE users
                SET username = ?, email = ?, display_name = ?, avatar = ?,
                    avatar_url = NULL
                WHERE id = ?
                """,
                (username, email, username, avatar, user_id),
            )
            row = db.execute(
                """
                SELECT id, username, email, display_name, avatar, avatar_url,
                       created_at, last_login_at, is_admin
                FROM users
                WHERE id = ?
                """,
                (user_id,),
            ).fetchone()
        if row is None:
            raise AuthError("Account not found.")
        return user_from_row(row)

    def list_users(self) -> list[dict[str, object]]:
        with self.connect() as db:
            rows = db.execute(
                """
                SELECT id, username, email, display_name, avatar, avatar_url,
                       created_at, last_login_at, is_admin
                FROM users
                ORDER BY is_admin DESC, username COLLATE NOCASE
                """
            ).fetchall()
        return [user_from_row(row).public() for row in rows]

    def set_admin(self, email: str, is_admin: bool) -> User:
        email = normalize_email(email)
        with self.connect() as db:
            row = db.execute(
                """
                SELECT id
                FROM users
                WHERE email = ? COLLATE NOCASE
                """,
                (email,),
            ).fetchone()
            if row is None:
                raise AuthError("User account not found.")
            db.execute(
                "UPDATE users SET is_admin = ? WHERE id = ?",
                (1 if is_admin else 0, int(row["id"])),
            )
            updated = db.execute(
                """
                SELECT id, username, email, display_name, avatar, avatar_url,
                       created_at, last_login_at, is_admin
                FROM users
                WHERE id = ?
                """,
                (int(row["id"]),),
            ).fetchone()
        return user_from_row(updated)

    def change_password(
        self,
        user_id: int,
        current_password: str,
        password: str,
        confirm_password: str,
    ) -> None:
        validate_password_pair(password, confirm_password)
        with self.connect() as db:
            row = db.execute(
                """
                SELECT auth_provider, password_hash
                FROM users
                WHERE id = ?
                """,
                (user_id,),
            ).fetchone()
            if row is None:
                raise AuthError("Account not found.")
            if row["auth_provider"] == "google":
                raise AuthError("Password changes are only available for local password accounts.")
            if not verify_password(current_password, row["password_hash"]):
                raise AuthError("Current password is incorrect.")
            db.execute(
                "UPDATE users SET password_hash = ? WHERE id = ?",
                (hash_password(password), user_id),
            )

    def send_password_reset_email(self, email: str, username: str, token: str) -> None:
        sender = os.getenv("GMAIL_USER", "").strip()
        app_password = os.getenv("GMAIL_APP_PASSWORD", "").strip()
        base_url = os.getenv("PASSWORD_RESET_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
        reset_link = f"{base_url}/?reset_token={token}"

        if not sender or not app_password:
            print(
                "[auth] Gmail reset email is not configured. "
                f"Password reset link for {username}: {reset_link}",
                flush=True,
            )
            return

        message = EmailMessage()
        message["Subject"] = "Dashboard password reset"
        message["From"] = sender
        message["To"] = email
        message.set_content(
            "\n".join(
                [
                    f"Hello {username},",
                    "",
                    "Use this link to reset your dashboard password:",
                    reset_link,
                    "",
                    f"This link expires in {RESET_MINUTES} minutes.",
                ]
            )
        )
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=20) as smtp:
            smtp.login(sender, app_password)
            smtp.send_message(message)

    def send_signup_otp_email(self, email: str, username: str, otp: str) -> None:
        sender = os.getenv("GMAIL_USER", "").strip()
        app_password = os.getenv("GMAIL_APP_PASSWORD", "").strip()

        if not sender or not app_password:
            print(
                "[auth] Gmail signup OTP is not configured. "
                f"Signup OTP for {username}: {otp}",
                flush=True,
            )
            return

        message = EmailMessage()
        message["Subject"] = "Dashboard signup verification code"
        message["From"] = sender
        message["To"] = email
        message.set_content(
            "\n".join(
                [
                    f"Hello {username},",
                    "",
                    f"Your dashboard signup verification code is: {otp}",
                    "",
                    f"This code expires in {SIGNUP_OTP_MINUTES} minutes.",
                ]
            )
        )
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=20) as smtp:
            smtp.login(sender, app_password)
            smtp.send_message(message)


def secure_compare(left: str, right: str) -> bool:
    return hmac.compare_digest(left.encode("utf-8"), right.encode("utf-8"))
