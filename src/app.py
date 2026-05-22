"""Streamlit entry point for the Pfizer SDF Intelligence System.

Layout (D-03):
    Sidebar: Langfuse connection status (checked once per session)
    Tab 1 — Compliance: SQLite-backed compliance dashboard
    Tab 2 — Chat: Document-grounded RAG chatbot
    Tab 3 — Eval: Placeholder for Phase 4 evaluation metrics

Pitfall 5 mitigation: all expensive initialization is guarded with
    `if "key" not in st.session_state`
to prevent re-execution on every Streamlit script rerun.
"""
from __future__ import annotations

import streamlit as st

from src.config import get_settings
from src.dashboard import render_chat_tab, render_compliance_tab, render_eval_tab
from src.tracing import verify_langfuse_connection

# Page config must be the first Streamlit call
st.set_page_config(
    page_title="Pfizer SDF Intelligence",
    page_icon=None,
    layout="wide",
)

# --- Sidebar: Langfuse connection status ---
# Guard with session_state to avoid re-calling auth_check() on every widget interaction
# (Pitfall 5: Streamlit reruns reset all local variables)
if "langfuse_ok" not in st.session_state:
    st.session_state.langfuse_ok = verify_langfuse_connection()

with st.sidebar:
    st.title("Pfizer SDF Intelligence")
    st.divider()
    if st.session_state.langfuse_ok:
        st.markdown("**Langfuse:** :green[Connected]")
    else:
        st.markdown("**Langfuse:** :red[Not connected]")
    st.caption("Set LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY in .env to enable tracing.")

# --- Main tabs (D-03) ---
tab_compliance, tab_chat, tab_eval = st.tabs(["Compliance", "Chat", "Eval"])

with tab_compliance:
    st.header("Compliance Dashboard")
    render_compliance_tab(get_settings().db_path)

with tab_chat:
    st.header("Document Q&A")
    render_chat_tab(get_settings().db_path)

with tab_eval:
    st.header("Evaluation")
    render_eval_tab(get_settings().db_path)
