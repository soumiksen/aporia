import subprocess
import sys
import textwrap
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.trace import ProxyTracerProvider

from app.api.hint import get_generator
from app.config import Settings
from app.guard.llm_judge import get_judge
from app.main import app
from app.telemetry.metrics import Metrics, get_metrics
from app.telemetry.otel import init_otel, otel_enabled
from tests.test_hint_ladder_guard import CLEAN, NONE, ScriptedGenerator, ScriptedJudge, ask

API_DIR = Path(__file__).resolve().parents[1]


def collect(reader: InMemoryMetricReader) -> dict[str, list[Any]]:
    """metric name -> data points."""
    out: dict[str, list[Any]] = {}
    data = reader.get_metrics_data()
    for rm in data.resource_metrics if data else []:
        for sm in rm.scope_metrics:
            for metric in sm.metrics:
                out[metric.name] = list(metric.data.data_points)
    return out


@pytest.fixture
def instruments():
    reader = InMemoryMetricReader()
    provider = MeterProvider(metric_readers=[reader])
    return Metrics(provider.get_meter("test")), reader


def test_every_metric_is_recorded_with_its_labels(instruments) -> None:
    metrics, reader = instruments
    metrics.observe_hint(1.5, 2, True)
    metrics.observe_guard("classifier_pass", False)
    metrics.observe_guard("judge", True)
    metrics.observe_retrieval("notes", 3)
    metrics.observe_retrieval("notes", 0)
    metrics.observe_cost(0.002, "hint")
    metrics.observe_cost(0.0, "hint")  # free calls add nothing
    metrics.observe_sandbox("failure_found")
    data = collect(reader)
    assert set(data) == {
        "aporia_hint_latency_seconds", "aporia_guard_decisions_total",
        "aporia_retrieval_hits_total", "aporia_llm_cost_usd_total", "aporia_sandbox_runs_total",
    }  # fmt: skip
    (latency,) = data["aporia_hint_latency_seconds"]
    assert latency.count == 1 and latency.sum == 1.5
    assert dict(latency.attributes) == {"level": "2", "grounded": "true"}
    guard = {
        (p.attributes["path"], p.attributes["outcome"]): p.value
        for p in data["aporia_guard_decisions_total"]
    }
    assert guard == {("classifier_pass", "pass"): 1, ("judge", "leak"): 1}
    hits = {p.attributes["outcome"]: p.value for p in data["aporia_retrieval_hits_total"]}
    assert hits == {"hit": 1, "miss": 1}
    (cost,) = data["aporia_llm_cost_usd_total"]
    assert cost.value == pytest.approx(0.002) and cost.attributes["purpose"] == "hint"
    assert dict(data["aporia_sandbox_runs_total"][0].attributes) == {"outcome": "failure_found"}


async def test_hint_endpoint_records_its_metrics(client, instruments, monkeypatch) -> None:
    metrics, reader = instruments
    monkeypatch.setattr("app.api.hint.get_metrics", lambda: metrics)
    app.dependency_overrides[get_generator] = lambda: ScriptedGenerator(CLEAN)
    app.dependency_overrides[get_judge] = lambda: ScriptedJudge(NONE)
    try:
        await ask(client, level=1)
    finally:
        app.dependency_overrides.pop(get_generator, None)
        app.dependency_overrides.pop(get_judge, None)
    data = collect(reader)
    (latency,) = data["aporia_hint_latency_seconds"]
    assert latency.count == 1 and dict(latency.attributes) == {"level": "1", "grounded": "false"}
    assert data["aporia_guard_decisions_total"][0].attributes["path"] == "judge"
    assert (
        dict(data["aporia_sandbox_runs_total"][0].attributes)["outcome"] == "skipped"
    )  # no reference


# ---- off by default ----


def test_otel_is_a_no_op_without_an_endpoint() -> None:
    settings = Settings(otel_exporter_otlp_endpoint="")
    fresh = FastAPI()
    assert otel_enabled(settings) is False
    assert init_otel(fresh, settings) is False
    assert isinstance(trace.get_tracer_provider(), ProxyTracerProvider)  # nothing installed
    assert not getattr(fresh, "_is_instrumented_by_opentelemetry", False)
    get_metrics().observe_hint(0.1, 1, False)  # the helpers cost nothing and never raise
    get_metrics().observe_guard("judge", False)


def run_python(code: str, env_extra: dict[str, str]) -> subprocess.CompletedProcess[str]:
    import os

    env = {**os.environ, "APORIA_LLM_MOCK": "1", "OTEL_EXPORTER_OTLP_ENDPOINT": "", **env_extra}
    return subprocess.run(
        [sys.executable, "-c", textwrap.dedent(code)], cwd=API_DIR, env=env, capture_output=True,
        text=True, timeout=120,
    )  # fmt: skip


def test_startup_without_the_endpoint_installs_nothing() -> None:
    result = run_python(
        """
        from opentelemetry import trace
        from opentelemetry.trace import ProxyTracerProvider
        import app.main  # imports the app exactly as uvicorn does
        assert isinstance(trace.get_tracer_provider(), ProxyTracerProvider)
        print("noop")
        """,
        {},
    )
    assert result.returncode == 0 and "noop" in result.stdout, result.stderr


def test_startup_with_an_endpoint_installs_the_sdk_and_instruments_fastapi() -> None:
    result = run_python(
        """
        from opentelemetry import trace
        import app.main
        from opentelemetry.sdk.trace import TracerProvider
        assert isinstance(trace.get_tracer_provider(), TracerProvider)
        assert getattr(app.main.app, "_is_instrumented_by_opentelemetry", False)
        print("active")
        """,
        {
            "OTEL_EXPORTER_OTLP_ENDPOINT": "http://127.0.0.1:9"
        },  # nothing listens; export fails quietly
    )
    assert result.returncode == 0 and "active" in result.stdout, result.stderr
