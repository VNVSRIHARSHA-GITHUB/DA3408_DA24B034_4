"""
All Prometheus metrics for the app, defined in one place.

Streamlit reruns main.py on every interaction, but a metric can be registered
only once and the /metrics port bound only once. So init_metrics() is called
through @st.cache_resource in main.py and runs once per server process.
"""

import logging
from dataclasses import dataclass

from prometheus_client import (
    CollectorRegistry,
    Counter,
    GCCollector,
    Gauge,
    Histogram,
    Info,
    PlatformCollector,
    ProcessCollector,
    Summary,
    disable_created_metrics,
    start_http_server,
)

log = logging.getLogger("caption_app.metrics")

METRICS_PORT = 18000  # must match the python_app target in prometheus.yml

# Buckets sized for this workload: BLIP on CPU takes ~0.5-4 s per image.
INFERENCE_BUCKETS = (0.25, 0.5, 1, 1.5, 2, 3, 4, 6, 8, 12, 16, 30)
MEGAPIXEL_BUCKETS = (0.1, 0.3, 0.5, 1, 2, 4, 8, 12, 24)
CAPTION_WORD_BUCKETS = (3, 5, 7, 9, 11, 13, 15, 20)
ZIP_EXTRACT_BUCKETS = (0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10)


@dataclass
class AppMetrics:
    registry: CollectorRegistry

    # Counters
    requests: Counter
    images: Counter
    skipped: Counter
    errors: Counter

    # Gauges
    model_loaded: Gauge
    model_load_seconds: Gauge
    active_requests: Gauge
    current_batch_images: Gauge
    bulk_progress: Gauge
    last_success_timestamp: Gauge

    # Histograms
    inference_seconds: Histogram
    image_megapixels: Histogram
    caption_words: Histogram
    zip_extract_seconds: Histogram

    # Summaries
    upload_bytes: Summary
    request_seconds: Summary

    # Info
    build: Info


def init_metrics(port: int = METRICS_PORT) -> AppMetrics:
    """Create every metric once and start the /metrics HTTP server on `port`."""
    disable_created_metrics()  # drop the unused *_created series

    reg = CollectorRegistry()

    # A private registry starts empty: add back process_* (app CPU/RAM),
    # python_info and python_gc_* collectors.
    ProcessCollector(registry=reg)
    PlatformCollector(registry=reg)
    GCCollector(registry=reg)

    m = AppMetrics(
        registry=reg,
        requests=Counter(
            "caption_requests",
            "User-triggered caption requests (one single-image upload or one bulk ZIP job)",
            ["mode", "status", "client_ip", "session_id"],
            registry=reg,
        ),
        images=Counter(
            "caption_images_processed",
            "Images passed through the captioning model",
            ["mode", "status"],  # status: success | failed
            registry=reg,
        ),
        skipped=Counter(
            "caption_files_skipped",
            "Files inside uploaded ZIPs that were not captioned",
            ["reason"],  # not_an_image | corrupt | too_large | over_limit | system_file
            registry=reg,
        ),
        errors=Counter(
            "caption_errors",
            "Errors raised while serving requests",
            ["stage", "error_type"],  # stage: model_load | decode | zip | inference
            registry=reg,
        ),
        model_loaded=Gauge(
            "caption_model_loaded",
            "1 when the captioning model is loaded and ready to serve, else 0",
            registry=reg,
        ),
        model_load_seconds=Gauge(
            "caption_model_load_seconds",
            "Wall-clock time taken to load the model at startup",
            registry=reg,
        ),
        active_requests=Gauge(
            "caption_active_requests",
            "Caption requests currently being processed",
            ["mode"],
            registry=reg,
        ),
        current_batch_images=Gauge(
            "caption_current_batch_images",
            "Number of images in the bulk job currently running (0 when idle)",
            registry=reg,
        ),
        bulk_progress=Gauge(
            "caption_bulk_progress_ratio",
            "Fraction of the current bulk job completed, 0 to 1",
            registry=reg,
        ),
        last_success_timestamp=Gauge(
            "caption_last_success_timestamp_seconds",
            "Unix time of the last successfully captioned image",
            registry=reg,
        ),
        inference_seconds=Histogram(
            "caption_inference_seconds",
            "Model inference time per image (preprocess + generate + decode)",
            ["mode", "beams"],
            buckets=INFERENCE_BUCKETS,
            registry=reg,
        ),
        image_megapixels=Histogram(
            "caption_image_megapixels",
            "Input image resolution in megapixels",
            ["mode"],
            buckets=MEGAPIXEL_BUCKETS,
            registry=reg,
        ),
        caption_words=Histogram(
            "caption_length_words",
            "Number of words in each generated caption",
            ["mode"],
            buckets=CAPTION_WORD_BUCKETS,
            registry=reg,
        ),
        zip_extract_seconds=Histogram(
            "caption_zip_extract_seconds",
            "Time to open, filter and decode all images in an uploaded ZIP",
            buckets=ZIP_EXTRACT_BUCKETS,
            registry=reg,
        ),
        upload_bytes=Summary(
            "caption_upload_bytes",
            "Size of uploaded files (image or ZIP)",
            ["mode", "client_ip", "session_id"],
            registry=reg,
        ),
        request_seconds=Summary(
            "caption_request_seconds",
            "End-to-end request time: decode/extract + all inferences",
            ["mode"],
            registry=reg,
        ),
        build=Info(
            "caption_build",
            "Model and runtime build information",
            registry=reg,
        ),
    )

    # Pre-create known label sets so they appear as 0 before the first event.
    for mode in ("single", "bulk"):
        m.active_requests.labels(mode=mode).set(0)
        for status in ("success", "failed"):
            m.images.labels(mode=mode, status=status)
    m.model_loaded.set(0)

    try:
        start_http_server(port, registry=reg)
        log.info("Prometheus metrics exposed at http://0.0.0.0:%d/metrics", port)
    except OSError as exc:
        # Port in use (e.g. a second instance): keep the app running.
        log.error("Could not start metrics server on port %d: %s", port, exc)

    return m
