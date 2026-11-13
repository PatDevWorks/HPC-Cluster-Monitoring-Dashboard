
from typing import Any, Dict

from fastapi import Depends, HTTPException, Request

from .auth_service import get_session_user
from .config import AUTH_COOKIE_NAME


def get_current_user(request: Request) -> Dict[str, Any]:
    """
    Validate the dashboard session stored in the HTTP-only cookie.
    """

    session_token = request.cookies.get(AUTH_COOKIE_NAME)

    if not session_token:
        raise HTTPException(
            status_code=401,
            detail="Authentication required.",
        )

    user = get_session_user(session_token)

    if not user:
        raise HTTPException(
            status_code=401,
            detail="Session expired or invalid. Please log in again.",
        )

    return user


def require_roles(*allowed_roles: str):
    """
    Restrict an endpoint to specified database-backed user roles.
    """

    def role_checker(
        current_user: Dict[str, Any] = Depends(get_current_user),
    ):
        if current_user.get("role") not in allowed_roles:
            raise HTTPException(
                status_code=403,
                detail="You do not have permission to perform this action.",
            )

        return current_user

    return role_checker
