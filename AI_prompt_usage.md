# AI prompt usage (PromQL attribution)

This file answers the course's **"Black Box" Metric Rule**: AI may be used to generate PromQL, but every AI-generated query must be attributed with the prompt used.

- The PromQL in `monitoring/prometheus/rules.yml` and in the Grafana dashboard (`monitoring/grafana/dashboards/caption_app.json`) was generated with AI assistance (Claude, Anthropic). Both files carry a comment pointing here.
- Each row lists the query, where it is used, and the prompt it was generated from. Queries taken from the course sample files are marked as such.
- The **logic of every query is calculated by hand**, with real numbers from this app, in [`METRICS.md`](METRICS.md).

## 1. Prometheus rules (`monitoring/prometheus/rules.yml`)

| Rule | PromQL | Prompt / origin |
|---|---|---|
| `cpu_util` (recording) | `sum by (mode) (rate(node_cpu_seconds_total{mode=~"system\|user"}[30s]))` | "Not AI-generated and written by me." |
| `caption:inference_seconds:p95_1m` (recording) | `histogram_quantile(0.95, sum by (le, mode) (rate(caption_inference_seconds_bucket[1m])))` | "PromQL for the 95th percentile of a Prometheus histogram caption_inference_seconds over the last 1 minute, split by the mode label" |
| `caption:inference_seconds:p50_1m` (recording) | `histogram_quantile(0.50, sum by (le, mode) (rate(caption_inference_seconds_bucket[1m])))` | "Just changed 0.95 to 0.5 in the above query" |
| `caption:images_processed:rate1m` (recording) | `sum by (mode) (rate(caption_images_processed_total{status="success"}[1m]))` | "PromQL for images captioned per second over the last 1 minute from the counter caption_images_processed_total, by mode, counting only status=success" |
| `node:memory_available:ratio` (recording) | `node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes` | "Not AI generated,written by me." |
| `CaptionAppDown` (alert) | `up{job="python_app"} == 0` | "Prometheus alert when the python_app scrape target is down for 5 s" |
| `CaptionModelNotLoaded` (alert) | `caption_model_loaded == 0` | "Prometheus alert when the gauge caption_model_loaded is 0 for 10 s" |
| `CaptionErrors` (alert) | `sum by (stage) (increase(caption_errors_total[1m])) > 0` | "Prometheus alert that fires when any errors were counted by caption_errors_total in the last minute" |
| `HighInferenceLatency` warning / critical (alerts) | `caption:inference_seconds:p95_1m > 4  /  > 8` | "Two Prometheus alerts with the same name on the p95 latency recording rule: warning above 4 s and critical above 8 s, so Alertmanager can inhibit the warning while the critical one fires" |
| `CPUMoreThan200Percent` (alert) | `cpu_util{mode="user"} > 2` | "Not AI generated and written by me." |
| `LowMemory` (alert) | `node:memory_available:ratio < 0.10` | "Not AI generated and written by me." |


## 2. Bulk-job annotation

| Where | PromQL | Prompt |
|---|---|---|
| Dashboard annotation "Bulk ZIP job running" | `max(caption_current_batch_images) > 0` | "Grafana annotation query that is true while a bulk job is running, using the gauge caption_current_batch_images" |
