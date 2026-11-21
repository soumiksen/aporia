import json
import re
from pathlib import Path

from opentelemetry.sdk.metrics import MeterProvider

from app.telemetry.metrics import Metrics

DASHBOARD = Path(__file__).resolve().parents[3] / "infra" / "grafana" / "aporia-dashboard.json"


def test_dashboard_is_valid_json_with_the_five_expected_panels() -> None:
    dash = json.loads(DASHBOARD.read_text())
    assert dash["uid"] == "aporia-overview" and len(dash["panels"]) == 5
    titles = " ".join(p["title"].lower() for p in dash["panels"])
    for word in ("latency", "guard", "cost", "retrieval", "sandbox"):
        assert word in titles
    ids = [p["id"] for p in dash["panels"]]
    assert len(set(ids)) == len(ids)


def test_every_metric_the_dashboard_queries_is_defined_in_code() -> None:
    """The dashboard may only reference metrics the API really emits (Prometheus adds the
    _bucket/_count/_sum suffixes to the histogram)."""
    provider = MeterProvider()
    defined = {
        name for name in vars(Metrics(provider.get_meter("t"))).values() if hasattr(name, "name")
    }
    names = {m.name for m in defined}  # type: ignore[attr-defined]
    queried = set()
    for panel in json.loads(DASHBOARD.read_text())["panels"]:
        for target in panel["targets"]:
            queried |= set(re.findall(r"aporia_[a-z_]+", target["expr"]))
    base = {re.sub(r"_(bucket|count|sum)$", "", q) for q in queried}
    assert base <= names, base - names
