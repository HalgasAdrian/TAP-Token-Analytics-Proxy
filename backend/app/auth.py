"""API-key authentication (A1).

Keys are issued by TAP, shown to the operator once, and stored only as a
SHA-256 hash. Authentication resolves a presented key to the owning project.

Security invariant: the plaintext key is never logged or persisted — only
`hash_api_key` output reaches the database.
"""

import hashlib
import secrets
from dataclasses import dataclass

from fastapi import Depends, Request, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models import ApiKey

from app.db import get_session
from app.models import Project


@dataclass
class AuthContext:
    """The identities behind an authenticated request.

    Carries the ApiKey as well as the Project because quotas are per key
    (`ApiKey.rate_limit`) while ownership and reporting are per project.
    """

    project: Project
    api_key: ApiKey


def generate_api_key() -> str:
    api_key = secrets.token_urlsafe(32)
    return api_key


def hash_api_key(key: str) -> str:
    hashed_key = hashlib.sha256(key.encode()).hexdigest()
    return hashed_key


async def resolve_auth(api_key: str, session: AsyncSession) -> AuthContext | None:
    """Resolve a plaintext key to its active key + project, or None.

    Both records must be active: deactivating a project revokes every key it
    issued, without having to walk the keys individually.
    """
    key_hash = hash_api_key(api_key)

    statement = (
        select(ApiKey, Project)
        .join(Project, Project.id == ApiKey.project_id)
        .where(
            ApiKey.key_hash == key_hash,
            ApiKey.active.is_(True),
            Project.active.is_(True),
        )
    )
    result = await session.execute(statement)
    row = result.first()

    if row is None:
        return None

    api_key_record, project = row
    return AuthContext(project=project, api_key=api_key_record)


async def resolve_project(api_key: str, session: AsyncSession) -> Project | None:
    """Resolve a plaintext key to its owning project, or None."""
    context = await resolve_auth(api_key, session)
    return context.project if context is not None else None


def _read_bearer_token(request: Request) -> str:
    """Extract the bearer token, or raise 401.

    The header value itself is never included in an error detail — an error
    message is a place key material can leak into logs.
    """
    auth_header = request.headers.get("Authorization")
    if auth_header is None:
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid Authorization header")

    return auth_header.removeprefix("Bearer ")


async def require_auth(
    request: Request, session: AsyncSession = Depends(get_session)
) -> AuthContext:
    """Authenticate the request, or raise 401."""
    api_key = _read_bearer_token(request)
    context = await resolve_auth(api_key, session)
    if context is None:
        raise HTTPException(status_code=401, detail="Invalid API key")

    return context


async def require_project(
    request: Request, session: AsyncSession = Depends(get_session)
) -> Project:
    """Authenticate the request and return only the owning project."""
    context = await require_auth(request, session)
    return context.project
