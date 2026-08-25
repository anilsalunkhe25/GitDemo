"""Streamlit operations console backed exclusively by the Flask API."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from api_client import ApiClient, ApiError, login

st.set_page_config(page_title="Relief Operations", page_icon="+", layout="wide")

if "token" not in st.session_state:
    st.session_state.token = None
if "user" not in st.session_state:
    st.session_state.user = None


def show_login() -> None:
    st.title("Emergency Relief Operations")
    st.caption("AI-assisted coordination for requests, stock, forecasts, and deliveries")
    with st.form("login"):
        email = st.text_input("Email", value="admin@relief.local")
        password = st.text_input("Password", type="password", value="Admin@123")
        submitted = st.form_submit_button("Sign in", type="primary")
    if submitted:
        try:
            result = login(email, password)
            st.session_state.token = result["access_token"]
            st.session_state.user = result["user"]
            st.rerun()
        except ApiError as exc:
            st.error(str(exc))


def frame() -> ApiClient:
    client = ApiClient(token=st.session_state.token)
    user = st.session_state.user
    with st.sidebar:
        st.title("Relief Ops")
        st.caption(f"{user['name']}  |  {user['role'].replace('_', ' ').title()}")
        page = st.radio("Workspace", ["Dashboard", "Requests", "Inventory", "Forecasting", "Deliveries", "Analytics"])
        if st.button("Log out"):
            st.session_state.token = None
            st.session_state.user = None
            st.rerun()
    return client, page


def dashboard(client: ApiClient) -> None:
    st.header("Operational dashboard")
    summary = client.get("/api/dashboard/summary")
    cards = [("Active emergencies", summary.get("active_emergencies", 0)), ("Pending requests", summary.get("pending_requests", 0)), ("Critical requests", summary.get("critical_requests", 0)), ("Active deliveries", summary.get("active_deliveries", 0))]
    columns = st.columns(len(cards))
    for column, (label, value) in zip(columns, cards):
        column.metric(label, value)
    alerts = summary.get("alerts", [])
    if alerts:
        st.subheader("Attention required")
        for alert in alerts:
            (st.error if alert.get("level") == "CRITICAL" else st.warning)(alert.get("message", "Review alert"))
    st.subheader("Inventory snapshot")
    rows = summary.get("inventory", summary.get("inventory_summary", []))
    if rows:
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def table_page(client: ApiClient, title: str, endpoint: str) -> None:
    st.header(title)
    try:
        rows = client.get(endpoint) or []
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    except ApiError as exc:
        st.error(str(exc))


def forecasting(client: ApiClient) -> None:
    st.header("AI Demand Forecasting")
    st.info("AI Recommendation - Human Review Required. Forecasts support decisions; administrators approve critical allocations.")
    try:
        metrics = client.get("/api/forecast/metrics")
        st.json(metrics)
        forecasts = client.get("/api/forecast/history") or []
        if forecasts:
            st.dataframe(pd.DataFrame(forecasts), use_container_width=True, hide_index=True)
    except ApiError as exc:
        st.warning(str(exc))


if not st.session_state.token:
    show_login()
else:
    api, selected = frame()
    try:
        if selected == "Dashboard":
            dashboard(api)
        elif selected == "Requests":
            table_page(api, "Relief requests", "/api/requests")
        elif selected == "Inventory":
            table_page(api, "Inventory", "/api/inventory")
        elif selected == "Forecasting":
            forecasting(api)
        elif selected == "Deliveries":
            table_page(api, "Delivery tracking", "/api/deliveries")
        else:
            try:
                st.header("Analytics")
                st.json(api.get("/api/dashboard/analytics"))
            except ApiError as exc:
                st.error(str(exc))
    except ApiError as exc:
        st.error(str(exc))
