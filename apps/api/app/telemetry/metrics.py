"""Custom Prometheus-style metrics, recorded through OpenTelemetry.

The instruments come from the global OpenTelemetry meter, which is a no-op until `init_otel`
installs a real provider (only when OTEL_EXPORTER_OTLP_ENDPOINT is set). So calling these helpers
costs nothing when observability is off. Labels never carry student code, problem text or device
ids.
"""

from typing import Any

from opentelemetry import metrics as otel_metrics


class Metrics:
    """The instruments. Pass a meter to test against an in-memory reader."""

    def __init__(self, meter: Any) -> None:
        self.hint_latency = meter.create_histogram(
            "aporia_hint_latency_seconds",
            unit="s",
            description="Time to produce a guarded hint (grounding, retrieval, model, guard)",
        )
        self.guard_decisions = meter.create_counter(
            "aporia_guard_decisions_total",
            description="Leak-guard decisions by the branch that decided and the outcome",
        )
        self.retrieval_hits = meter.create_counter(
            "aporia_retrieval_hits_total",
            description="Retrievals by kind; outcome=hit when at least one result was found",
        )
        self.llm_cost = meter.create_counter(
            "aporia_llm_cost_usd_total", description="Model spend in US dollars"
        )
        self.sandbox_runs = meter.create_counter(
            "aporia_sandbox_runs_total", description="Execution-grounding runs by outcome"
        )

    def observe_hint(self, seconds: float, level: int, grounded: bool) -> None:
        self.hint_latency.record(seconds, {"level": str(level), "grounded": str(grounded).lower()})

    def observe_guard(self, path: str, leaks: bool) -> None:
        self.guard_decisions.add(
            1, {"path": path or "unknown", "outcome": "leak" if leaks else "pass"}
        )

    def observe_retrieval(self, kind: str, found: int) -> None:
        self.retrieval_hits.add(1, {"kind": kind, "outcome": "hit" if found > 0 else "miss"})

    def observe_cost(self, usd: float, purpose: str) -> None:
        if usd > 0:
            self.llm_cost.add(usd, {"purpose": purpose})

    def observe_sandbox(self, outcome: str) -> None:
        self.sandbox_runs.add(1, {"outcome": outcome})


_metrics: Metrics | None = None


def get_metrics() -> Metrics:
    global _metrics
    if _metrics is None:
        _metrics = Metrics(otel_metrics.get_meter("aporia"))
    return _metrics
