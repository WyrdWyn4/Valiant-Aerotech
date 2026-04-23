import streamlit as st
from streamlit_autorefresh import st_autorefresh

from app.core.config import Config
from app.services.telemetry_service import TelemetryService
from app.ui.dashboard_view import render_dashboard


st.set_page_config(page_title="MAVLink Dashboard", layout="wide")

if "telemetry_service" not in st.session_state:
    config = Config()
    service = TelemetryService(config)
    service.start()
    st.session_state.telemetry_service = service
    st.session_state.telemetry_config = config

service = st.session_state.telemetry_service
config = st.session_state.telemetry_config

st_autorefresh(interval=config.ui_refresh_ms, key="mav_dashboard_refresh")

snapshot = service.snapshot()
render_dashboard(snapshot)