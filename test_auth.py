from __future__ import annotations

import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from auth import AuthError, AuthStore, verify_password


class CapturingAuthStore(AuthStore):
    def __init__(self, db_path: Path) -> None:
        self.reset_emails: list[tuple[str, str, str]] = []
        self.signup_otps: list[tuple[str, str, str]] = []
        super().__init__(db_path)

    def send_password_reset_email(self, email: str, username: str, token: str) -> None:
        self.reset_emails.append((email, username, token))

    def send_signup_otp_email(self, email: str, username: str, otp: str) -> None:
        self.signup_otps.append((email, username, otp))


class AuthStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "auth.sqlite3"
        self.store = CapturingAuthStore(self.db_path)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def password_hash_for(self, username: str) -> str:
        with closing(sqlite3.connect(self.db_path)) as db:
            row = db.execute(
                "SELECT password_hash FROM users WHERE username = ?",
                (username,),
            ).fetchone()
        return row[0]

    def test_signup_hashes_password_and_prevents_duplicate_username(self) -> None:
        user = self.store.create_user(
            "shimaa",
            "shimaa@example.com",
            "StrongPass123",
            "StrongPass123",
            "Shimaa Waheep",
            "avatar-finance",
        )
        self.assertEqual(user.username, "shimaa")
        self.assertEqual(user.display_name, "Shimaa Waheep")
        self.assertEqual(user.avatar, "avatar-finance")

        stored_hash = self.password_hash_for("shimaa")
        self.assertNotEqual(stored_hash, "StrongPass123")
        self.assertTrue(stored_hash.startswith("$2"))
        self.assertTrue(verify_password("StrongPass123", stored_hash))

        with self.assertRaisesRegex(AuthError, "Username already exists"):
            self.store.create_user(
                "SHIMAA",
                "other@example.com",
                "StrongPass123",
                "StrongPass123",
                "Other User",
                "avatar-it",
            )

    def test_login_session_lookup_and_logout(self) -> None:
        user = self.store.create_user(
            "analyst",
            "analyst@example.com",
            "StrongPass123",
            "StrongPass123",
            "Data Analyst",
            "avatar-data",
        )
        logged_in = self.store.authenticate("analyst", "StrongPass123")
        self.assertEqual(logged_in.id, user.id)
        email_login = self.store.authenticate("analyst@example.com", "StrongPass123")
        self.assertEqual(email_login.id, user.id)

        with self.assertRaisesRegex(AuthError, "Invalid username/email or password"):
            self.store.authenticate("analyst", "wrong-password")

        token = self.store.create_session(user.id)
        session_user = self.store.user_for_session(token)
        self.assertEqual(session_user.username, "analyst")
        self.assertIsNotNone(session_user.created_at)
        self.assertIsNotNone(session_user.last_login_at)
        self.store.delete_session(token)
        self.assertIsNone(self.store.user_for_session(token))

    def test_profile_update_changes_username_email_and_avatar(self) -> None:
        user = self.store.create_user(
            "profileuser",
            "profile@example.com",
            "StrongPass123",
            "StrongPass123",
            "Profile User",
            "avatar-data",
        )
        updated = self.store.update_profile(
            user.id,
            "profile.updated",
            "profile.updated@example.com",
            "avatar-it",
        )
        self.assertEqual(updated.username, "profile.updated")
        self.assertEqual(updated.email, "profile.updated@example.com")
        self.assertEqual(updated.display_name, "profile.updated")
        self.assertEqual(updated.avatar, "avatar-it")

        logged_in = self.store.authenticate("profile.updated@example.com", "StrongPass123")
        self.assertEqual(logged_in.id, user.id)

    def test_profile_update_rejects_duplicate_username_or_email(self) -> None:
        first = self.store.create_user(
            "firstuser",
            "first@example.com",
            "StrongPass123",
            "StrongPass123",
            "First User",
            "avatar-data",
        )
        self.store.create_user(
            "seconduser",
            "second@example.com",
            "StrongPass123",
            "StrongPass123",
            "Second User",
            "avatar-it",
        )
        with self.assertRaisesRegex(AuthError, "Username already exists"):
            self.store.update_profile(first.id, "seconduser", "first.new@example.com", "avatar-data")
        with self.assertRaisesRegex(AuthError, "Email already exists"):
            self.store.update_profile(first.id, "firstuser", "second@example.com", "avatar-data")

    def test_change_password_requires_current_password(self) -> None:
        user = self.store.create_user(
            "passworduser",
            "password@example.com",
            "StrongPass123",
            "StrongPass123",
            "Password User",
            "avatar-executive",
        )
        with self.assertRaisesRegex(AuthError, "Current password is incorrect"):
            self.store.change_password(
                user.id,
                "WrongPass123",
                "NewStrongPass123",
                "NewStrongPass123",
            )
        self.store.change_password(
            user.id,
            "StrongPass123",
            "NewStrongPass123",
            "NewStrongPass123",
        )
        self.store.authenticate("passworduser", "NewStrongPass123")

    def test_signup_requires_email_otp_before_user_is_created(self) -> None:
        self.store.begin_signup(
            "newuser",
            "newuser@example.com",
            "New User",
            "avatar-marketing",
            "StrongPass123",
            "StrongPass123",
        )
        self.assertEqual(len(self.store.signup_otps), 1)
        email, username, otp = self.store.signup_otps[0]
        self.assertEqual(email, "newuser@example.com")
        self.assertEqual(username, "newuser")
        self.assertRegex(otp, r"^\d{6}$")

        with self.assertRaisesRegex(AuthError, "Invalid username/email or password"):
            self.store.authenticate("newuser", "StrongPass123")

        with self.assertRaisesRegex(AuthError, "invalid or expired"):
            self.store.verify_signup_otp("newuser@example.com", "000000")

        user = self.store.verify_signup_otp("newuser@example.com", otp)
        self.assertEqual(user.username, "newuser")
        self.assertEqual(user.display_name, "New User")
        self.assertEqual(user.avatar, "avatar-marketing")
        self.store.authenticate("newuser@example.com", "StrongPass123")

    def test_password_reset_sends_token_changes_password_and_invalidates_sessions(self) -> None:
        user = self.store.create_user(
            "owner",
            "owner@example.com",
            "StrongPass123",
            "StrongPass123",
            "Project Owner",
            "avatar-executive",
        )
        session_token = self.store.create_session(user.id)

        self.assertTrue(self.store.request_password_reset("owner@example.com"))
        self.assertEqual(len(self.store.reset_emails), 1)
        email, username, reset_token = self.store.reset_emails[0]
        self.assertEqual(email, "owner@example.com")
        self.assertEqual(username, "owner")

        reset_user = self.store.reset_password(
            reset_token,
            "NewStrongPass123",
            "NewStrongPass123",
        )
        self.assertEqual(reset_user.username, "owner")
        self.assertIsNone(self.store.user_for_session(session_token))
        self.store.authenticate("owner", "NewStrongPass123")

        with self.assertRaisesRegex(AuthError, "invalid or expired"):
            self.store.reset_password(
                reset_token,
                "AnotherStrongPass123",
                "AnotherStrongPass123",
            )

    def test_unknown_password_reset_identifier_does_not_send_email(self) -> None:
        self.assertFalse(self.store.request_password_reset("missing@example.com"))
        self.assertEqual(self.store.reset_emails, [])

    def test_google_user_is_created_and_reused_by_email(self) -> None:
        user = self.store.upsert_google_user(
            "google-sub-1",
            "google.user@example.com",
            "Google User",
            "https://example.com/avatar.png",
        )
        self.assertEqual(user.email, "google.user@example.com")
        self.assertEqual(user.display_name, "Google User")
        self.assertEqual(user.avatar, "https://example.com/avatar.png")

        same_user = self.store.upsert_google_user(
            "google-sub-1",
            "google.user@example.com",
            "Google User Updated",
            "https://example.com/avatar2.png",
        )
        self.assertEqual(same_user.id, user.id)
        self.assertEqual(same_user.display_name, "Google User Updated")
        self.assertEqual(same_user.avatar, "https://example.com/avatar2.png")

    def test_google_user_falls_back_when_profile_name_is_invalid(self) -> None:
        user = self.store.upsert_google_user(
            "google-sub-short-name",
            "shimaa3811@gmail.com",
            "",
            None,
        )
        self.assertEqual(user.email, "shimaa3811@gmail.com")
        self.assertEqual(user.display_name, "shimaa3811")

    def test_google_state_is_single_use(self) -> None:
        state = self.store.create_google_state()
        self.store.consume_google_state(state)
        with self.assertRaisesRegex(AuthError, "expired"):
            self.store.consume_google_state(state)

    def test_default_admin_email_gets_admin_role(self) -> None:
        user = self.store.create_user(
            "demo.admin",
            "employee1001@example.com",
            "StrongPass123",
            "StrongPass123",
            "Demo Admin",
            "avatar-it",
        )
        self.assertTrue(user.is_admin)
        self.assertTrue(user.public()["isAdmin"])

    def test_set_admin_updates_existing_user(self) -> None:
        user = self.store.create_user(
            "employee",
            "employee@example.com",
            "StrongPass123",
            "StrongPass123",
            "Employee User",
            "avatar-hr",
        )
        self.assertFalse(user.is_admin)
        updated = self.store.set_admin("employee@example.com", True)
        self.assertTrue(updated.is_admin)
        self.assertTrue(
            next(item for item in self.store.list_users() if item["email"] == "employee@example.com")["isAdmin"]
        )


if __name__ == "__main__":
    unittest.main()
