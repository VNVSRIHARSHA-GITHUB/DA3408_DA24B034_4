# DA3408 Assignment 4 — Application Monitoring with Prometheus & Grafana

CPU-only image captioning app (Streamlit + BLIP) instrumented with `prometheus_client`, with node_exporter, Prometheus alerting (Alertmanager) and a Grafana dashboard.

**Demo video (dashboard at 5 s refresh):**  https://drive.google.com/file/d/1umxdgqUcF3EJwNnJo4IZIKYh921m7aai/view?usp=sharing

---

## Layout

```
DA3408_DA24B034_4/
├── README.md
├── METRICS.md                    # Every metric + PromQL, with hand calculations
├── AI_prompt_usage.md            # Prompts used for AI-generated PromQL
├── ai_usage.md                   # AI usage disclosure
├── requirements.txt              # Pinned Python dependencies (CPU-only torch)
├── .streamlit/config.toml        # Headless mode, 50 MB upload limit
│
├── app/                          # Streamlit captioning app
│   ├── main.py                   # UI (single + bulk ZIP), metric updates
│   ├── metrics.py                # All Prometheus metrics + /metrics server (:18000)
│   ├── captioner.py              # BLIP model on CPU
│   ├── bulk.py                   # Safe image / ZIP loading (skips bad files)
│   └── client_info.py            # client_ip and session_id labels
│
├── monitoring/
│   ├── docker-compose.yml        # node_exporter, Prometheus, Alertmanager, receiver, Grafana
│   ├── prometheus/
│   │   ├── prometheus.yml        # Scrape jobs: node, python_app, alertmanager, prometheus
│   │   └── rules.yml             # 5 recording rules + 7 alert rules
│   ├── alertmanager/
│   │   └── alertmanager.yml      # Routing to the local receiver, inhibit rule
│   └── grafana/
│       ├── provisioning/         # Auto-adds the Prometheus data source and the dashboard
│       └── dashboards/
│           └── caption_app.json  # Grafana dashboard JSON export (20 panels)
│
├── tools/
│   └── alert_receiver.py         # Webhook receiver for Alertmanager notifications
│
├── sample_data/                  # Test images and ZIPs
└── screenshots/                  # Evidence (see Screenshots)
```

---

## Screenshots

| File | Shows |
|---|---|
| [`01_single.png`](screenshots/01_single.png) | Single image mode: one image captioned on CPU |
| [`02_bulk_messy.png`](screenshots/02_bulk_messy.png) | Bulk ZIP with 5 images + 6 bad files: bad files skipped with a reason, no crash |
| [`03_bulk_demo.png`](screenshots/03_bulk_demo.png) | Bulk ZIP of 27 images captioned, shown as a gallery |
| [`04a_metrics_counters_gauges.png`](screenshots/04a_metrics_counters_gauges.png) | `/metrics` page: Counters with `client_ip` / `session_id` labels, and Gauges |
| [`04b_metrics_histogram_summary.png`](screenshots/04b_metrics_histogram_summary.png) | `/metrics` page: Histogram buckets, Summaries and the Info metric (`device="cpu"`) |
| [`05_prometheus_targets.png`](screenshots/05_prometheus_targets.png) | Prometheus targets: app, node_exporter, Alertmanager and Prometheus all UP |
| [`06_alerts_inactive.png`](screenshots/06_alerts_inactive.png) | All 7 alert rules loaded and inactive while the app is idle |
| [`07_alert_firing_prometheus.png`](screenshots/07_alert_firing_prometheus.png) | CPU alert firing in Prometheus during a bulk job |
| [`08_alertmanager.png`](screenshots/08_alertmanager.png) | The same alert received by Alertmanager and routed to the local receiver |
| [`09_alert_receiver.png`](screenshots/09_alert_receiver.png) | Receiver output: CPU alert and app-down alert, each fired and resolved |
| [`10a_dashboard_top.png`](screenshots/10a_dashboard_top.png) | Grafana dashboard: health, throughput and latency rows |
| [`10b_dashboard_bottom.png`](screenshots/10b_dashboard_bottom.png) | Grafana dashboard: workload and system rows, CPU spike of the app during a bulk job |
| [`metrics_snapshot.txt`](screenshots/metrics_snapshot.txt) | Raw metric values used for the hand calculations in `METRICS.md` |

---

## Setup and run

### Requirements
- Linux with **Python 3.10+** (tested with 3.14 on Ubuntu)
- **Docker** with Docker Compose
- Free ports: 8501, 18000 (app), 9090, 9093, 9100, 3000, 5001 (monitoring stack)
- Internet on the first run (downloads the BLIP model, ~1 GB, and the Docker images)

Open **three terminals** in the repo folder `DA3408_DA24B034_4/`.

### Terminal 1 — the captioning app

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
CUDA_VISIBLE_DEVICES="" streamlit run app/main.py
```

- `requirements.txt` installs the CPU-only PyTorch build; `CUDA_VISIBLE_DEVICES=""` keeps inference on the CPU.
- Wait until the model has loaded (first run: a few minutes for the download; later: a few seconds).
- App: **http://localhost:8501** · Metrics: **http://localhost:18000/metrics**
- Leave this terminal running.

### Terminal 2 — the monitoring stack

```bash
cd monitoring
docker compose up -d
docker compose ps
```

All five containers (`node-exporter`, `prometheus`, `alertmanager`, `alert-receiver`, `grafana`) should show **Up**. They use the host network, so Prometheus reaches the app at `localhost:18000`.

| Service | URL |
|---|---|
| Prometheus targets / alerts | http://localhost:9090/targets · http://localhost:9090/alerts |
| Alertmanager | http://localhost:9093 |
| node_exporter | http://localhost:9100/metrics |
| Grafana | http://localhost:3000 (login `admin` / `admin`) → Dashboards → **CPU Image Captioning: Application Monitoring** |

### Terminal 3 — live alert notifications

```bash
cd monitoring
docker compose logs -f alert-receiver
```

Prints one line per alert, `FIRING` or `RESOLVED` (times are UTC, the container default).

### Try it

1. Open **http://localhost:9090/targets** — all four targets should be **UP**.
2. Open the Grafana dashboard (refresh 5 s, last 15 minutes).
3. In the app, **Single image** tab: upload `sample_data/single/cat1.jpeg` → **Generate caption**.
4. **Bulk (ZIP)** tab: upload `sample_data/bulk_messy.zip` → **Caption all images** (5 captioned, 6 bad files skipped).
5. **Bulk (ZIP)** tab: upload `sample_data/bulk_demo.zip` → **Caption all images** (27 images, ~45 s). On the dashboard, throughput, latency and CPU rise together; within ~10 s **`CPUMoreThan200Percent`** fires and appears in Terminal 3.
6. Stop the app (Ctrl+C in Terminal 1): after ~5 s **`CaptionAppDown`** fires. Start it again and the alert resolves.

### Stop everything

```bash
# Terminal 1: Ctrl+C
cd monitoring && docker compose down
```

### Troubleshooting
- **Container name already in use:** an older container with the same name exists; remove it with `docker rm -f <name>` and run `docker compose up -d` again.
- **Port already in use:** stop any locally installed Prometheus, node_exporter or Grafana using the ports above.
- **No data in Grafana:** check that the app is running and `python_app` is UP on the Prometheus targets page.

---

## AI Usage Disclosure

See [`ai_usage.md`](ai_usage.md) for how AI tools were used. The prompts for AI-generated PromQL are listed in [`AI_prompt_usage.md`](AI_prompt_usage.md), and the logic of every query is calculated by hand in [`METRICS.md`](METRICS.md).