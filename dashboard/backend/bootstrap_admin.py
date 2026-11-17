
import getpass
import sqlite3
import sys
import json

from app.config import AUTH_SECRET_KEY
from app.database import get_conn, init_db
from app.auth_service import (
    hash_password,
    normalize_email,
    validate_email,
    utc_string,
)


def main():
    print("\n===================================")
    print(" HPC AIOps - Super Admin Bootstrap")
    print("===================================\n")

    if not AUTH_SECRET_KEY:
        print("ERROR: AUTH_SECRET_KEY is not configured.")
        sys.exit(1)

    init_db()

    email = normalize_email(input("Administrator email: "))

    if not validate_email(email):
        print("ERROR: Invalid email address.")
        sys.exit(1)

    password = getpass.getpass("Create password: ")
    confirmation = getpass.getpass("Confirm password: ")

    if password != confirmation:
        print("ERROR: Passwords do not match.")
        sys.exit(1)

    try:
        password_hash = hash_password(password)
    except ValueError as exc:
        print(f"ERROR: {exc}")
        sys.exit(1)

    now = utc_string()
    conn = get_conn()

    try:
        conn.execute("BEGIN IMMEDIATE")

        existing_super_admin = conn.execute(
            """
            SELECT id
            FROM auth_users
            WHERE role = 'super_admin'
            LIMIT 1
            """
        ).fetchone()

        if existing_super_admin:
            raise ValueError(
                "A super administrator already exists. "
                "Bootstrap cannot be repeated."
            )

        existing_email = conn.execute(
            """
            SELECT id
            FROM auth_users
            WHERE email = ?
            """,
            (email,)
        ).fetchone()

        if existing_email:
            raise ValueError(
                "This email address already has an account."
            )

        cursor = conn.execute(
            """
            INSERT INTO auth_users (
                email,
                password_hash,
                role,
                is_active,
                email_verified_utc,
                created_utc,
                updated_utc
            )
            VALUES (?, ?, 'super_admin', 1, ?, ?, ?)
            """,
            (email, password_hash, now, now, now)
        )

        user_id = cursor.lastrowid

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
                user_id,
                "super_admin_bootstrap",
                email,
                json.dumps({"method": "local_cli"}),
                now
            )
        )

        conn.commit()

        print("\nSUCCESS: Super administrator created.")
        print(f"Account: {email}")
        print("Role: super_admin")
        print("Email verified: Yes")
        print("\nKeep your password secure.")

    except (ValueError, sqlite3.IntegrityError) as exc:
        conn.rollback()
        print(f"\nERROR: {exc}")
        sys.exit(1)

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()


if __name__ == "__main__":
    main()
