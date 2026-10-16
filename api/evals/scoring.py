"""The eval dataset's schema and how a finished run is checked against a case."""

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict

from src.core.config import ActionName
from src.modules.copilot.schemas import RunRead, RunStepRead

DATASET_DIR = Path(__file__).parent / "datasets"


class Expectations(BaseModel):
    """What a case checks. Fields left out aren't checked; `service: null` checks that no service was picked."""

    model_config = ConfigDict(extra="forbid")

    category: Literal["investigate", "knowledge", "out_of_scope"] | None = None
    service: str | None = None
    tools: list[str] = []
    mentions: list[list[str]] = []
    action: ActionName | Literal["none"] | None = None


class EvalCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    question: str
    scenario: str | None = None
    expect: Expectations


class Dataset(BaseModel):
    model_config = ConfigDict(extra="forbid")

    min_pass_rate: float
    cases: list[EvalCase]


def load_dataset(name: str) -> Dataset:
    return Dataset.model_validate(yaml.safe_load((DATASET_DIR / f"{name}.yaml").read_text()))


def score(case: EvalCase, run: RunRead, steps: list[RunStepRead]) -> list[str]:
    """Every way the run fell short of the case; an empty list means it passed."""
    if run.status == "failed":
        return [f"run failed: {run.error}"]

    expect = case.expect
    classification = run.classification or {}
    failures = []
    if expect.category is not None and classification.get("category") != expect.category:
        failures.append(f"category: expected {expect.category}, got {classification.get('category')}")
    if "service" in expect.model_fields_set and classification.get("service") != expect.service:
        failures.append(f"service: expected {expect.service}, got {classification.get('service')}")

    called = {step.tool_name for step in steps if step.node == "gather_evidence" and step.tool_name}
    if missing := sorted(set(expect.tools) - called):
        failures.append(f"tools not called: {missing}")

    text = _answer_text(run).lower()
    for group in expect.mentions:
        if not any(word.lower() in text for word in group):
            failures.append(f"answer mentions none of {group}")

    if expect.action is not None:
        failures.extend(_check_action(expect.action, run))
    return failures


def _check_action(expected: str, run: RunRead) -> list[str]:
    proposal = run.remediation
    proposed = proposal.action if proposal else "none"
    if proposed != expected:
        return [f"action: expected {expected}, got {proposed}"]
    if proposal and (run.status != "awaiting_approval" or proposal.status != "proposed"):
        return [f"action should wait for approval; run is {run.status}, proposal is {proposal.status}"]
    return []


def _answer_text(run: RunRead) -> str:
    diagnosis: dict[str, Any] = run.diagnosis or {}
    return " ".join([run.answer or "", diagnosis.get("likely_cause", ""), *diagnosis.get("evidence", [])])
