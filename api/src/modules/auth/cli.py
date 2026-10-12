"""Create a superuser: `python -m src.modules.auth.cli EMAIL`, prompting for the password."""

import argparse
import asyncio
import getpass
import sys

from pydantic import ValidationError

from src.core.config import settings
from src.core.database import engine, session_factory
from src.core.exceptions import AppError
from src.core.logging import configure_logging
from src.modules.auth.schemas import UserCreate, UserRead
from src.modules.auth.user_service import UserService


async def create_superuser(email: str, password: str) -> UserRead:
    try:
        async with session_factory() as session:
            return await UserService(session).create_superuser(UserCreate(email=email, password=password))
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a superuser account.")
    parser.add_argument("email")
    email = parser.parse_args().email

    password = getpass.getpass("Password: ")
    if password != getpass.getpass("Password (again): "):
        sys.exit("error: passwords do not match")

    configure_logging(settings.log_level)
    # There is no API error handler here, so expected failures become a clean message and exit code.
    try:
        user = asyncio.run(create_superuser(email, password))
    except ValidationError as exc:
        sys.exit("error: " + "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors()))
    except AppError as exc:
        sys.exit(f"error: {exc.message}")
    print(f"Superuser {user.email} created.")


if __name__ == "__main__":
    main()
