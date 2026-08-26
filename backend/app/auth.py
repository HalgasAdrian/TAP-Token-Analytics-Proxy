"""API-key authentication.

Keys are issued by TAP and stored only as a SHA-256 hash; the plaintext is never
logged or persisted.

The TAP key travels in its own header, leaving Authorization free to carry the
caller's provider credential straight through to the upstream. One header for
both would mean TAP forwarding its own key to OpenAI, which would reject it.
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import ApiKey, Project

TAP_KEY_HEADER = "X-TAP-Key"


@dataclass
class AuthContext:
    """Quotas are per key, ownership and reporting per project."""

    project: Project
    api_key: ApiKey


def generate_api_key() -> str:
    return secrets.token_urlsafe(32)


def hash_api_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


async def resolve_auth(api_key: str, session: AsyncSession) -> AuthContext | None:
    """Both must be active, so deactivating a project revokes every key it
    issued."""
    statement = (
        select(ApiKey, Project)
        .join(Project, Project.id == ApiKey.project_id)
        .where(
            ApiKey.key_hash == hash_api_key(api_key),
            ApiKey.active.is_(True),
            Project.active.is_(True),
        )
    )
    row = (await session.execute(statement)).first()
    if row is None:
        return None

    api_key_record, project = row
    return AuthContext(project=project, api_key=api_key_record)


def _read_tap_key(request: Request) -> str:
    key = request.headers.get(TAP_KEY_HEADER)
    if not key:
        raise HTTPException(status_code=401, detail=f"Missing {TAP_KEY_HEADER} header")

    return key


async def require_auth(
    request: Request, session: AsyncSession = Depends(get_session)
) -> AuthContext:
    context = await resolve_auth(_read_tap_key(request), session)
    if context is None:
        raise HTTPException(status_code=401, detail="Invalid API key")

    return context
