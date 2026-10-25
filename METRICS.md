# Metrics and PromQL — explained and calculated by hand

This file lists every metric the app exposes, why it exists, and works through the logic of the PromQL used in `monitoring/prometheus/rules.yml` and the Grafana dashboard, using **real values** from this app.

Source of the numbers: [`screenshots/metrics_snapshot.txt`](screenshots/metrics_snapshot.txt), taken after one single-image caption and two bulk jobs (`bulk_demo.zip`, 27 images; `bulk_messy.zip`, 5 images + 6 bad files), all with `num_beams = 1`, laptop on battery.

---

## 1. Custom application metrics (17)

Defined in [`app/metrics.py`](app/metrics.py), exposed on `http://localhost:18000/metrics`.

### Counters — only go up (reset to 0 when the app restarts)

| Metric | Labels | Incremented when | Why it is monitored |
|---|---|---|---|
| `caption_requests_total` | `mode`, `status`, `client_ip`, `session_id` | A user clicks *Generate caption* (1 request) or *Caption all images* (1 request per ZIP) | Who uses the app and how often; carries the client-metadata labels |
| `caption_images_processed_total` | `mode`, `status` | Each image goes through the model | Throughput (images per second) |
| `caption_files_skipped_total` | `reason` | A file inside a ZIP is skipped (`not_an_image`, `corrupt`, `too_large`, `over_limit`, `system_file`) | Input quality; shows bulk mode does not crash on bad files |
| `caption_errors_total` | `stage`, `error_type` | A real failure (`model_load`, `decode`, `zip`, `inference`) | Error rate; `CaptionErrors` alert |

### Gauges — current value, can go up and down

| Metric | Labels | Value | Why it is monitored |
|---|---|---|---|
| `caption_model_loaded` | – | 1 when BLIP is ready, else 0 | Readiness: the app can be reachable while the model is still loading |
| `caption_model_load_seconds` | – | Time taken to load the model at start-up | Cold-start cost after a restart |
| `caption_active_requests` | `mode` | Requests being processed right now | Concurrency |
| `caption_current_batch_images` | – | Images in the running bulk job (0 when idle) | Job size; drives the "bulk job running" annotation |
| `caption_bulk_progress_ratio` | – | 0 → 1 during a bulk job | Progress of a long job, visible to an operator |
| `caption_last_success_timestamp_seconds` | – | Unix time of the last successful caption | Freshness: detects a stuck app |

### Histograms — distributions (`_bucket{le=…}`, `_sum`, `_count`)

| Metric | Labels | Buckets | Why it is monitored |
|---|---|---|---|
| `caption_inference_seconds` | `mode`, `beams` | 0.25, 0.5, 1, 1.5, 2, 3, 4, 6, 8, 12, 16, 30 s | Latency per image; percentiles; cost of beam search |
| `caption_length_words` | `mode` | 3, 5, 7, 9, 11, 13, 15, 20 words | Output quality (found the repetition bug, see §5) |
| `caption_image_megapixels` | `mode` | 0.1 … 24 MP | What users upload |
| `caption_zip_extract_seconds` | – | 0.05 … 10 s | Time spent unzipping, separate from model time |

Buckets were chosen for this workload (BLIP on CPU takes ~0.5–4 s per image), not left at library defaults.

### Summaries — `_sum` and `_count`

| Metric | Labels | Observed value | Why it is monitored |
|---|---|---|---|
| `caption_upload_bytes` | `mode`, `client_ip`, `session_id` | Size of each upload | Data volume per client |
| `caption_request_seconds` | `mode` | End-to-end time per request | What the user actually waits for |

### Info — static labels

| Metric | Labels |
|---|---|
| `caption_build_info` | `app_version`, `model`, `device="cpu"`, `torch_threads`, `torch_version="2.14.1+cpu"`, `transformers_version` |

Proves on `/metrics` that inference runs on CPU only.

**Label cardinality note:** every distinct `(client_ip, session_id)` pair creates new time series. That is fine for a demo with a few browsers; in production, `session_id` would not be used as a label.

---

## 2. Automatic metrics used

| Metric | Source | Used for |
|---|---|---|
| `process_cpu_seconds_total` | prometheus_client (app process) | CPU used by the app itself |
| `process_resident_memory_bytes` | prometheus_client (app process) | Memory of the app (BLIP model in RAM) |
| `node_cpu_seconds_total` | node_exporter | CPU of the whole machine (`cpu_util` rule, CPU alert) |
| `node_memory_MemTotal_bytes`, `node_memory_MemAvailable_bytes` | node_exporter | Machine RAM used; `LowMemory` alert |
| `node_disk_read_bytes_total`, `node_disk_written_bytes_total` | node_exporter | Disk I/O panel |
| `up` | Prometheus (per scrape target) | "App reachable" panel; `CaptionAppDown` alert |
| `ALERTS` | Prometheus | "Firing alerts" panel |

---

## 3. PromQL building blocks — worked by hand

### 3.1 `rate()` on a counter → per-second speed

`rate(counter[w])` = (last value − first value in the window) ÷ window length.

**Throughput** — recording rule `caption:images_processed:rate1m`:

```
sum by (mode) (rate(caption_images_processed_total{status="success"}[1m]))
```

The `bulk_demo.zip` job captioned 27 images in 45.1 s. When the 1-minute window covers the whole job, the counter increased by 27 within 60 s:

```
rate = 27 / 60 s = 0.45 images/s
```

The throughput panel peaked at **0.458 images/s** (≈ 27.5 images per 60 s), matching this. While the job runs, the true speed is 27 / 45.1 s = 0.60 images/s; the 1-minute window averages it with the idle seconds around the job.

**CPU cores busy** — recording rule `cpu_util` (from the course sample):

```
sum by (mode) (rate(node_cpu_seconds_total{mode=~"system|user"}[30s]))
```

`node_cpu_seconds_total` counts the seconds each core has spent in each mode since boot (e.g. `cpu="0", mode="idle"` = 53 745.06 s ≈ 15 h). Its rate is "CPU-seconds per second", i.e. the number of cores busy. During the bulk job the panel showed **8.68** cores in user mode, so over the 30 s window:

```
increase in user CPU-seconds (all cores) = 8.68 × 30 s ≈ 260 s
```

The app's own `rate(process_cpu_seconds_total{job="python_app"}[30s])` peaked at **7.98 cores** (≈ 239 CPU-seconds in 30 s), so the captioning app explains ~92 % of the machine's user CPU at that moment (7.98 / 8.68). This is the system-vs-application corroboration on the dashboard.

### 3.2 `increase()` on a counter → how many in a window

`increase(counter[w])` = rate × window, i.e. the count in that window.

**Requests per minute** panel: `sum by (client_ip, mode) (increase(caption_requests_total[1m]))`.
Snapshot: `caption_requests_total{client_ip="localhost", mode="bulk", session_id="ba447a0f"} = 2`. If both bulk jobs fall inside the same minute, the panel shows 2 for `localhost · bulk`, otherwise 1 at each job.

**Errors (last 15 min)**: `sum(increase(caption_errors_total[15m])) or on() vector(0)`. No errors occurred in the snapshot, so the counter series has no samples; `or on() vector(0)` turns "no data" into **0**.

### 3.3 `_sum / _count` on a histogram or summary → average

| Quantity | Calculation (snapshot values) | Result |
|---|---|---|
| Mean inference time (bulk) | 53.3497 s ÷ 32 | **1.67 s / image** |
| Mean inference time (single) | 1.5607 s ÷ 1 | **1.56 s** |
| Mean caption length (bulk) | 266 words ÷ 32 | **8.3 words** |
| Mean input image size (bulk) | 16.2672 MP ÷ 32 | **0.51 MP** |
| Mean ZIP extraction time | 0.4781 s ÷ 2 | **0.24 s / ZIP** |
| Mean bulk upload size | 2 187 704 B ÷ 2 | **≈ 1.09 MB / ZIP** |
| Total bulk request time | `_sum` = 54.11 s | = 45.1 s (demo) + 9.0 s (messy), as shown in the app |

The dashboard uses the same idea over a time window, e.g. *Average end-to-end request time*:
`rate(caption_request_seconds_sum[5m]) / rate(caption_request_seconds_count[5m])` (seconds per request in the last 5 minutes), and *Runtime info* uses the all-time version `sum(…_sum) / sum(…_count)`.

### 3.4 Reading cumulative histogram buckets

Bucket counters are **cumulative**: `le="2.0"` counts every observation ≤ 2 s. Per-bucket counts are differences.

Bulk `caption_inference_seconds` (snapshot):

| `le` | cumulative count | images in this bucket |
|---|---|---|
| 1.0 | 0 | – |
| 1.5 | 4 | 4 (1.0–1.5 s) |
| 2.0 | 31 | 31 − 4 = **27** (1.5–2.0 s) |
| 3.0 | 32 | 32 − 31 = 1 (2.0–3.0 s) |
| +Inf | 32 | 0 |

So 27 of 32 images took 1.5–2.0 s. This is exactly what the latency heatmap shows (dark cells in the 1.5–2 s row).

### 3.5 `histogram_quantile()` → percentiles

Recording rules:

```
caption:inference_seconds:p95_1m = histogram_quantile(0.95, sum by (le, mode) (rate(caption_inference_seconds_bucket[1m])))
caption:inference_seconds:p50_1m = histogram_quantile(0.50, sum by (le, mode) (rate(caption_inference_seconds_bucket[1m])))
```

Method: find the bucket that contains the target rank, then interpolate linearly inside it.

**p95 (bulk, 32 observations):**
1. Target rank = 0.95 × 32 = **30.4**
2. Cumulative counts: `le=1.5` → 4, `le=2.0` → 31, so rank 30.4 is in the **1.5–2.0 s** bucket (27 images)
3. Interpolate: 1.5 + (30.4 − 4) / (31 − 4) × (2.0 − 1.5) = 1.5 + 26.4 / 27 × 0.5 = **1.99 s**

**p50 (bulk):**
1. Target rank = 0.50 × 32 = **16**
2. Also in the 1.5–2.0 s bucket
3. 1.5 + (16 − 4) / 27 × 0.5 = **1.72 s**

Grafana showed **p95 = 1.98 s** and **p50 = 1.75 s**. The small difference is expected: the recording rule uses only the last 1 minute (`rate(...[1m])`), which covered mainly the 27-image demo job, while the hand calculation uses all 32 bulk images.

`histogram_quantile` assumes values are spread evenly inside a bucket, so its accuracy depends on bucket boundaries; dense buckets around 1–2 s were chosen for that reason.

---

## 4. Alert rules — logic and observed behaviour

| Alert | Expression | Logic | Observed |
|---|---|---|---|
| `CaptionAppDown` (critical) | `up{job="python_app"} == 0` for 5 s | Prometheus sets `up = 0` when it cannot scrape `:18000` | App stopped → target DOWN ("connection refused"), alert fired, re-sent every minute (`repeat_interval: 1m`), resolved on restart ([`09_alert_receiver.png`](screenshots/09_alert_receiver.png)) |
| `CaptionModelNotLoaded` (critical) | `caption_model_loaded == 0` for 10 s | The metrics server starts before BLIP loads | Not fired: model loads in ~3 s (`caption_model_load_seconds = 2.76`), shorter than the 10 s `for` |
| `CaptionErrors` (warning) | `sum by (stage) (increase(caption_errors_total[1m])) > 0` | Any error in the last minute | Not fired: 0 errors (skipped files are not errors) |
| `HighInferenceLatency` (warning / critical) | p95 > 4 s / p95 > 8 s for 10 s | Normal p95 ≈ 2 s, so 4 s ≈ 2× normal | Not fired: p95 = 1.98 s. If both fire, the inhibit rule mutes the warning |
| `CPUMoreThan200Percent` (warning) | `cpu_util{mode="user"} > 2` for 5 s | More than 2 cores busy in user mode | Fired during both bulk jobs (8.68 > 2), resolved after each ([`07`](screenshots/07_alert_firing_prometheus.png), [`08`](screenshots/08_alertmanager.png), [`09`](screenshots/09_alert_receiver.png)) |
| `LowMemory` (warning) | `node:memory_available:ratio < 0.10` for 30 s | `MemAvailable / MemTotal` below 10 % | Not fired: the app uses a flat ~1.9 GB |

---

## 5. Findings from the metrics

1. **Repetition bug found and fixed with a metric.** In an earlier run, `caption_length_words_bucket{le="20.0"}` was 30 while `le="+Inf"` was 32: two captions had more than 20 words. They were "a gi gi gi …" loops on giraffe images (greedy decoding repeating a sub-word token until the 30-token limit). After adding `repetition_penalty` and `no_repeat_ngram_size`, the snapshot shows `le="20.0"` = `le="+Inf"` = 32: no runaway captions.
2. **Power state changes latency.** The same 27-image job took 23.0 s plugged in (0.85 s/image) and 45.1 s on battery (1.67 s/image), visible directly in the latency histogram. This is why the latency alert threshold (4 s) has headroom above normal.
3. **The app causes the CPU spike.** During bulk jobs the app process uses ~8 cores out of ~8.7 busy machine cores (§3.1), while its memory stays flat at ~1.9 GB because images are processed one at a time.
4. **Unzipping is not a bottleneck.** ZIP extraction averages 0.24 s against ~45 s of inference for 27 images, so bulk time is almost entirely model time.