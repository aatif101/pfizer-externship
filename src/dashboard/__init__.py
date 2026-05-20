"""Dashboard data adapters for read-only Streamlit views."""

from src.dashboard.chat import render_chat_tab
from src.dashboard.compliance import format_compliance_rows, load_compliance_rows, render_compliance_tab

__all__ = ["format_compliance_rows", "load_compliance_rows", "render_chat_tab", "render_compliance_tab"]
