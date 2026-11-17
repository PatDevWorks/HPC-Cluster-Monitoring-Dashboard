
import hashlib
import hmac
import secrets
import re
import sqlite3

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from pwdlib import PasswordHash

from .config import AUTH_SECRET_KEY, AUTH_SESSION_HOURS
from .database import get_conn


# --------------------------------------------------
# Security configuration
# --------------------------------------------------

_password_hasher = PasswordHash.recommended()

OTP_LENGTH = 6
OTP_EXPIRY_MINUTES = 5
OTP_MAX_ATTEMPTS = 5
OTP_RESEND_COOLDOWN_SECONDS = 60

VALID_ROLES = {"super_admin", "admin", "viewer"}


# --------------------------------------------------
# Shared utilities
# --------------------------------------------------

def utc_now() -> datetime:
    """Return the current timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


def utc_string(value: Optional[datetime] = None) -> str:
    """Convert a datetime to a consistent UTC ISO timestamp."""
    value = value or utc_now()
    return value.astimezone(timezone.utc).isoformat()


def hash_token(token: str) -> str:
    """Create a keyed digest for sensitive authentication tokens."""
    if not AUTH_SECRET_KEY:
        raise RuntimeError("AUTH_SECRET_KEY is not configured.")

    return hmac.new(
        AUTH_SECRET_KEY.encode("utf-8"),
        token.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()


def normalize_email(email: str) -> str:
    """Normalize an email address."""
    return email.strip().lower()


def validate_email(email: str) -> bool:
    """Perform basic email address validation."""
    email = normalize_email(email)

    return bool(
        re.fullmatch(
            r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@"
            r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}"
            r"[A-Za-z0-9])?"
            r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}"
            r"[A-Za-z0-9])?)+",
            email
        )
    )


# --------------------------------------------------
# Password security
# --------------------------------------------------

def hash_password(password: str) -> str:
    """Hash a password using the recommended Argon2 configuration."""
    if len(password) < 12:
        raise ValueError("Password must contain at least 12 characters.")

    return _password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against its stored Argon2 hash."""
    try:
        return _password_hasher.verify(password, password_hash)
    except (ValueError, TypeError):
        return False
def authenticate_password(email: str, password: str) -> Optional[dict]:
    """
    Verify user credentials without exposing whether an email exists.

    Returns the account details when credentials are valid,
    otherwise returns None.
    """

    if not email or not password:
        return None

    email = normalize_email(email)

    if not validate_email(email):
        return None

    conn = get_conn()

    try:
        user = conn.execute(
            """
            SELECT
                id,
                email,
                password_hash,
                role,
                is_active,
                email_verified_utc
            FROM auth_users
            WHERE email = ?
            """,
            (email,)
        ).fetchone()

        if not user:
            return None

        if not user["is_active"]:
            return None

        if not verify_password(password, user["password_hash"]):
            return None

        return {
            "id": user["id"],
            "email": user["email"],
            "role": user["role"],
            "email_verified": bool(user["email_verified_utc"])
        }

    finally:
        conn.close()
# --------------------------------------------------
# One-time password (OTP) management
# --------------------------------------------------

def issue_otp(user_id: int, purpose: str = "login") -> str:
    """
    Generate and store a six-digit OTP.

    Returns the plaintext code internally so the email service
    can deliver it. Never expose it through a public API response.
    """

    if purpose not in {"login", "email_verification"}:
        raise ValueError("Unsupported OTP purpose.")

    now = utc_now()
    now_text = utc_string(now)
    expiry_text = utc_string(
        now + timedelta(minutes=OTP_EXPIRY_MINUTES)
    )

    code = f"{secrets.randbelow(1_000_000):06d}"
    code_hash = hash_token(f"otp:{user_id}:{purpose}:{code}")

    conn = get_conn()

    try:
        conn.execute("BEGIN IMMEDIATE")

        user = conn.execute(
            """
            SELECT id, is_active
            FROM auth_users
            WHERE id = ?
            """,
            (user_id,)
        ).fetchone()

        if not user or not user["is_active"]:
            raise ValueError("User does not exist or is inactive.")

        latest = conn.execute(
            """
            SELECT created_utc
            FROM auth_otps
            WHERE user_id = ? AND purpose = ?
            ORDER BY created_utc DESC
            LIMIT 1
            """,
            (user_id, purpose)
        ).fetchone()

        if latest:
            latest_time = datetime.fromisoformat(
                latest["created_utc"]
            )

            elapsed = (now - latest_time).total_seconds()

            if elapsed < OTP_RESEND_COOLDOWN_SECONDS:
                raise ValueError(
                    "Please wait before requesting another OTP."
                )

        # Invalidate previously issued, unused OTPs.
        conn.execute(
            """
            UPDATE auth_otps
            SET invalidated_utc = ?
            WHERE user_id = ?
              AND purpose = ?
              AND consumed_utc IS NULL
              AND invalidated_utc IS NULL
            """,
            (now_text, user_id, purpose)
        )

        conn.execute(
            """
            INSERT INTO auth_otps (
                user_id,
                otp_hash,
                purpose,
                attempts,
                max_attempts,
                created_utc,
                expires_utc
            )
            VALUES (?, ?, ?, 0, ?, ?, ?)
            """,
            (
                user_id,
                code_hash,
                purpose,
                OTP_MAX_ATTEMPTS,
                now_text,
                expiry_text
            )
        )

        conn.commit()
        return code

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()


def verify_otp(
    user_id: int,
    code: str,
    purpose: str = "login"
) -> bool:
    """
    Verify the latest valid OTP.

    A successful OTP is consumed immediately.
    Failed attempts are recorded in the database.
    """

    if purpose not in {"login", "email_verification"}:
        return False

    if not re.fullmatch(r"\d{6}", code or ""):
        return False

    now = utc_now()
    now_text = utc_string(now)

    conn = get_conn()

    try:
        conn.execute("BEGIN IMMEDIATE")

        otp = conn.execute(
            """
            SELECT *
            FROM auth_otps
            WHERE user_id = ?
              AND purpose = ?
              AND consumed_utc IS NULL
              AND invalidated_utc IS NULL
            ORDER BY created_utc DESC
            LIMIT 1
            """,
            (user_id, purpose)
        ).fetchone()

        if not otp:
            conn.commit()
            return False

        expiry = datetime.fromisoformat(otp["expires_utc"])

        if now >= expiry:
            conn.execute(
                """
                UPDATE auth_otps
                SET invalidated_utc = ?
                WHERE id = ?
                """,
                (now_text, otp["id"])
            )
            conn.commit()
            return False

        if otp["attempts"] >= otp["max_attempts"]:
            conn.execute(
                """
                UPDATE auth_otps
                SET invalidated_utc = ?
                WHERE id = ?
                """,
                (now_text, otp["id"])
            )
            conn.commit()
            return False

        submitted_hash = hash_token(
            f"otp:{user_id}:{purpose}:{code}"
        )

        if not hmac.compare_digest(
            submitted_hash,
            otp["otp_hash"]
        ):
            new_attempts = otp["attempts"] + 1

            conn.execute(
                """
                UPDATE auth_otps
                SET attempts = ?,
                    invalidated_utc = CASE
                        WHEN ? >= max_attempts THEN ?
                        ELSE invalidated_utc
                    END
                WHERE id = ?
                """,
                (
                    new_attempts,
                    new_attempts,
                    now_text,
                    otp["id"]
                )
            )

            conn.commit()
            return False

        conn.execute(
            """
            UPDATE auth_otps
            SET consumed_utc = ?
            WHERE id = ?
            """,
            (now_text, otp["id"])
        )

        conn.commit()
        return True

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()


# --------------------------------------------------
# Server-managed session management
# --------------------------------------------------

def create_session(user_id: int) -> dict:
    """
    Create a secure session for an active, verified user.

    The raw token is returned once for the HTTP-only cookie.
    Only its keyed hash is stored in the database.
    """

    raw_token = secrets.token_urlsafe(32)
    token_digest = hash_token(f"session:{raw_token}")

    now = utc_now()
    expires = now + timedelta(hours=AUTH_SESSION_HOURS)

    conn = get_conn()

    try:
        conn.execute("BEGIN IMMEDIATE")

        user = conn.execute(
            """
            SELECT id, email, role, is_active, email_verified_utc
            FROM auth_users
            WHERE id = ?
            """,
            (user_id,)
        ).fetchone()

        if (
            not user
            or not user["is_active"]
            or not user["email_verified_utc"]
        ):
            raise ValueError(
                "An active, email-verified account is required."
            )

        conn.execute(
            """
            INSERT INTO auth_sessions (
                user_id,
                session_token_hash,
                created_utc,
                expires_utc,
                last_seen_utc
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                user_id,
                token_digest,
                utc_string(now),
                utc_string(expires),
                utc_string(now)
            )
        )

        conn.commit()

        return {
            "token": raw_token,
            "expires_utc": utc_string(expires),
            "user": {
                "id": user["id"],
                "email": user["email"],
                "role": user["role"]
            }
        }

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()


def get_session_user(raw_token: Optional[str]) -> Optional[dict]:
    """
    Validate a session token and return its authenticated user.

    Returns None for missing, expired, revoked, or invalid sessions.
    """

    if not raw_token:
        return None

    token_digest = hash_token(f"session:{raw_token}")
    now = utc_now()
    now_text = utc_string(now)

    conn = get_conn()

    try:
        conn.execute("BEGIN IMMEDIATE")

        row = conn.execute(
            """
            SELECT
                s.id AS session_id,
                s.expires_utc,
                s.last_seen_utc,
                u.id AS user_id,
                u.email,
                u.full_name,
                u.role,
                u.is_active,
                u.email_verified_utc
            FROM auth_sessions s
            JOIN auth_users u ON u.id = s.user_id
            WHERE s.session_token_hash = ?
              AND s.revoked_utc IS NULL
            """,
            (token_digest,)
        ).fetchone()

        if not row:
            conn.commit()
            return None

        expires = datetime.fromisoformat(row["expires_utc"])

        if (
            now >= expires
            or not row["is_active"]
            or not row["email_verified_utc"]
        ):
            conn.commit()
            return None

        # Update last_seen at most once every five minutes.
        last_seen = (
            datetime.fromisoformat(row["last_seen_utc"])
            if row["last_seen_utc"]
            else None
        )

        if (
            last_seen is None
            or (now - last_seen).total_seconds() >= 300
        ):
            conn.execute(
                """
                UPDATE auth_sessions
                SET last_seen_utc = ?
                WHERE id = ?
                """,
                (now_text, row["session_id"])
            )

        conn.commit()

        return {
    "id": row["user_id"],
    "email": row["email"],
    "full_name": row["full_name"],
    "role": row["role"],
    "session_id": row["session_id"]
}

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()


def revoke_session(raw_token: Optional[str]) -> bool:
    """Revoke one session using its raw token."""

    if not raw_token:
        return False

    token_digest = hash_token(f"session:{raw_token}")

    conn = get_conn()

    try:
        cursor = conn.execute(
            """
            UPDATE auth_sessions
            SET revoked_utc = ?
            WHERE session_token_hash = ?
              AND revoked_utc IS NULL
            """,
            (utc_string(), token_digest)
        )

        conn.commit()
        return cursor.rowcount > 0

    finally:
        conn.close()


def revoke_all_sessions(user_id: int) -> int:
    """Revoke every active session belonging to a user."""

    conn = get_conn()

    try:
        cursor = conn.execute(
            """
            UPDATE auth_sessions
            SET revoked_utc = ?
            WHERE user_id = ?
              AND revoked_utc IS NULL
            """,
            (utc_string(), user_id)
        )

        conn.commit()
        return cursor.rowcount

    finally:
        conn.close()


# --------------------------------------------------
# Authentication audit logging
# --------------------------------------------------

def record_auth_event(
    event_type: str,
    actor_user_id: Optional[int] = None,
    target_email: Optional[str] = None,
    details: Optional[dict[str, Any]] = None
) -> None:
    """Record an authentication-related event."""

    import json

    conn = get_conn()

    try:
        conn.execute(
            """
            INSERT INTO auth_audit_log (
                actor_user_id,
                event_type,
                target_email,
                details_json,
                created_utc
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                actor_user_id,
                event_type,
                normalize_email(target_email)
                if target_email else None,
                json.dumps(details or {}),
                utc_string()
            )
        )

        conn.commit()

    finally:
        conn.close()

# --------------------------------------------------
# Invitation-only account registration
# --------------------------------------------------

def create_invitation(
    email: str,
    role: str,
    invited_by: int,
    validity_hours: int = 48
) -> dict:
    """Create a secure, time-limited account invitation."""

    email = normalize_email(email)

    if not validate_email(email):
        raise ValueError("Invalid email address.")

    if role not in {"admin", "viewer"}:
        raise ValueError("Invalid invitation role.")

    if not 1 <= validity_hours <= 168:
        raise ValueError("Invitation validity must be 1-168 hours.")

    raw_token = secrets.token_urlsafe(32)
    token_digest = hash_token(f"invite:{raw_token}")

    now = utc_now()
    expires = now + timedelta(hours=validity_hours)

    conn = get_conn()

    try:
        conn.execute("BEGIN IMMEDIATE")

        actor = conn.execute(
            """
            SELECT role, is_active
            FROM auth_users
            WHERE id = ?
            """,
            (invited_by,)
        ).fetchone()

        if not actor or not actor["is_active"]:
            raise ValueError("Inviting administrator is invalid.")

        if actor["role"] != "super_admin":
           raise ValueError("Only the super administrator can invite users.")

        existing_user = conn.execute(
            """
            SELECT id
            FROM auth_users
            WHERE email = ?
            """,
            (email,)
        ).fetchone()

        if existing_user:
            raise ValueError("An account already exists for this email.")

        # Revoke any previous outstanding invitations.
        conn.execute(
            """
            UPDATE auth_invitations
            SET revoked_utc = ?
            WHERE email = ?
              AND accepted_utc IS NULL
              AND revoked_utc IS NULL
            """,
            (utc_string(now), email)
        )

        conn.execute(
            """
            INSERT INTO auth_invitations (
                email,
                token_hash,
                role,
                invited_by,
                created_utc,
                expires_utc
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                email,
                token_digest,
                role,
                invited_by,
                utc_string(now),
                utc_string(expires)
            )
        )

        conn.execute(
            """
            INSERT INTO auth_audit_log (
                actor_user_id,
                event_type,
                target_email,
                details_json,
                created_utc
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                invited_by,
                "invitation_created",
                email,
                '{"role": "' + role + '"}',
                utc_string(now)
            )
        )

        conn.commit()

        return {
            "email": email,
            "role": role,
            "token": raw_token,
            "expires_utc": utc_string(expires)
        }

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()



def accept_invitation(
    raw_token: str,
    full_name: str,
    password: str
) -> dict:
    """Redeem an invitation and create an unverified user account."""

    if not raw_token:
        raise ValueError("Invitation token is required.")

    full_name = full_name.strip()

    if not full_name:
        raise ValueError("Full name is required.")

    if len(full_name) > 120:
        raise ValueError("Full name must not exceed 120 characters.")

    password_digest = hash_password(password)
    token_digest = hash_token(f"invite:{raw_token}")

    now = utc_now()
    now_text = utc_string(now)

    conn = get_conn()

    try:
        conn.execute("BEGIN IMMEDIATE")

        invitation = conn.execute(
            """
            SELECT *
            FROM auth_invitations
            WHERE token_hash = ?
              AND accepted_utc IS NULL
              AND revoked_utc IS NULL
            """,
            (token_digest,)
        ).fetchone()

        if not invitation:
            raise ValueError("Invitation is invalid or already used.")

        expires = datetime.fromisoformat(
            invitation["expires_utc"]
        )

        if now >= expires:
            raise ValueError("Invitation has expired.")

        existing_user = conn.execute(
            """
            SELECT id
            FROM auth_users
            WHERE email = ?
            """,
            (invitation["email"],)
        ).fetchone()

        if existing_user:
            raise ValueError("An account already exists for this email.")

        cursor = conn.execute(
            """
            INSERT INTO auth_users (
    email,
    full_name,
    password_hash,
    role,
    is_active,
    email_verified_utc,
    created_utc,
    updated_utc
)
VALUES (?, ?, ?, ?, 1, NULL, ?, ?)
            """,
            (
    invitation["email"],
    full_name,
    password_digest,
    invitation["role"],
    now_text,
    now_text
)
        )

        user_id = cursor.lastrowid

        conn.execute(
            """
            UPDATE auth_invitations
            SET accepted_utc = ?
            WHERE id = ?
            """,
            (now_text, invitation["id"])
        )

        conn.execute(
            """
            INSERT INTO auth_audit_log (
                actor_user_id,
                event_type,
                target_email,
                details_json,
                created_utc
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                invitation["invited_by"],
                "invitation_accepted",
                invitation["email"],
                '{"new_user_id": ' + str(user_id) + '}',
                now_text
            )
        )

        conn.commit()

        return {
            "user_id": user_id,
            "email": invitation["email"],
            "full_name": full_name, 
            "role": invitation["role"],
            "email_verified": False
        }

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()



def verify_email_otp(user_id: int, code: str) -> bool:
    """
    Verify an email OTP and activate email verification.

    OTP consumption and account verification happen
    in one atomic database transaction.
    """

    purpose = "email_verification"

    if not re.fullmatch(r"\d{6}", code or ""):
        return False

    now = utc_now()
    now_text = utc_string(now)

    conn = get_conn()

    try:
        conn.execute("BEGIN IMMEDIATE")

        # Find the latest unused email verification OTP.
        otp = conn.execute(
            """
            SELECT *
            FROM auth_otps
            WHERE user_id = ?
              AND purpose = ?
              AND consumed_utc IS NULL
              AND invalidated_utc IS NULL
            ORDER BY created_utc DESC
            LIMIT 1
            """,
            (user_id, purpose)
        ).fetchone()

        if not otp:
            conn.commit()
            return False

        # Check expiration.
        expiry = datetime.fromisoformat(otp["expires_utc"])

        if now >= expiry:
            conn.execute(
                """
                UPDATE auth_otps
                SET invalidated_utc = ?
                WHERE id = ?
                """,
                (now_text, otp["id"])
            )
            conn.commit()
            return False

        # Check maximum attempts.
        if otp["attempts"] >= otp["max_attempts"]:
            conn.execute(
                """
                UPDATE auth_otps
                SET invalidated_utc = ?
                WHERE id = ?
                """,
                (now_text, otp["id"])
            )
            conn.commit()
            return False

        # Compare the submitted code against its stored hash.
        submitted_hash = hash_token(
            f"otp:{user_id}:{purpose}:{code}"
        )

        if not hmac.compare_digest(
            submitted_hash,
            otp["otp_hash"]
        ):
            new_attempts = otp["attempts"] + 1

            conn.execute(
                """
                UPDATE auth_otps
                SET attempts = ?,
                    invalidated_utc = CASE
                        WHEN ? >= max_attempts THEN ?
                        ELSE invalidated_utc
                    END
                WHERE id = ?
                """,
                (
                    new_attempts,
                    new_attempts,
                    now_text,
                    otp["id"]
                )
            )

            conn.commit()
            return False

        # Mark the account as email verified.
        cursor = conn.execute(
            """
            UPDATE auth_users
            SET email_verified_utc = ?,
                updated_utc = ?
            WHERE id = ?
              AND is_active = 1
              AND email_verified_utc IS NULL
            """,
            (now_text, now_text, user_id)
        )

        # Do not consume the OTP if the account cannot be verified.
        if cursor.rowcount != 1:
            conn.rollback()
            return False

        # Consume the OTP in the same transaction.
        conn.execute(
            """
            UPDATE auth_otps
            SET consumed_utc = ?
            WHERE id = ?
            """,
            (now_text, otp["id"])
        )

        conn.commit()
        return True

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()

