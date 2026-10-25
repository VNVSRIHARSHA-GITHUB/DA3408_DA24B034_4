# AI prompt usage (PromQL attribution)

- The PromQL in `monitoring/prometheus/rules.yml` and in the Grafana dashboard (`monitoring/grafana/dashboards/caption_app.json`) was generated with AI assistance (Claude, Anthropic). rules.yml carry a comment pointing here.
- Each row lists the query, where it is used, and the prompt it was generated from.
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
| `CaptionModelNotLoaded` (alert) | `caption_model_loaded == 0` | "Not AI generated and written by me " |
| `CaptionErrors` (alert) | `sum by (stage) (increase(caption_errors_total[1m])) > 0` | "Prometheus alert that fires when any errors were counted by caption_errors_total in the last minute" |
| `HighInferenceLatency` warning / critical (alerts) | `caption:inference_seconds:p95_1m > 4  /  > 8` | "Two Prometheus alerts with the same name on the p95 latency recording rule: warning above 4 s and critical above 8 s, so Alertmanager can inhibit the warning while the critical one fires" |
| `CPUMoreThan200Percent` (alert) | `cpu_util{mode="user"} > 2` | "Not AI generated and written by me." |
| `LowMemory` (alert) | `node:memory_available:ratio < 0.10` | "Not AI generated and written by me." |



## 2. Grafana dashboard panels (`monitoring/grafana/dashboards/caption_app.json`)

| Row | Panel | PromQL | Prompt |
|---|---|---|---|
| 1 · Health | App reachable | `max(up{job="python_app"}) or on() vector(0)` | "Grafana stat query: is the python_app scrape target up? Return 0 instead of no data when the series is missing" |
| 1 · Health | Model ready | `max(caption_model_loaded) or on() vector(0)` | "Grafana stat query for the caption_model_loaded gauge that returns 0 when the app is down" |
| 1 · Health | Firing alerts | `count(ALERTS{alertstate="firing"}) or on() vector(0)` | "PromQL that counts the Prometheus alerts currently firing, returning 0 when none" |
| 2 · Throughput & latency | Latency distribution: how many images fell in each inference-time bucket | `sum by (le) (increase(caption_inference_seconds_bucket[30s]))` | "PromQL for a Grafana heatmap of the caption_inference_seconds histogram: images per bucket in each 30 s slice" |
| 2 · Throughput & latency | Requests per minute, by client and mode | `sum by (client_ip, mode) (increase(caption_requests_total[1m]))` | "PromQL for requests per minute from caption_requests_total, split by the client_ip and mode labels" |
| 2 · Throughput & latency | Average inference time by beam width (num_beams) | `sum by (beams) (rate(caption_inference_seconds_sum[5m])) / sum by (beams) (rate(caption_inference_seconds_count[5m]))` | "PromQL for the mean of the caption_inference_seconds histogram over 5 minutes, grouped by the beams label" |
| 3 · Workload | Runtime info: what is running and what it costs to start and feed | `max by (device, model, torch_version) (caption_build_info)`<br>`max(caption_model_load_seconds)`<br>`sum(caption_zip_extract_seconds_sum) / sum(caption_zip_extract_seconds_count)`<br>`sum(caption_image_megapixels_sum) / sum(caption_image_megapixels_count)` | "PromQL for: the device/model/torch_version labels of caption_build_info; the gauge caption_model_load_seconds; the all-time average of the histograms caption_zip_extract_seconds and caption_image_megapixels (sum / count)" |
| 3 · Workload | Upload volume: bytes received per second, by mode | `sum by (mode) (rate(caption_upload_bytes_sum[1m]))` | "PromQL for bytes uploaded per second over 1 minute from the summary caption_upload_bytes, by mode" |
| 3 · Workload | Average end-to-end request time, by mode | `sum by (mode) (rate(caption_request_seconds_sum[5m])) / sum by (mode) (rate(caption_request_seconds_count[5m]))` | "PromQL for the average of the summary caption_request_seconds over 5 minutes, by mode" |
| 4 · System resources | Memory: machine RAM used vs caption-app resident memory | `node_memory_MemTotal_bytes - node_memory_MemAvailable_bytes`<br>`process_resident_memory_bytes{job="python_app"}` | "PromQL for host RAM in use from node_exporter, and the app's resident memory from process_resident_memory_bytes" |


## 3. Bulk-job annotation

| Where | PromQL | Prompt |
|---|---|---|
| Dashboard annotation "Bulk ZIP job running" | `max(caption_current_batch_images) > 0` | "Grafana annotation query that is true while a bulk job is running, using the gauge caption_current_batch_images" |
