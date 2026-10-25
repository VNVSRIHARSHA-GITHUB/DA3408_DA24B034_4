"""Client IP and session ID, used as Prometheus labels."""

import uuid

import streamlit as st


def get_session_id() -> str:
    """Short random ID per browser session."""
    if "session_id" not in st.session_state:
        st.session_state.session_id = uuid.uuid4().hex[:8]
    return st.session_state.session_id


def get_client_ip() -> str:
    """Best-effort client IP from Streamlit's request context."""
    ctx = getattr(st, "context", None)
    if ctx is None:
        return "unknown"

    ip = getattr(ctx, "ip_address", None)
    if ip:
        return ip

    headers = getattr(ctx, "headers", None) or {}
    forwarded = headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()

    host = headers.get("Host", "")
    if host.startswith(("localhost", "127.0.0.1", "[::1]")):
        return "localhost"
    return "unknown"
