import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app import database
from app.auth_routes import FIRST_LOGIN_COOKIE_NAME
from app.email_service import EmailDeliveryError
from app.auth_service import create_session, hash_password
from app.config import AUTH_COOKIE_NAME
from app.main import app


class TemporaryPasswordFlowTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.original_db_path = database.DB_PATH
        database.DB_PATH = Path(self.tempdir.name) / "auth-test.sqlite"
        database.init_db()
        now = "2026-01-01T00:00:00+00:00"
        conn = database.get_conn()
        try:
            user_id = conn.execute(
                """INSERT INTO auth_users (email, full_name, password_hash, role, is_active,
                   email_verified_utc, created_utc, updated_utc)
                   VALUES (?, ?, ?, 'super_admin', 1, ?, ?, ?)""",
                ("root@example.org", "Root Admin", hash_password("AdminPermanentPassword!123"), now, now, now),
            ).lastrowid
            conn.commit()
        finally:
            conn.close()
        self.admin_session = create_session(user_id)
        self.client = TestClient(app)
        self.client.cookies.set(AUTH_COOKIE_NAME, self.admin_session["token"])
        self.deliveries = []
        self.email_patch = patch("app.auth_routes.send_transactional_email", side_effect=self._capture_email)
        self.email_patch.start()

    def tearDown(self):
        self.email_patch.stop()
        self.client.close()
        database.DB_PATH = self.original_db_path
        self.tempdir.cleanup()

    def _capture_email(self, **kwargs):
        self.deliveries.append(kwargs)

    def _last_otp(self):
        match = re.search(r"\b(\d{6})\b", self.deliveries[-1]["text_content"])
        self.assertIsNotNone(match)
        return match.group(1)

    def _invite(self):
        response = self.client.post("/api/auth/invitations", json={"email": "new.user@example.org", "role": "viewer"})
        self.assertEqual(response.status_code, 200, response.text)
        match = re.search(r"temporary password: ([^ ]+)\.", self.deliveries[-1]["text_content"])
        self.assertIsNotNone(match)
        return match.group(1)

    def test_complete_first_login_is_restricted_then_becomes_normal_session(self):
        temporary = self._invite()
        login = self.client.post("/api/auth/login", json={"email": "new.user@example.org", "password": temporary})
        self.assertEqual(login.status_code, 200, login.text)
        self.assertTrue(login.json()["email_verification_required"])
        self.assertEqual(self.client.post("/api/auth/login", json={"email": "new.user@example.org", "password": temporary}).status_code, 401)
        restricted_cookie = login.cookies.get(FIRST_LOGIN_COOKIE_NAME)
        self.assertTrue(restricted_cookie)
        self.assertIn(AUTH_COOKIE_NAME, login.headers.get("set-cookie", ""))
        # httpx's manually injected cookie uses a different jar domain than response cookies.
        self.client.cookies.clear()
        self.client.cookies.set(FIRST_LOGIN_COOKIE_NAME, restricted_cookie)

        verify_email = self.client.post("/api/auth/verify-email", json={"email": "new.user@example.org", "code": self._last_otp()})
        self.assertTrue(verify_email.json()["otp_required"])
        verify_otp = self.client.post("/api/auth/verify-otp", json={"email": "new.user@example.org", "code": self._last_otp()})
        self.assertTrue(verify_otp.json()["password_change_required"])
        self.assertEqual(self.client.get("/api/auth/me").status_code, 401)
        self.assertEqual(self.client.get("/api/state").status_code, 401)

        changed = self.client.post("/api/auth/first-login/password", json={"password": "NewPermanentPassword!123"})
        self.assertEqual(changed.status_code, 200, changed.text)
        self.assertTrue(changed.json()["authenticated"])
        self.assertEqual(self.client.get("/api/auth/me").status_code, 200)
        self.assertEqual(self.client.post("/api/auth/login", json={"email": "new.user@example.org", "password": temporary}).status_code, 401)
        limited = self.client.post("/api/auth/login", json={"email": "new.user@example.org", "password": "NewPermanentPassword!123"})
        self.assertEqual(limited.status_code, 429)  # Existing one-minute resend cooldown remains active.
        conn = database.get_conn()
        try:
            conn.execute("UPDATE auth_otps SET created_utc='2000-01-01T00:00:00+00:00' WHERE user_id=(SELECT id FROM auth_users WHERE email='new.user@example.org') AND purpose='login'")
            conn.commit()
        finally:
            conn.close()
        permanent_login = self.client.post("/api/auth/login", json={"email": "new.user@example.org", "password": "NewPermanentPassword!123"})
        self.assertEqual(permanent_login.status_code, 200, permanent_login.text)
        normal_otp = self.client.post("/api/auth/verify-otp", json={"email": "new.user@example.org", "code": self._last_otp()})
        self.assertTrue(normal_otp.json()["authenticated"])
        self.assertEqual(self.client.get("/api/auth/me").status_code, 200)

    def test_reissue_invalidates_old_credential_and_expiry_is_enforced(self):
        old_password = self._invite()
        conn = database.get_conn()
        try:
            user_id = conn.execute("SELECT id FROM auth_users WHERE email='new.user@example.org'").fetchone()["id"]
        finally:
            conn.close()
        reissued = self.client.post("/api/auth/temporary-password/reissue", json={"user_id": user_id})
        self.assertEqual(reissued.status_code, 200, reissued.text)
        self.assertNotIn("password", reissued.json())
        new_password = re.search(r"temporary password is ([^ ]+)\.", self.deliveries[-1]["text_content"]).group(1)
        self.assertEqual(self.client.post("/api/auth/login", json={"email": "new.user@example.org", "password": old_password}).status_code, 401)
        conn = database.get_conn()
        try:
            conn.execute("UPDATE auth_temporary_credentials SET expires_utc='2000-01-01T00:00:00+00:00' WHERE user_id=?", (user_id,))
            conn.commit()
        finally:
            conn.close()
        self.assertEqual(self.client.post("/api/auth/login", json={"email": "new.user@example.org", "password": new_password}).status_code, 401)
        self.client.post("/api/auth/temporary-password/reissue", json={"user_id": user_id})
        last_password = re.search(r"temporary password is ([^ ]+)\.", self.deliveries[-1]["text_content"]).group(1)
        self.assertEqual(self.client.post("/api/auth/login", json={"email": "new.user@example.org", "password": last_password}).status_code, 200)
        self.assertEqual(self.client.post("/api/auth/login", json={"email": "new.user@example.org", "password": last_password}).status_code, 401)

    def test_schema_initialization_preserves_existing_accounts(self):
        conn = database.get_conn()
        try:
            conn.execute("CREATE TABLE ml_engine_settings (setting TEXT NOT NULL)")
            conn.execute("INSERT INTO ml_engine_settings VALUES ('preserve-me')")
            conn.commit()
        finally:
            conn.close()
        database.init_db()
        conn = database.get_conn()
        try:
            row = conn.execute("SELECT email, role FROM auth_users WHERE email='root@example.org'").fetchone()
            self.assertEqual(tuple(row), ("root@example.org", "super_admin"))
            columns = {r["name"] for r in conn.execute("PRAGMA table_info(auth_temporary_credentials)")}
            self.assertIn("expires_utc", columns)
            self.assertIn("completed_utc", columns)
            self.assertEqual(conn.execute("SELECT setting FROM ml_engine_settings").fetchone()["setting"], "preserve-me")
        finally:
            conn.close()

    def test_failed_invitation_delivery_leaves_credential_revoked_and_reissuable(self):
        with patch("app.auth_routes.send_transactional_email", side_effect=EmailDeliveryError("delivery failed")):
            failed = self.client.post("/api/auth/invitations", json={"email": "new.user@example.org", "role": "viewer"})
        self.assertEqual(failed.status_code, 502)
        conn = database.get_conn()
        try:
            row = conn.execute("SELECT revoked_utc FROM auth_temporary_credentials WHERE user_id=(SELECT id FROM auth_users WHERE email='new.user@example.org')").fetchone()
            self.assertIsNotNone(row["revoked_utc"])
            user_id = conn.execute("SELECT id FROM auth_users WHERE email='new.user@example.org'").fetchone()["id"]
        finally:
            conn.close()
        self.assertEqual(self.client.post("/api/auth/login", json={"email": "new.user@example.org", "password": "unknown"}).status_code, 401)
        result = self.client.post("/api/auth/temporary-password/reissue", json={"user_id": user_id})
        self.assertEqual(result.status_code, 200, result.text)


if __name__ == "__main__":
    unittest.main()
