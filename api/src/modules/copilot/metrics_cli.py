"""Live copilot metrics in the terminal: `python -m src.modules.copilot.metrics_cli` (Ctrl-C to stop).

Runs the Copilot Grafana dashboard's queries against Prometheus. The API exports metrics every 10 s, so values lag
by up to that much.
"""

import asyncio
import math
import sys
from datetime import datetime

from src.core.config import settings
from src.core.exceptions import AppError
from src.core.http import request_json

REFRESH_SECONDS = 5

# Title -> PromQL, kept in step with config/grafana/dashboards/copilot.json. Each result series is one line.
_PANELS = {
    "Runs by outcome (last 5 min)": "sum by (status) (increase(copilot_runs_total[5m]))",
    "Remediation events (last 5 min)": "sum by (event, risk) (increase(copilot_remediation_events_total[5m]))",
    "Step errors (last 5 min)": (
        'sum by (node, tool) (increase(copilot_step_duration_milliseconds_count{error="true"}[5m]))'
    ),
    "Node latency p95 (ms)": (
        'histogram_quantile(0.95, sum by (le, node) (rate(copilot_step_duration_milliseconds_bucket{tool=""}[5m])))'
    ),
    "LLM call latency p95 (ms)": (
        'histogram_quantile(0.95, sum by (le, node) (rate(copilot_step_duration_milliseconds_bucket{tool="llm"}[5m])))'
    ),
    "LLM tokens per minute": "sum by (node, type) (rate(copilot_llm_tokens_total[5m])) * 60",
}


async def _query(promql: str) -> list[dict]:
    body = await request_json(
        "GET", f"{settings.prometheus_url.rstrip('/')}/api/v1/query", upstream="prometheus", params={"query": promql}
    )
    return body["data"]["result"]


async def render() -> str:
    results = await asyncio.gather(*(_query(promql) for promql in _PANELS.values()))
    lines = [f"Copilot metrics at {datetime.now():%H:%M:%S}, refreshed every {REFRESH_SECONDS} s (Ctrl-C to stop)"]
    for title, series in zip(_PANELS, results, strict=True):
        lines.append(f"\n{title}")
        # A quantile over zero calls is NaN; like an empty result, it means nothing happened in the window.
        rows = [(s["metric"], float(s["value"][1])) for s in series if not math.isnan(float(s["value"][1]))]
        if not rows:
            lines.append("  no data")
        for labels, value in rows:
            lines.append(f"  {' '.join(f'{k}={v}' for k, v in labels.items()) or 'total':<50} {value:>10.1f}")
    return "\n".join(lines)


async def watch() -> None:
    while True:
        screen = await render()
        # Clear the terminal and redraw from the top, like `watch`.
        print("\033[2J\033[H" + screen, flush=True)
        await asyncio.sleep(REFRESH_SECONDS)


def main() -> None:
    # There is no API error handler here, so expected failures become a clean message and exit code.
    try:
        asyncio.run(watch())
    except KeyboardInterrupt:
        pass
    except AppError as exc:
        sys.exit(f"error: {exc.message} {exc.details or ''}")


if __name__ == "__main__":
    main()
