"""Admin CLI for provisioning projects and API keys.

Run it inside the api container:

    docker compose exec api python -m app.cli create-project --name "My App"
    docker compose exec api python -m app.cli issue-key --project-id 1 --name prod
    docker compose exec api python -m app.cli list-keys
    docker compose exec api python -m app.cli revoke-key --id 1

Security invariant: a generated key is printed exactly once, at issue time, and
only its SHA-256 hash is stored. There is no way to recover it afterwards — if
it is lost, revoke it and issue another.
"""

from __future__ import annotations

import argparse
import asyncio

from sqlalchemy import select

from app.auth import generate_api_key, hash_api_key
from app.config import settings
from app.db import AsyncSessionLocal, init_db
from app.models import ApiKey, Project


async def create_project(name: str) -> None:
    async with AsyncSessionLocal() as session:
        project = Project(name=name)
        session.add(project)
        await session.commit()
        await session.refresh(project)
        print(f"created project id={project.id} name={project.name!r}")


async def issue_key(project_id: int, name: str, rate_limit: int | None) -> None:
    async with AsyncSessionLocal() as session:
        project = await session.get(Project, project_id)
        if project is None:
            raise SystemExit(f"no project with id={project_id}")

        plaintext = generate_api_key()
        record = ApiKey(
            project_id=project_id,
            name=name,
            key_hash=hash_api_key(plaintext),
            rate_limit=(
                rate_limit
                if rate_limit is not None
                else settings.default_rate_limit
            ),
        )
        session.add(record)
        await session.commit()
        await session.refresh(record)

        print(f"issued key id={record.id} for project {project.name!r}")
        print(f"  rate limit: {record.rate_limit} requests / "
              f"{settings.rate_limit_window_seconds}s")
        print()
        print("  Copy this now — it is not recoverable:")
        print(f"    {plaintext}")
        print()
        print("  Use it as: Authorization: Bearer <key>")


async def list_projects() -> None:
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Project).order_by(Project.id))
        projects = result.scalars().all()

    if not projects:
        print("no projects")
        return
    for project in projects:
        state = "active" if project.active else "inactive"
        print(f"{project.id}\t{project.name}\t{state}\t{project.created_at:%Y-%m-%d}")


async def list_keys(project_id: int | None) -> None:
    async with AsyncSessionLocal() as session:
        statement = select(ApiKey).order_by(ApiKey.id)
        if project_id is not None:
            statement = statement.where(ApiKey.project_id == project_id)
        result = await session.execute(statement)
        keys = result.scalars().all()

    if not keys:
        print("no keys")
        return
    print("id\tproject\tname\tlimit\tstate")
    for key in keys:
        state = "active" if key.active else "revoked"
        print(
            f"{key.id}\t{key.project_id}\t{key.name}\t{key.rate_limit}\t{state}"
        )


async def revoke_key(key_id: int) -> None:
    async with AsyncSessionLocal() as session:
        record = await session.get(ApiKey, key_id)
        if record is None:
            raise SystemExit(f"no key with id={key_id}")
        record.active = False
        await session.commit()
        print(f"revoked key id={key_id}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)

    create = subcommands.add_parser("create-project", help="create a project")
    create.add_argument("--name", required=True)

    issue = subcommands.add_parser("issue-key", help="issue an API key")
    issue.add_argument("--project-id", type=int, required=True)
    issue.add_argument("--name", required=True, help="label, e.g. 'prod' or 'ci'")
    issue.add_argument(
        "--rate-limit",
        type=int,
        default=None,
        help=f"requests per window (default {settings.default_rate_limit})",
    )

    subcommands.add_parser("list-projects", help="list projects")

    keys = subcommands.add_parser("list-keys", help="list issued keys")
    keys.add_argument("--project-id", type=int, default=None)

    revoke = subcommands.add_parser("revoke-key", help="deactivate a key")
    revoke.add_argument("--id", type=int, required=True, dest="key_id")

    return parser


async def dispatch(args: argparse.Namespace) -> None:
    # The CLI may run before the API has ever started (or against a fresh
    # volume), so ensure the schema exists first.
    await init_db()

    if args.command == "create-project":
        await create_project(args.name)
    elif args.command == "issue-key":
        await issue_key(args.project_id, args.name, args.rate_limit)
    elif args.command == "list-projects":
        await list_projects()
    elif args.command == "list-keys":
        await list_keys(args.project_id)
    elif args.command == "revoke-key":
        await revoke_key(args.key_id)


def main() -> None:
    asyncio.run(dispatch(build_parser().parse_args()))


if __name__ == "__main__":
    main()
