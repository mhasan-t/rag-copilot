"""Seed data for the web UI's browser tests: `python -m tests.e2e_seed`, run by Playwright's global setup.

Writes to the dev database, since the UI under test talks to the dev API. Everything it creates is tagged with a
random suffix, so repeated runs don't collide. Runs are created with the scripted LLM (no real model is needed); the
UI then exercises the real API, including approvals that execute against the demo service.

Prints one JSON line: the users' credentials and the ids of the runs.
"""

import asyncio
import json
import secrets
from typing import Any

from src.core.database import engine, session_factory
from src.core.exceptions import AppError
from src.core.http import http_client
from src.modules.auth.schemas import UserCreate, UserRead
from src.modules.auth.user_service import UserService
from src.modules.copilot.checkpointer import close_checkpointer
from src.modules.copilot.run_service import CopilotModels, RunService
from tests.copilot_helpers import classify_as, proposing
from tests.fake_chat_model import ScriptedChatModel
from tests.fake_embeddings import WordHashEmbeddings

PASSWORD = "e2e-password-" + secrets.token_hex(4)
KNOWLEDGE_ANSWER = (
    "Follow **Rolling back a deployment**:\n\n1. Get superuser approval.\n2. Roll back to the previous revision."
)


async def main() -> None:
    tag = secrets.token_hex(3)
    async with session_factory() as session:
        users = UserService(session)
        superuser = await users.create_superuser(UserCreate(email=f"e2e-admin-{tag}@example.com", password=PASSWORD))
        operator = await users.create_user(superuser, UserCreate(email=f"e2e-ops-{tag}@example.com", password=PASSWORD))

    model = ScriptedChatModel(handlers={})
    models = CopilotModels(model, model, WordHashEmbeddings())
    scale = proposing("scale_deployment", replicas=2)
    questions = {
        "high_risk": (f"[{tag}] Why is payments slow?", proposing("rollback_deployment")),
        "low_risk": (f"[{tag}] Is payments under-provisioned?", scale),
        "answered": (f"[{tag}] How do I roll back a deployment?", None),
        "failed": (f"[{tag}] Why is checkout slow?", "fail"),
    }
    runs = {name: await _ask(operator, models, model, question, how) for name, (question, how) in questions.items()}
    users = {"superuser": superuser.email, "operator": operator.email}
    print(json.dumps({"tag": tag, "password": PASSWORD, **users, "runs": runs}))
    await close_checkpointer()
    await engine.dispose()
    await http_client.aclose()


async def _ask(actor: UserRead, models: CopilotModels, model: ScriptedChatModel, question: str, diagnosis: Any) -> str:
    """`diagnosis`: a Diagnosis handler for an investigation, None for a runbook question, "fail" for an LLM outage."""
    if diagnosis == "fail":
        model.handlers = {"Classification": _unreachable}
    elif diagnosis is None:
        model.handlers = {
            "Classification": classify_as("knowledge", service=None),
            "text": lambda _: KNOWLEDGE_ANSWER,
        }
    else:
        model.handlers = {"Classification": classify_as("investigate"), "Diagnosis": diagnosis}
    async with session_factory() as session:
        try:
            return str((await RunService(session).ask(actor, question, models)).id)
        except AppError as exc:
            return str((exc.details or {})["run_id"])


def _unreachable(_prompt: str) -> Any:
    raise ConnectionError("model server down")


if __name__ == "__main__":
    asyncio.run(main())
