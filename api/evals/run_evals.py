"""Run the eval dataset against a real LLM and report the pass rate: `make eval` (see the development docs).

Uses its own throwaway database (`<database>_eval`), seeded like `make seed`, and replays recorded evidence instead
of querying the live stack. Exits non-zero when the pass rate is below the dataset's min_pass_rate.
"""

from src.core.scratch_database import recreate_database, use_scratch_database

# Must run before anything reads the settings.
_MAIN_DATABASE_URL = use_scratch_database("eval")

import argparse  # noqa: E402
import asyncio  # noqa: E402
import json  # noqa: E402
import re  # noqa: E402
import secrets  # noqa: E402
import sys  # noqa: E402
from datetime import UTC, datetime  # noqa: E402
from pathlib import Path  # noqa: E402

from evals.eval_runner import CaseResult, evaluate  # noqa: E402
from evals.scoring import load_dataset  # noqa: E402
from src.core.config import settings  # noqa: E402
from src.core.database import engine, session_factory  # noqa: E402
from src.core.exceptions import AppError  # noqa: E402
from src.core.http import http_client  # noqa: E402
from src.core.llm import build_chat_model, build_embeddings  # noqa: E402
from src.core.logging import configure_logging  # noqa: E402
from src.modules.auth.schemas import UserCreate  # noqa: E402
from src.modules.auth.user_service import UserService  # noqa: E402
from src.modules.copilot.checkpointer import close_checkpointer  # noqa: E402
from src.modules.incidents.incident_service import IncidentService  # noqa: E402
from src.modules.incidents.seed import load_seed_incidents  # noqa: E402
from src.modules.knowledge.seed import seed_documents  # noqa: E402

REPORT_DIR = Path(__file__).parent / "reports"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate the copilot against a real LLM.")
    parser.add_argument("--dataset", default="copilot", help="Dataset name under evals/datasets (default: copilot)")
    parser.add_argument("--provider", help="Override LLM_PROVIDER, e.g. to compare providers")
    parser.add_argument("--model", help="Override LLM_MODEL; also used for classification unless --classifier-model")
    parser.add_argument("--classifier-model", help="Model for the classify step")
    parser.add_argument("--case", action="append", default=[], help="Only run this case id (repeatable)")
    return parser.parse_args()


async def main() -> int:
    args = _parse_args()
    # Only warnings: the report is the output.
    configure_logging("WARNING")
    dataset = load_dataset(args.dataset)
    cases = [case for case in dataset.cases if not args.case or case.id in args.case]
    if unknown := set(args.case) - {case.id for case in cases}:
        sys.exit(f"error: unknown case ids {sorted(unknown)}")

    provider = args.provider or settings.llm_provider
    model = args.model or settings.llm_model
    classifier = args.classifier_model or (args.model or settings.llm_classifier_model or settings.llm_model)
    print(f"Evaluating {len(cases)} cases with {provider}:{model} (classifier {classifier})", flush=True)
    try:
        await recreate_database(_MAIN_DATABASE_URL)
        embeddings = build_embeddings()
        await seed_documents(embeddings)
        async with session_factory() as session:
            await IncidentService(session).seed(load_seed_incidents(datetime.now(UTC)))
            actor = await UserService(session).create_superuser(
                UserCreate(email="evals@example.com", password=secrets.token_urlsafe(24))
            )
        results = await evaluate(
            cases,
            actor,
            build_chat_model(model, args.provider),
            build_chat_model(classifier, args.provider),
            embeddings,
        )
    except AppError as exc:
        sys.exit(f"error: {exc.message} {exc.details or ''}; check the LLM_* and EMBEDDING_* settings")
    finally:
        await close_checkpointer()
        await engine.dispose()
        await http_client.aclose()

    pass_rate = sum(result.passed for result in results) / len(results)
    _print_report(results, pass_rate, dataset.min_pass_rate)
    path = _write_report(results, pass_rate, dataset.min_pass_rate, provider, model, classifier)
    print(f"Full report: {path}")
    return 0 if pass_rate >= dataset.min_pass_rate else 1


def _print_report(results: list[CaseResult], pass_rate: float, min_pass_rate: float) -> None:
    width = max(len(result.id) for result in results)
    print()
    for result in results:
        print(f"{'PASS' if result.passed else 'FAIL'}  {result.id:<{width}}  {result.seconds:>6.1f}s")
        for failure in result.failures:
            print(f"      - {failure}")
    verdict = "OK" if pass_rate >= min_pass_rate else "BELOW THRESHOLD"
    passed = sum(result.passed for result in results)
    print(f"\n{passed}/{len(results)} passed ({pass_rate:.0%}; minimum {min_pass_rate:.0%}): {verdict}")


def _write_report(
    results: list[CaseResult], pass_rate: float, min_pass_rate: float, provider: str, model: str, classifier: str
) -> Path:
    REPORT_DIR.mkdir(exist_ok=True)
    started = datetime.now(UTC)
    path = REPORT_DIR / f"{started:%Y%m%dT%H%M%S}_{re.sub(r'[^A-Za-z0-9.-]+', '-', f'{provider}-{model}')}.json"
    report = {
        "finished_at": started.isoformat(),
        "provider": provider,
        "model": model,
        "classifier_model": classifier,
        "pass_rate": pass_rate,
        "min_pass_rate": min_pass_rate,
        "cases": [result.model_dump(mode="json") for result in results],
    }
    path.write_text(json.dumps(report, indent=2) + "\n")
    return path


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
