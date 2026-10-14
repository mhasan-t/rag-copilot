"""Throwaway copies of the database for tests and evals, so they never touch dev data."""

import asyncio
import os

import asyncpg
from sqlalchemy import make_url


def use_scratch_database(suffix: str) -> str:
    """Points DATABASE_URL at `<database>_<suffix>`; returns the original URL.

    Call before anything imports src.core.config, which reads the settings once.
    """
    original = os.environ["DATABASE_URL"]
    url = make_url(original)
    os.environ["DATABASE_URL"] = url.set(database=f"{url.database}_{suffix}").render_as_string(hide_password=False)
    return original


async def recreate_database(original_url: str) -> None:
    """Drops and recreates the scratch database (the current DATABASE_URL), then applies every migration."""
    original, scratch = make_url(original_url), make_url(os.environ["DATABASE_URL"])
    if scratch.database == original.database:
        raise RuntimeError("Refusing to recreate the main database; call use_scratch_database first")
    # Connect to the original database to drop and create the scratch one; you can't drop the one you're in.
    admin = await asyncpg.connect(original.set(drivername="postgresql").render_as_string(hide_password=False))
    try:
        await admin.execute(f'DROP DATABASE IF EXISTS "{scratch.database}" WITH (FORCE)')
        await admin.execute(f'CREATE DATABASE "{scratch.database}"')
    finally:
        await admin.close()

    migration = await asyncio.create_subprocess_exec(
        "alembic", "upgrade", "head", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
    )
    output, _ = await migration.communicate()
    if migration.returncode != 0:
        raise RuntimeError(f"Migrations failed:\n{output.decode()}")
