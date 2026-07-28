from base64 import encode
import hashlib
import secrets

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import Project


def generate_api_key() -> str:
    api_key = secrets.token_urlsafe(32)
    return api_key


def hash_api_key(key: str) -> str:
    hashed_key = hashlib.sha256(key.encode()).hexdigest()
    return hashed_key

async def resolve_project(api_key: str, session: AsyncSession) -> Project | None:
    # ============================================================
    # ASSIGNMENT: A1 API key auth
    # ------------------------------------------------------------
    # Implement: generate a random key, hash keys with SHA-256, look up the
    #            owning Project by key_hash, and enforce a valid key (401 otherwise).
    # Why:       gates the proxy when AUTH_ENABLED=true and attributes usage to a project.
    # Done when: with AUTH_ENABLED=true a request with a valid key resolves its Project
    #            and an invalid/missing key returns HTTP 401.
    # Reference: https://docs.python.org/3/library/secrets.html
    #            https://docs.python.org/3/library/hashlib.html
    #            https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html
    #            https://fastapi.tiangolo.com/tutorial/dependencies/
    #            https://fastapi.tiangolo.com/tutorial/security/
    # ============================================================
    raise NotImplementedError("ASSIGNMENT: A1 API key auth")


async def require_project(
    request: Request, session: AsyncSession = Depends(get_session)
) -> Project:
    # ============================================================
    # ASSIGNMENT: A1 API key auth
    # ------------------------------------------------------------
    # Implement: generate a random key, hash keys with SHA-256, look up the
    #            owning Project by key_hash, and enforce a valid key (401 otherwise).
    # Why:       gates the proxy when AUTH_ENABLED=true and attributes usage to a project.
    # Done when: with AUTH_ENABLED=true a request with a valid key resolves its Project
    #            and an invalid/missing key returns HTTP 401.
    # Reference: https://docs.python.org/3/library/secrets.html
    #            https://docs.python.org/3/library/hashlib.html
    #            https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html
    #            https://fastapi.tiangolo.com/tutorial/dependencies/
    #            https://fastapi.tiangolo.com/tutorial/security/
    # ============================================================
    raise NotImplementedError("ASSIGNMENT: A1 API key auth")
