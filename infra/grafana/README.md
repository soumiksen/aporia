# Grafana dashboard

`aporia-dashboard.json` is a five-panel overview for the API's OpenTelemetry metrics: hint latency
p50/p95, guard decisions by path and outcome, LLM cost per hour, retrieval hit rate, and sandbox
runs by outcome.

## Use it
```
docker compose -f infra/docker-compose.yml --profile observability up -d lgtm
# run the API with the OTLP endpoint (Grafana's all-in-one image listens on 4318):
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318 uv run uvicorn app.main:app
```
Open http://localhost:3000 (login `admin` / `admin`), then Dashboards > New > Import and upload
`aporia-dashboard.json`, choosing the Prometheus data source when asked.

## Verification status
Verified: the JSON was imported into a running `grafana/otel-lgtm` container through Grafana's
HTTP API (the import succeeded and all 5 panels were stored), the API was run with
`OTEL_EXPORTER_OTLP_ENDPOINT` set and served hints, and every panel query was executed against the
bundled Prometheus and returned series (the metric names are `aporia_hint_latency_seconds_*`,
`aporia_guard_decisions_total`, `aporia_retrieval_hits_total`, `aporia_llm_cost_usd_total`,
`aporia_sandbox_runs_total`).

**Not verified:** how the panels *look* (layout, colours, units) in a browser, and anything with real
traffic or a real model: the run used the mock model, so the cost panel only showed values emitted by
a separate script. Treat the visuals as unverified until someone has opened it.
