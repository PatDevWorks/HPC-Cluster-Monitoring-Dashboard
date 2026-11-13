
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from html import escape
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
    create_invitation,
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


class EmailVerificationRequest(BaseModel):
    email: str
    code: str


class ResendVerificationRequest(BaseModel):
    email: str

@router.post("/invitations")
def send_invitation(
    payload: InvitationRequest,
    current_user: dict = Depends(require_roles("super_admin")),
):
    """Create an invitation and email the registration link."""

    try:
        invitation = create_invitation(
            email=payload.email,
            role=payload.role,
            invited_by=current_user["id"],
            validity_hours=payload.validity_hours,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        )

    registration_url = (
        f"{FRONTEND_BASE_URL}/register"
        f"?token={quote(invitation['token'], safe='')}"
    )

    recipient = escape(invitation["email"])
    assigned_role = escape(invitation["role"])
    expiry = escape(invitation["expires_utc"])

    subject = "Invitation - Sol Plaatje A Dev Cluster Dashboard"

    html_content = f"""
    <html>
        <body style="font-family: Arial, sans-serif;">
            <h2>Sol Plaatje A Dev Cluster Dashboard</h2>

            <p>You have been invited to join the HPC dashboard.</p>

            <p><strong>Email:</strong> {recipient}</p>
            <p><strong>Assigned role:</strong> {assigned_role}</p>

            <p>
                <a href="{registration_url}"
                   style="background-color:#1d4ed8;
                          color:white;
                          padding:12px 20px;
                          text-decoration:none;
                          border-radius:5px;">
                    Accept Invitation
                </a>
            </p>

            <p>This invitation expires at {expiry}.</p>
            <p>If you were not expecting this invitation, ignore this email.</p>
        </body>
    </html>
    """

    text_content = (
        "You have been invited to join the Sol Plaatje A Dev Cluster Dashboard. "
        f"Your assigned role is {invitation['role']}. "
        f"Register using this link: {registration_url}. "
        f"Invitation expiry: {invitation['expires_utc']}."
    )

    try:
        send_transactional_email(
            to_email=invitation["email"],
            subject=subject,
            html_content=html_content,
            text_content=text_content,
        )
    except EmailDeliveryError:
        record_auth_event(
            event_type="invitation_email_delivery_failed",
            actor_user_id=current_user["id"],
            target_email=invitation["email"],
        )

        raise HTTPException(
            status_code=502,
            detail=(
                "The invitation was created, but its email could not be delivered. "
                "Create a new invitation to generate a fresh link."
            ),
        )

    record_auth_event(
        event_type="invitation_email_sent",
        actor_user_id=current_user["id"],
        target_email=invitation["email"],
    )

    return {
        "success": True,
        "message": "Invitation sent successfully.",
        "email": invitation["email"],
        "role": invitation["role"],
        "expires_utc": invitation["expires_utc"],
    }
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

    subject = "Verify your email - Sol Plaatje A Dev Cluster Dashboard"

    html_content = f"""
    <html>
        <body style="font-family: Arial, sans-serif;">
            <h2>Sol Plaatje A Dev Cluster Dashboard</h2>

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
def verify_email(payload: EmailVerificationRequest):
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

    subject = "Your email verification code - Sol Plaatje A Dev Cluster Dashboard"

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
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired verification code."
        )

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
@router.post("/login")
def login(payload: LoginRequest):
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

        raise HTTPException(
            status_code=401,
            detail="Invalid email address or password."
        )

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

    subject = "Sol Plaatje A Dev Cluster Dashboard - Login Verification"

    html_content = f"""
    <html>
        <body style="font-family: Arial, sans-serif;">
            <h2>Sol Plaatje A Dev Cluster Dashboard</h2>
            <p>Your login verification code is:</p>

            <h1 style="letter-spacing: 8px;">{otp}</h1>

            <p>This code expires in 5 minutes.</p>
            <p>If you did not request this code, you can ignore this email.</p>
        </body>
    </html>
    """

    text_content = (
    f"Your Sol Plaatje A Dev Cluster Dashboard login code is {otp}. "
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
