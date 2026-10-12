"""Steady synthetic traffic for the demo payments service, so there is always telemetry to look at."""

import asyncio
import os
import random

import httpx

TARGET_URL = os.environ.get("LOADGEN_TARGET_URL", "http://payments:8000")
REQUESTS_PER_SECOND = float(os.environ.get("LOADGEN_REQUESTS_PER_SECOND", "5"))


async def _send(client: httpx.AsyncClient) -> None:
    # Fire-and-forget: errors are expected (v2 fails on purpose), and the service records them itself.
    try:
        if random.random() < 0.7:
            await client.post("/payments")
        else:
            await client.get(f"/payments/{random.randint(1, 10_000)}")
    except httpx.HTTPError:
        pass


async def main() -> None:
    tasks: set[asyncio.Task] = set()
    async with httpx.AsyncClient(base_url=TARGET_URL, timeout=10) as client:
        # Fixed arrival rate, independent of response time, so a slow version shows up as latency, not lower load.
        while True:
            task = asyncio.create_task(_send(client))
            tasks.add(task)
            task.add_done_callback(tasks.discard)
            await asyncio.sleep(1 / REQUESTS_PER_SECOND)


if __name__ == "__main__":
    asyncio.run(main())
