import asyncio
from collections.abc import Awaitable, Callable

from httpx import AsyncClient

PASSWORD = "correct-horse-battery"


async def auth_headers(client: AsyncClient, email: str, password: str = PASSWORD) -> dict[str, str]:
    response = await client.post("/v1/auth/token", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def eventually[T](check: Callable[[], Awaitable[T]], within_seconds: float = 90, interval: float = 3) -> T:
    """Retries `check` until it stops raising AssertionError; for telemetry, which arrives seconds after the fact.

    On timeout, re-raises the last assertion so the failure says what was still wrong.
    """
    last_failure: AssertionError | None = None
    try:
        async with asyncio.timeout(within_seconds):
            while True:
                try:
                    return await check()
                except AssertionError as failure:
                    last_failure = failure
                    await asyncio.sleep(interval)
    except TimeoutError:
        if last_failure is None:
            raise
        raise last_failure from None
