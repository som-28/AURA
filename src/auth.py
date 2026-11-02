"""Clerk request authentication for the browser app and FastAPI API."""
from __future__ import annotations

import os
import logging
import re
from typing import Any

from fastapi import Request


logger = logging.getLogger(__name__)
_SECRET_LIKE_TEXT = re.compile(
    r"(?i)(bearer\s+|(?:token|secret|password|cookie|authorization|publishable[_ -]?key|jwt[_ -]?key)[=: ]+)[^\s,;]+"
)


def _safe_auth_detail(value: object) -> str:
    """Keep auth diagnostics useful without exposing credentials or tokens."""
    text = str(value).replace("\n", " ").replace("\r", " ").strip()
    text = _SECRET_LIKE_TEXT.sub(r"\1<redacted>", text)
    return text[:240]


def _auth_request_detail(request: Request) -> str:
    header_present = bool(request.headers.get("authorization"))
    cookie_present = bool(request.cookies.get("__session"))
    return f"authorization_present={header_present} session_cookie_present={cookie_present}"


def clerk_is_configured() -> bool:
    return bool(
        os.getenv("CLERK_PUBLISHABLE_KEY", "").strip()
        and (
            os.getenv("CLERK_SECRET_KEY", "").strip()
            or os.getenv("CLERK_JWT_KEY", "").strip()
        )
    )


def auth_is_required() -> bool:
    return os.getenv("AURA_AUTH_REQUIRED", "true").strip().lower() not in {"0", "false", "no"}


def public_asset_or_route(request: Request) -> bool:
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        return False
    path = request.url.path
    if path in {"/", "/health", "/auth/config", "/auth/bootstrap.js"}:
        return True
    return path.lower().endswith((
        ".css", ".js", ".svg", ".ico", ".png", ".jpg", ".jpeg", ".webp",
        ".woff", ".woff2", ".ttf", ".map",
    ))


def verify_clerk_request(request: Request) -> str | None:
    """Return the signed-in Clerk subject after verifying its session token."""
    publishable_key = os.getenv("CLERK_PUBLISHABLE_KEY", "").strip()
    secret_key = os.getenv("CLERK_SECRET_KEY", "").strip()
    jwt_key = os.getenv("CLERK_JWT_KEY", "").replace("\\n", "\n").strip()
    if not publishable_key or not (secret_key or jwt_key):
        return None

    try:
        from clerk_backend_api import AuthenticateRequestOptions, authenticate_request

        allowed = [
            item.strip()
            for item in os.getenv(
                "CLERK_AUTHORIZED_PARTIES",
                "http://127.0.0.1:8000,http://localhost:8000",
            ).split(",")
            if item.strip()
        ]
        options: dict[str, Any] = {
            "authorized_parties": allowed,
            "accepts_token": ["session_token"],
        }
        if secret_key:
            options["secret_key"] = secret_key
        if jwt_key:
            options["jwt_key"] = jwt_key
        state = authenticate_request(request, AuthenticateRequestOptions(**options))
        if not state.is_signed_in:
            reason = getattr(state, "reason", None) or "unsigned_request"
            logger.warning(
                "Clerk request was not signed in: reason=%s %s",
                _safe_auth_detail(reason),
                _auth_request_detail(request),
            )
            return None
        user_id = str((state.payload or {}).get("sub") or "").strip()
        if not user_id:
            logger.warning(
                "Clerk request was signed in but had no subject: %s",
                _auth_request_detail(request),
            )
        return user_id or None
    except Exception as error:
        logger.exception(
            "Clerk request authentication failed: exception=%s detail=%s %s",
            type(error).__name__,
            _safe_auth_detail(error),
            _auth_request_detail(request),
        )
        return None
