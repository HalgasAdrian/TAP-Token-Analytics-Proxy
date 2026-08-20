"""Access control for the dashboard and the metrics API.

These endpoints return aggregates only — no metrics response contains a request
or response body — but they still describe traffic, spend, and failure rates, so
they are not public once a credential is configured.

Two credentials, because there are two kinds of caller:

* ``METRICS_TOKEN`` as a bearer token, for scripts and scheduled jobs.
* ``DASHBOARD_PASSWORD`` over HTTP Basic, for the browser. Basic is what lets
  the dashboard authenticate without shipping a secret inside its own bundle —
  the browser prompts and then attaches the credential to same-origin requests
  automatically.

With neither set, access is open and startup logs a warning.
"""

from __future__ import annotations

import base64
import secrets

from fastapi import HTTPException, Request, status

from app.config import settings

UNAUTHORIZED_HEADERS = {"WWW-Authenticate": 'Basic realm="TAP"'}


def _constant_time_match(presented: str, expected: str) -> bool:
    if not expected or not presented:
        return False
    return secrets.compare_digest(presented, expected)


def _bearer_token(request: Request) -> str:
    header = request.headers.get("Authorization", "")
    return header.removeprefix("Bearer ") if header.startswith("Bearer ") else ""


def _basic_password(request: Request) -> str:
    """The password half of a Basic header; the username is not checked."""
    header = request.headers.get("Authorization", "")
    if not header.startswith("Basic "):
        return ""
    try:
        decoded = base64.b64decode(header.removeprefix("Basic "), validate=True)
        _, _, password = decoded.decode().partition(":")
    except (ValueError, UnicodeDecodeError):
        return ""
    return password


def access_is_configured() -> bool:
    return bool(settings.metrics_token or settings.dashboard_password)


def is_authorised(request: Request) -> bool:
    if not access_is_configured():
        return True
    return _constant_time_match(
        _bearer_token(request), settings.metrics_token
    ) or _constant_time_match(_basic_password(request), settings.dashboard_password)


def require_metrics_access(request: Request) -> None:
    if not is_authorised(request):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid credentials",
            headers=UNAUTHORIZED_HEADERS,
        )
