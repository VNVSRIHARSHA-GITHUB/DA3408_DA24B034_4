"""
CPU-only image captioning app (DA3408 Assignment 4).
Run from the repo root: streamlit run app/main.py
UI on :8501, Prometheus metrics on :18000/metrics.
"""

import os

os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")  # CPU-only, before torch loads

import logging
import time
import zipfile

import pandas as pd
import streamlit as st
import torch
import transformers

from bulk import (
    DECODE_ERRORS,
    MAX_FILE_BYTES,
    MAX_IMAGES_PER_ZIP,
    MAX_UPLOAD_MB,
    extract_images,
    load_image,
)
from captioner import Captioner
from client_info import get_client_ip, get_session_id
from metrics import METRICS_PORT, AppMetrics, init_metrics

APP_VERSION = "1.1.0"
IMAGE_TYPES = ["jpg", "jpeg", "png", "bmp", "webp", "gif", "tif", "tiff"]
MAX_BEAMS = 5
GALLERY_COLUMNS = 4
THUMB_SIZE = (320, 320)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("caption_app")

st.set_page_config(page_title="CPU Image Captioning", page_icon="\U0001F5BC\uFE0F", layout="wide")


# Run once per server process (survives Streamlit reruns). Metrics start before
# the model so caption_model_loaded = 0 is visible while BLIP loads.
@st.cache_resource
def get_metrics() -> AppMetrics:
    return init_metrics()


@st.cache_resource(show_spinner="Loading BLIP on CPU (first run downloads ~1 GB)...")
def get_captioner(_m: AppMetrics) -> Captioner:
    _m.model_loaded.set(0)
    captioner = Captioner()
    _m.model_load_seconds.set(captioner.load_seconds)
    _m.build.info(
        {
            "app_version": APP_VERSION,
            "model": captioner.model_name,
            "device": "cpu",
            "torch_threads": str(captioner.num_threads),
            "torch_version": torch.__version__,
            "transformers_version": transformers.__version__,
        }
    )
    _m.model_loaded.set(1)
    log.info("Model %s loaded in %.1fs", captioner.model_name, captioner.load_seconds)
    return captioner


m = get_metrics()
try:
    captioner = get_captioner(m)
except Exception as exc:  # e.g. no internet on first run, disk full
    m.errors.labels(stage="model_load", error_type=type(exc).__name__).inc()
    m.model_loaded.set(0)
    st.error(f"Could not load the captioning model: {exc}")
    st.stop()

client_ip = get_client_ip()
session_id = get_session_id()


def caption_one(image, mode: str, num_beams: int) -> str:
    """Run the model on one image and record per-image metrics."""
    m.image_megapixels.labels(mode=mode).observe(image.width * image.height / 1e6)

    start = time.perf_counter()
    text = captioner.caption(image, num_beams=num_beams)
    # Timed manually so only successful inferences enter the histogram.
    m.inference_seconds.labels(mode=mode, beams=str(num_beams)).observe(time.perf_counter() - start)

    m.caption_words.labels(mode=mode).observe(len(text.split()))
    m.images.labels(mode=mode, status="success").inc()
    m.last_success_timestamp.set_to_current_time()
    return text


def thumbnail(image):
    """Small copy of an image for the bulk gallery."""
    thumb = image.copy()
    thumb.thumbnail(THUMB_SIZE)
    return thumb


# ---------------- Sidebar ----------------
with st.sidebar:
    st.header("Decoding")
    num_beams = st.slider(
        "Beam search width (num_beams)",
        min_value=1,
        max_value=MAX_BEAMS,
        value=1,
        help=(
            "1 = greedy decoding (fastest). Higher values keep that many candidate "
            "captions at each step and return the best one: sometimes better "
            "captions, but more CPU time per image. The effect is visible on the "
            "Grafana panel 'Average inference time by beam width'."
        ),
    )
    st.caption("1 = greedy (fastest) · higher = beam search (slower on CPU)")

    st.header("Limits")
    st.markdown(
        f"""
- **Max upload size:** {MAX_UPLOAD_MB} MB per file
- **Max images per ZIP:** {MAX_IMAGES_PER_ZIP} (extra images are skipped)
- **Max size per image in a ZIP:** {MAX_FILE_BYTES // (1024 * 1024)} MB
"""
    )

    st.header("Runtime")
    st.markdown(
        f"""
- **Model:** `{captioner.model_name}`
- **Device:** CPU ({captioner.num_threads} threads)
- **Model load time:** {captioner.load_seconds:.1f} s
- **Metrics:** `:{METRICS_PORT}/metrics`
- **Your client IP:** `{client_ip}`
- **Your session ID:** `{session_id}`
"""
    )

# ---------------- Main page ----------------
st.title("\U0001F5BC\uFE0F CPU Image Captioning")
st.caption("BLIP image captioning running on CPU only, instrumented with Prometheus.")

single_tab, bulk_tab = st.tabs(["Single image", "Bulk (ZIP)"])

# Single mode
with single_tab:
    st.info(f"Upload one image (max **{MAX_UPLOAD_MB} MB**). Formats: {', '.join(IMAGE_TYPES)}.")
    upload = st.file_uploader("Upload one image", type=IMAGE_TYPES, key="single_upload")

    if upload is not None:
        st.image(upload, width=380)

        # Run only on click, so reruns don't re-caption or re-count.
        if st.button("Generate caption", type="primary", key="single_go"):
            data = upload.getvalue()
            m.upload_bytes.labels(mode="single", client_ip=client_ip, session_id=session_id).observe(len(data))
            m.active_requests.labels(mode="single").inc()
            start = time.perf_counter()
            status = "success"
            try:
                with st.spinner(f"Captioning on CPU (num_beams={num_beams})…"):
                    image = load_image(data)
                    caption = caption_one(image, "single", num_beams)
                st.session_state.single_result = (upload.name, caption, num_beams,
                                                  time.perf_counter() - start)
            except DECODE_ERRORS as exc:
                status = "failed"
                m.errors.labels(stage="decode", error_type=type(exc).__name__).inc()
                st.session_state.single_result = None
                st.error(f"This file could not be read as an image ({type(exc).__name__}).")
            except Exception as exc:
                status = "failed"
                m.images.labels(mode="single", status="failed").inc()
                m.errors.labels(stage="inference", error_type=type(exc).__name__).inc()
                st.session_state.single_result = None
                st.error(f"Captioning failed: {exc}")
            finally:
                m.active_requests.labels(mode="single").dec()
                m.request_seconds.labels(mode="single").observe(time.perf_counter() - start)
                m.requests.labels(
                    mode="single", status=status, client_ip=client_ip, session_id=session_id
                ).inc()

        result = st.session_state.get("single_result")
        if result and result[0] == upload.name:
            st.success(f"**Caption:** {result[1]}")
            st.caption(f"num_beams={result[2]} · {result[3]:.1f} s")

# Bulk mode
with bulk_tab:
    st.info(
        f"Upload a ZIP of images (max **{MAX_UPLOAD_MB} MB**). "
        f"At most **{MAX_IMAGES_PER_ZIP} images** are captioned per job; any extra images are skipped. "
        f"Non-image files, corrupt images and images over {MAX_FILE_BYTES // (1024 * 1024)} MB "
        "are skipped too, so the app never crashes on bad input."
    )
    zip_upload = st.file_uploader("Upload a ZIP file", type=["zip"], key="bulk_upload")

    if zip_upload is not None and st.button("Caption all images", type="primary", key="bulk_go"):
        data = zip_upload.getvalue()
        m.upload_bytes.labels(mode="bulk", client_ip=client_ip, session_id=session_id).observe(len(data))
        m.active_requests.labels(mode="bulk").inc()
        start = time.perf_counter()
        status = "success"
        images, skipped, rows, thumbs = [], [], [], []
        try:
            extract_start = time.perf_counter()
            images, skipped = extract_images(data)
            m.zip_extract_seconds.observe(time.perf_counter() - extract_start)
            for item in skipped:
                m.skipped.labels(reason=item.reason).inc()

            if not images:
                status = "failed"
                st.warning("No valid images found in this ZIP.")
            else:
                total = len(images)
                m.current_batch_images.set(total)
                m.bulk_progress.set(0)
                progress = st.progress(0.0, text=f"Captioning 0 / {total} images on CPU…")

                for i, item in enumerate(images, start=1):
                    try:
                        text = caption_one(item.image, "bulk", num_beams)
                        rows.append({"file": item.name, "caption": text, "status": "ok"})
                    except Exception as exc:  # one bad image must not stop the batch
                        text = ""
                        status = "partial"
                        m.images.labels(mode="bulk", status="failed").inc()
                        m.errors.labels(stage="inference", error_type=type(exc).__name__).inc()
                        rows.append({"file": item.name, "caption": "", "status": f"failed: {type(exc).__name__}"})
                    thumbs.append(thumbnail(item.image))
                    m.bulk_progress.set(i / total)
                    progress.progress(i / total, text=f"Captioning {i} / {total} images on CPU…")

        except zipfile.BadZipFile as exc:
            status = "failed"
            m.errors.labels(stage="zip", error_type=type(exc).__name__).inc()
            st.error("That file is not a valid ZIP archive.")
        finally:
            duration = time.perf_counter() - start
            m.active_requests.labels(mode="bulk").dec()
            m.request_seconds.labels(mode="bulk").observe(duration)
            m.current_batch_images.set(0)
            m.requests.labels(mode="bulk", status=status, client_ip=client_ip, session_id=session_id).inc()

        st.session_state.bulk_result = {
            "zip": zip_upload.name,
            "rows": rows,
            "thumbs": thumbs,
            "skipped": [{"file": s.name, "reason": s.reason} for s in skipped],
            "seconds": duration,
            "num_beams": num_beams,
        }

    result = st.session_state.get("bulk_result")
    if result and zip_upload is not None and result["zip"] == zip_upload.name:
        ok = sum(r["status"] == "ok" for r in result["rows"])
        st.success(
            f"Captioned **{ok}** image(s) in **{result['seconds']:.1f} s** "
            f"(num_beams={result['num_beams']}); skipped **{len(result['skipped'])}** file(s)."
        )
        over_limit = sum(s["reason"] == "over_limit" for s in result["skipped"])
        if over_limit:
            st.warning(
                f"This ZIP had more than {MAX_IMAGES_PER_ZIP} images: only the first "
                f"{MAX_IMAGES_PER_ZIP} were captioned and {over_limit} were skipped."
            )

        if result["rows"]:
            gallery_tab, table_tab = st.tabs(["Gallery", "Table"])
            with gallery_tab:
                cols = st.columns(GALLERY_COLUMNS)
                for i, (row, thumb) in enumerate(zip(result["rows"], result["thumbs"])):
                    with cols[i % GALLERY_COLUMNS]:
                        st.image(thumb)
                        st.markdown(f"**{row['caption'] or '(failed)'}**")
                        st.caption(row["file"])
            with table_tab:
                df = pd.DataFrame(result["rows"])
                st.dataframe(df, use_container_width=True, hide_index=True)
            st.download_button(
                "Download captions (CSV)",
                pd.DataFrame(result["rows"]).to_csv(index=False).encode("utf-8"),
                file_name="captions.csv",
                mime="text/csv",
            )
        if result["skipped"]:
            with st.expander(f"Skipped files ({len(result['skipped'])})"):
                st.dataframe(pd.DataFrame(result["skipped"]), use_container_width=True, hide_index=True)
