
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from html import escape
from datetime import datetime, timezone
from .auth_dependencies import (
    get_current_user,
    require_roles,
)
from .auth_service import (
    authenticate_password,
    issue_otp,
    verify_otp,
    verify_email_otp,
    create_session,
    record_auth_event,
    revoke_session,
    create_temporary_account,
    reissue_temporary_password,
    revoke_temporary_password,
    create_first_login_state,
    get_first_login_state,
    complete_first_login,
    accept_invitation,
)
from urllib.parse import quote

from .database import get_conn

from .config import FRONTEND_BASE_URL
from .email_service import (
    send_transactional_email,
    EmailDeliveryError,
)
from .config import (
    AUTH_COOKIE_NAME,
    AUTH_COOKIE_SECURE,
    AUTH_SESSION_HOURS,
)
router = APIRouter(prefix="/api/auth", tags=["Authentication"])


class LoginRequest(BaseModel):
    email: str
    password: str


class OTPVerifyRequest(BaseModel):
    email: str
    code: str
class InvitationRequest(BaseModel):
    email: str
    role: str
    validity_hours: int = 48


class RegistrationRequest(BaseModel):
    token: str
    full_name: str
    password: str


class ProfileUpdateRequest(BaseModel):
    full_name: str


class EmailVerificationRequest(BaseModel):
    email: str
    code: str


class ResendVerificationRequest(BaseModel):
    email: str


class FirstLoginPasswordRequest(BaseModel):
    password: str


class ReissueTemporaryPasswordRequest(BaseModel):
    user_id: int


FIRST_LOGIN_COOKIE_NAME = "hpc_first_login"

@router.post("/invitations")
def send_invitation(
    payload: InvitationRequest,
    current_user: dict = Depends(require_roles("super_admin")),
):
    """Create an invited account and email its one-time temporary password."""

    try:
        invitation = create_temporary_account(
            email=payload.email,
            role=payload.role,
            invited_by=current_user["id"],
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        )

    recipient = escape(invitation["email"])
    assigned_role = escape(invitation["role"])
    expiry = escape(invitation["expires_utc"])
    temporary_password = escape(invitation["password"])

    subject = "Invitation - HPC Predictive Monitoring Dashboard"

    html_content = f"""
    <html>
        <body style="font-family: Arial, sans-serif;">
            <h2>HPC Predictive Monitoring Dashboard</h2>

            <p>You have been invited to join the HPC dashboard. Sign in using the temporary password below.</p>

            <p><strong>Email:</strong> {recipient}</p>
            <p><strong>Assigned role:</strong> {assigned_role}</p>

            <p><strong>Temporary password:</strong> {temporary_password}</p>
            <p>This password expires at {expiry}. You will verify your email and create a permanent password after signing in.</p>
            <p>If you were not expecting this invitation, ignore this email.</p>
        </body>
    </html>
    """

    text_content = (
        "You have been invited to join the HPC Predictive Monitoring Dashboard. "
        f"Your assigned role is {invitation['role']}. "
        f"Sign in at {FRONTEND_BASE_URL} using temporary password: {invitation['password']}. "
        f"It expires at {invitation['expires_utc']}."
    )

    try:
        send_transactional_email(
            to_email=invitation["email"],
            subject=subject,
            html_content=html_content,
            text_content=text_content,
        )
    except EmailDeliveryError:
        revoke_temporary_password(invitation["user_id"])
        record_auth_event(
            event_type="invitation_email_delivery_failed",
            actor_user_id=current_user["id"],
            target_email=invitation["email"],
        )

        raise HTTPException(
            status_code=502,
            detail=(
                "The account was created, but its email could not be delivered. Reissue its temporary password from User Management."
            ),
        )

    record_auth_event(
        event_type="invitation_email_sent",
        actor_user_id=current_user["id"],
        target_email=invitation["email"],
    )

    return {
        "success": True,
        "message": "Temporary password sent successfully.",
        "email": invitation["email"],
        "role": invitation["role"],
        "expires_utc": invitation["expires_utc"],
    }


@router.post("/temporary-password/reissue")
def reissue_user_temporary_password(
    payload: ReissueTemporaryPasswordRequest,
    current_user: dict = Depends(require_roles("super_admin")),
):
    try:
        credential = reissue_temporary_password(payload.user_id, current_user["id"])
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    password = escape(credential["password"])
    expiry = escape(credential["expires_utc"])
    try:
        send_transactional_email(
            to_email=credential["email"],
            subject="Your new temporary password - HPC Predictive Monitoring Dashboard",
            html_content=f"<p>Your new temporary password is <strong>{password}</strong>.</p><p>It expires at {expiry}. Sign in to verify your email and create a permanent password.</p>",
            text_content=f"Your new temporary password is {credential['password']}. It expires at {credential['expires_utc']}.",
        )
    except EmailDeliveryError:
        revoke_temporary_password(credential["user_id"])
        record_auth_event(event_type="temporary_password_delivery_failed", actor_user_id=current_user["id"], target_email=credential["email"])
        raise HTTPException(status_code=502, detail="The credential was rotated but could not be emailed. Reissue it again after checking email delivery.")
    record_auth_event(event_type="temporary_password_resent", actor_user_id=current_user["id"], target_email=credential["email"])
    return {"success": True, "message": "Temporary password reissued and emailed.", "email": credential["email"], "expires_utc": credential["expires_utc"]}
@router.post("/register")
def register_account(payload: RegistrationRequest):
    """Accept an invitation and create an unverified account."""

    try:
        account = accept_invitation(
            raw_token=payload.token,
            full_name=payload.full_name,
            password=payload.password,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        )

    # Generate an email-verification code.
    try:
        otp = issue_otp(
            user_id=account["user_id"],
            purpose="email_verification",
        )
    except ValueError:
        record_auth_event(
            event_type="registration_otp_generation_failed",
            target_email=account["email"],
        )
        raise HTTPException(
            status_code=429,
            detail=(
                "Your account was created, but a verification code "
                "could not be generated. Please request another code."
            ),
        )

    safe_name = escape(account["full_name"])

    subject = "Verify your email - HPC Predictive Monitoring Dashboard"

    html_content = f"""
    <html>
        <body style="font-family: Arial, sans-serif;">
            <h2>HPC Predictive Monitoring Dashboard</h2>

            <p>Hello {safe_name},</p>

            <p>Your account has been created successfully.</p>

            <p>Your email verification code is:</p>

            <h1 style="letter-spacing: 8px;">{otp}</h1>

            <p>This code expires in 5 minutes.</p>

            <p>
                You must verify your email address before logging in.
            </p>
        </body>
    </html>
    """

    text_content = (
        f"Hello {account['full_name']}. "
        f"Your email verification code is {otp}. "
        "It expires in 5 minutes."
    )

    try:
        send_transactional_email(
            to_email=account["email"],
            subject=subject,
            html_content=html_content,
            text_content=text_content,
        )
    except EmailDeliveryError:
        record_auth_event(
            event_type="registration_verification_delivery_failed",
            target_email=account["email"],
        )

        raise HTTPException(
            status_code=502,
            detail=(
                "Your account was created, but the verification email "
                "could not be delivered. Please request another code."
            ),
        )

    record_auth_event(
        event_type="registration_verification_sent",
        target_email=account["email"],
    )

    return {
        "success": True,
        "message": "Account created. Check your email for the verification code.",
        "email": account["email"],
        "email_verification_required": True,
    }
@router.post("/verify-email")
def verify_email(payload: EmailVerificationRequest, request: Request):
    """Verify a newly registered user's email address."""

    email = payload.email.strip().lower()

    conn = get_conn()
    try:
        user = conn.execute(
            """
            SELECT id, is_active, email_verified_utc
            FROM auth_users
            WHERE email = ?
            """,
            (email,),
        ).fetchone()
    finally:
        conn.close()

    if not user or not user["is_active"]:
        raise HTTPException(
            status_code=400,
            detail="Invalid or expired verification request.",
        )

    if user["email_verified_utc"]:
        return {
            "success": True,
            "message": "Email address is already verified.",
        }

    verified = verify_email_otp(
        user_id=user["id"],
        code=payload.code.strip(),
    )

    if not verified:
        raise HTTPException(
            status_code=400,
            detail="Invalid or expired verification code.",
        )

    record_auth_event(
        event_type="email_verification_success",
        actor_user_id=user["id"],
        target_email=email,
    )

    first_login = get_first_login_state(request.cookies.get(FIRST_LOGIN_COOKIE_NAME))
    if first_login and first_login["user_id"] == user["id"]:
        try:
            otp = issue_otp(user_id=user["id"], purpose="login")
            send_transactional_email(
                to_email=email,
                subject="HPC Predictive Monitoring Dashboard - Login Verification",
                html_content=f"<p>Your login verification code is:</p><h1>{escape(otp)}</h1><p>This code expires in 5 minutes.</p>",
                text_content=f"Your login verification code is {otp}. It expires in 5 minutes.",
            )
        except (ValueError, EmailDeliveryError):
            raise HTTPException(status_code=502, detail="Email verified, but the login code could not be delivered. Sign in again to request a new code.")
        return {"success": True, "message": "Email verified. A login verification code has been sent.", "otp_required": True, "password_change_required": True}

    return {
        "success": True,
        "message": "Email address verified successfully. You can now log in.",
    }
@router.post("/resend-verification")
def resend_verification(payload: ResendVerificationRequest):
    """Resend an email verification code."""

    email = payload.email.strip().lower()

    generic_response = {
        "success": True,
        "message": (
            "If an active unverified account exists, "
            "a verification code has been sent."
        ),
    }

    conn = get_conn()
    try:
        user = conn.execute(
            """
            SELECT id, email, is_active, email_verified_utc
            FROM auth_users
            WHERE email = ?
            """,
            (email,),
        ).fetchone()
    finally:
        conn.close()

    # Do not reveal whether an account exists.
    if not user or not user["is_active"] or user["email_verified_utc"]:
        return generic_response

    try:
        otp = issue_otp(
            user_id=user["id"],
            purpose="email_verification",
        )
    except ValueError:
        return generic_response

    subject = "Your email verification code - HPC Predictive Monitoring Dashboard"

    html_content = f"""
    <html>
        <body>
            <h2>Email verification</h2>
            <p>Your new verification code is:</p>
            <h1>{escape(otp)}</h1>
            <p>This code expires in 5 minutes.</p>
            <p>If you did not request this code, you can ignore this email.</p>
        </body>
    </html>
    """

    text_content = (
        f"Your new email verification code is {otp}. "
        "It expires in 5 minutes."
    )

    try:
        send_transactional_email(
            to_email=email,
            subject=subject,
            html_content=html_content,
            text_content=text_content,
        )
    except EmailDeliveryError:
        record_auth_event(
            event_type="verification_resend_delivery_failed",
            target_email=email,
        )
        return generic_response

    record_auth_event(
        event_type="verification_code_resent",
        actor_user_id=user["id"],
        target_email=email,
    )

    return generic_response
@router.post("/verify-otp")
def verify_login_otp(
    payload: OTPVerifyRequest,
    request: Request,
    response: Response,
):
    """Verify login OTP and establish an authenticated session."""

    email = payload.email.strip().lower()

    # Retrieve the account associated with the email.
    from .database import get_conn

    conn = get_conn()

    try:
        user = conn.execute(
            """
            SELECT id, email, role, is_active, email_verified_utc
            FROM auth_users
            WHERE email = ?
            """,
            (email,)
        ).fetchone()
    finally:
        conn.close()

    if (
        not user
        or not user["is_active"]
        or not user["email_verified_utc"]
    ):
        record_auth_event(
            event_type="login_otp_failed",
            target_email=email,
        )
        raise HTTPException(status_code=401, detail="Invalid or expired verification code.")

    first_login = get_first_login_state(request.cookies.get(FIRST_LOGIN_COOKIE_NAME))
    if first_login:
        if first_login["user_id"] != user["id"] or not first_login["email_verified_utc"]:
            raise HTTPException(status_code=401, detail="Invalid or expired verification code.")
        valid = verify_otp(user_id=user["id"], code=payload.code, purpose="login")
        if not valid:
            record_auth_event(event_type="login_otp_failed", actor_user_id=user["id"], target_email=email)
            raise HTTPException(status_code=401, detail="Invalid or expired verification code.")
        conn = get_conn()
        try:
            conn.execute("UPDATE auth_first_login_states SET otp_verified_utc = ? WHERE id = ? AND consumed_utc IS NULL AND revoked_utc IS NULL", (datetime.now(timezone.utc).isoformat(), first_login["id"]))
            conn.commit()
        finally:
            conn.close()
        return {"success": True, "authenticated": False, "password_change_required": True}
    # Verify and consume the OTP.
    valid = verify_otp(
        user_id=user["id"],
        code=payload.code,
        purpose="login",
    )

    if not valid:
        record_auth_event(
            event_type="login_otp_failed",
            actor_user_id=user["id"],
            target_email=email,
        )
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired verification code."
        )

    # Create a server-managed session.
    try:
        session = create_session(user["id"])
    except ValueError:
        raise HTTPException(
            status_code=403,
            detail="Unable to establish an authenticated session."
        )

    # Store the session token in an HTTP-only cookie.
    response.set_cookie(
        key=AUTH_COOKIE_NAME,
        value=session["token"],
        max_age=AUTH_SESSION_HOURS * 3600,
        httponly=True,
        secure=AUTH_COOKIE_SECURE,
        samesite="lax",
        path="/",
    )

    record_auth_event(
        event_type="login_success",
        actor_user_id=user["id"],
        target_email=email,
    )

    return {
        "success": True,
        "authenticated": True,
        "user": session["user"],
        "expires_utc": session["expires_utc"],
    }
@router.get("/me")
def get_authenticated_user(
    current_user: dict = Depends(get_current_user),
):
    """Return the currently authenticated dashboard user."""
    return {
    "authenticated": True,
    "user": {
        "id": current_user["id"],
        "email": current_user["email"],
        "full_name": current_user["full_name"],
        "role": current_user["role"],
    },
}


@router.patch("/profile")
def update_authenticated_profile(
    payload: ProfileUpdateRequest,
    current_user: dict = Depends(get_current_user),
):
    """Update the signed-in user's own display name."""
    full_name = payload.full_name.strip()
    if not full_name:
        raise HTTPException(status_code=400, detail="Name cannot be blank.")
    if len(full_name) > 120:
        raise HTTPException(status_code=400, detail="Name must be 120 characters or fewer.")

    conn = get_conn()
    try:
        cursor = conn.execute(
            "UPDATE auth_users SET full_name = ? WHERE id = ?",
            (full_name, current_user["id"]),
        )
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Account not found.")
        conn.commit()
    finally:
        conn.close()

    return {
        "success": True,
        "user": {
            "id": current_user["id"],
            "email": current_user["email"],
            "full_name": full_name,
            "role": current_user["role"],
        },
    }
@router.post("/login")
def login(payload: LoginRequest, response: Response):
    """Authenticate credentials and send a login OTP."""

    user = authenticate_password(
        payload.email,
        payload.password
    )

    if not user:
        record_auth_event(
            event_type="login_failed",
            target_email=payload.email,
        )
        raise HTTPException(status_code=401, detail="Invalid email address or password.")

    if user.get("temporary_password"):
        # Never let an unrelated or stale normal session survive a restricted login.
        response.delete_cookie(key=AUTH_COOKIE_NAME, path="/", httponly=True, secure=AUTH_COOKIE_SECURE, samesite="lax")
        state = create_first_login_state(user["id"])
        response.set_cookie(key=FIRST_LOGIN_COOKIE_NAME, value=state["token"], max_age=20 * 60,
            httponly=True, secure=AUTH_COOKIE_SECURE, samesite="lax", path="/")
        if not user["email_verified"]:
            try:
                otp = issue_otp(user_id=user["id"], purpose="email_verification")
                send_transactional_email(
                    to_email=user["email"],
                    subject="Verify your email - HPC Predictive Monitoring Dashboard",
                    html_content=f"<p>Your email verification code is:</p><h1>{escape(otp)}</h1><p>This code expires in 5 minutes.</p>",
                    text_content=f"Your email verification code is {otp}. It expires in 5 minutes.",
                )
            except (ValueError, EmailDeliveryError):
                raise HTTPException(status_code=502, detail="Could not deliver the verification email. Use Resend code or contact an administrator for a fresh temporary password.")
            return {"success": True, "first_login": True, "email_verification_required": True,
                    "message": "A verification code has been sent to your email."}
        try:
            otp = issue_otp(user_id=user["id"], purpose="login")
            send_transactional_email(
                to_email=user["email"],
                subject="HPC Predictive Monitoring Dashboard - Login Verification",
                html_content=f"<p>Your login verification code is:</p><h1>{escape(otp)}</h1><p>This code expires in 5 minutes.</p>",
                text_content=f"Your login verification code is {otp}. It expires in 5 minutes.",
            )
        except (ValueError, EmailDeliveryError):
            raise HTTPException(status_code=502, detail="Could not deliver the verification email. Use Resend code or contact an administrator for a fresh temporary password.")
        return {"success": True, "first_login": True, "otp_required": True,
                "message": "A verification code has been sent to your email."}

    if not user["email_verified"]:
        raise HTTPException(
            status_code=403,
            detail="Email verification is required before login."
        )

    try:
        otp = issue_otp(
            user_id=user["id"],
            purpose="login"
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=429,
            detail=str(exc)
        )

    subject = "HPC Predictive Monitoring Dashboard - Login Verification"

    html_content = f"""
    <html>
        <body style="font-family: Arial, sans-serif;">
            <h2>HPC Predictive Monitoring Dashboard</h2>
            <p>Your login verification code is:</p>

            <h1 style="letter-spacing: 8px;">{otp}</h1>

            <p>This code expires in 5 minutes.</p>
            <p>If you did not request this code, you can ignore this email.</p>
        </body>
    </html>
    """

    text_content = (
    f"Your HPC Predictive Monitoring Dashboard login code is {otp}. "
    "It expires in 5 minutes."
)

    try:
        send_transactional_email(
            to_email=user["email"],
            subject=subject,
            html_content=html_content,
            text_content=text_content,
        )

    except EmailDeliveryError:
        record_auth_event(
            event_type="login_otp_delivery_failed",
            actor_user_id=user["id"],
            target_email=user["email"],
        )

        raise HTTPException(
            status_code=502,
            detail="Could not deliver the verification email. Please try again later."
        )

    record_auth_event(
        event_type="login_otp_sent",
        actor_user_id=user["id"],
        target_email=user["email"],
    )

    return {
        "success": True,
        "otp_required": True,
        "message": "A verification code has been sent to your registered email."
    }


@router.post("/first-login/password")
def set_first_login_password(payload: FirstLoginPasswordRequest, request: Request, response: Response):
    raw_state = request.cookies.get(FIRST_LOGIN_COOKIE_NAME)
    state = get_first_login_state(raw_state, require_otp=True)
    if not state:
        raise HTTPException(status_code=401, detail="First-time login verification is required.")
    try:
        complete_first_login(raw_state, payload.password)
        session = create_session(state["user_id"])
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    response.delete_cookie(key=FIRST_LOGIN_COOKIE_NAME, path="/", httponly=True, secure=AUTH_COOKIE_SECURE, samesite="lax")
    response.set_cookie(key=AUTH_COOKIE_NAME, value=session["token"], max_age=AUTH_SESSION_HOURS * 3600,
        httponly=True, secure=AUTH_COOKIE_SECURE, samesite="lax", path="/")
    return {"success": True, "authenticated": True, "user": session["user"], "expires_utc": session["expires_utc"]}


@router.get("/first-login/status")
def first_login_status(request: Request):
    state = get_first_login_state(request.cookies.get(FIRST_LOGIN_COOKIE_NAME))
    if not state:
        raise HTTPException(status_code=401, detail="No active first-time login.")
    if not state["email_verified_utc"]:
        stage = "email_otp"
    elif not state["otp_verified_utc"]:
        stage = "otp"
    else:
        stage = "new_password"
    return {"active": True, "stage": stage, "email": state["email"]}


@router.post("/first-login/resend-otp")
def resend_first_login_otp(request: Request):
    state = get_first_login_state(request.cookies.get(FIRST_LOGIN_COOKIE_NAME))
    if not state:
        raise HTTPException(status_code=401, detail="First-time login state is invalid or expired.")
    if not state["email_verified_utc"] or state["otp_verified_utc"]:
        raise HTTPException(status_code=400, detail="A login verification code is not available for this step.")
    try:
        otp = issue_otp(user_id=state["user_id"], purpose="login")
    except ValueError as exc:
        raise HTTPException(status_code=429, detail=str(exc))
    try:
        send_transactional_email(
            to_email=state["email"],
            subject="HPC Predictive Monitoring Dashboard - Login Verification",
            html_content=f"<p>Your login verification code is:</p><h1>{escape(otp)}</h1><p>This code expires in 5 minutes.</p>",
            text_content=f"Your login verification code is {otp}. It expires in 5 minutes.",
        )
    except EmailDeliveryError:
        raise HTTPException(status_code=502, detail="Could not deliver the verification code. Please try again after the resend cooldown.")
    return {"success": True, "message": "A new verification code has been sent."}

@router.post("/logout")
def logout(
    request: Request,
    response: Response,
):
    """Revoke the current server-side session."""
    session_token = request.cookies.get(AUTH_COOKIE_NAME)

    if session_token:
        revoke_session(session_token)

    response.delete_cookie(
        key=AUTH_COOKIE_NAME,
        path="/",
        httponly=True,
        secure=AUTH_COOKIE_SECURE,
        samesite="lax",
    )

    return {"success": True, "message": "Logged out."}
