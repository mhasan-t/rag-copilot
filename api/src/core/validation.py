import re
from typing import Annotated

from pydantic import StringConstraints

from src.core.exceptions import InvalidInputError

# Service names are substituted into PromQL/LogQL/TraceQL; restricting the alphabet makes injection impossible.
SERVICE_NAME_PATTERN = r"^[a-z0-9][a-z0-9_.-]{0,62}$"

type ServiceName = Annotated[str, StringConstraints(pattern=SERVICE_NAME_PATTERN)]


def require_service_name(name: str) -> str:
    """For internal callers (e.g. LLM tool calls) that don't pass through request validation."""
    if not re.fullmatch(SERVICE_NAME_PATTERN, name):
        raise InvalidInputError("Invalid service name", details={"service": name})
    return name
