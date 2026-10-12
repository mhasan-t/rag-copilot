from typing import Any

import httpx

from src.core.exceptions import NotFoundError, UpstreamError

# Shared connection pool for calls to other services (monitoring stack, deployment backends).
http_client = httpx.AsyncClient(timeout=httpx.Timeout(10.0))


async def request_json(method: str, url: str, *, upstream: str, **kwargs: Any) -> Any:
    """JSON request to another service; failures become UpstreamError (502), and 404 becomes NotFoundError.

    `upstream` names the service in error messages, e.g. "prometheus".
    """
    try:
        response = await http_client.request(method, url, **kwargs)
    except httpx.HTTPError as exc:
        raise UpstreamError(f"{upstream} is unreachable", details={"error": type(exc).__name__}) from exc
    if response.status_code == 404:
        raise NotFoundError(f"{upstream}: not found", details={"url": url})
    if response.is_error:
        # The body usually explains the failure (e.g. a query parse error); keep it short in case it's an HTML page.
        raise UpstreamError(f"{upstream} returned {response.status_code}", details={"response": response.text[:500]})
    return response.json()
