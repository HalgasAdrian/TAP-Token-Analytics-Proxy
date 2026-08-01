import hashlib
import secrets

from fastapi import Depends, Request, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models import ApiKey

from app.db import get_session
from app.models import Project


def generate_api_key() -> str:
    api_key = secrets.token_urlsafe(32)
    return api_key


def hash_api_key(key: str) -> str:
    hashed_key = hashlib.sha256(key.encode()).hexdigest()
    return hashed_key

async def resolve_project(api_key: str, session: AsyncSession) -> Project | None:
    key_hash = hash_api_key(api_key)

    statement = select(ApiKey).where(
        ApiKey.key_hash == key_hash,
        ApiKey.active == True,
    )
    result = await session.execute(statement)
    api_key_record = result.scalar_one_or_none()

    if api_key_record is None:
        return None

    statement = select(Project).where(Project.id == api_key_record.project_id)
    result = await session.execute(statement)
    project = result.scalar_one_or_none()

    if project is None:
        return None

    return project

async def require_project(
    request: Request, session: AsyncSession = Depends(get_session)
) -> Project:
    auth_header = request.headers.get("Authorization")
    if auth_header is None:
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail = "Invalid Authorization header")

    api_key = auth_header.removeprefix("Bearer ")
    project = await resolve_project(api_key, session)
    if project is None:
        raise HTTPException(status_code=401, detail="Invalid API key")

    return project
