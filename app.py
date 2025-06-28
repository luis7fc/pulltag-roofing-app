import streamlit as st
from auth import login
from system_monitor import show_system_metrics

# Tab scripts (each must define a `run()` function)
from tabs import (
    community_creation,
    budget_upload,
    reporting,
    super_request,
    warehouse_kitting,
    backorder_kitting,
    user_management,
    items_editor,
    roof_editor,
)

st.set_page_config(page_title="Roofing Pulltag System", layout="wide")

# 🔐 Login
login()
if not st.session_state.get("user"):
    st.stop()

user = st.session_state["user"]
role = user.get("role")
username = user.get("username")

# Sidebar context
st.sidebar.markdown(f"**Logged in as:** `{username}` ({role})")
show_system_metrics(role)

# 🔁 Tab Definitions per Role
base_tabs = {
    "🏘️ Community Creation": community_creation.run,
    "📄 Budget Upload": budget_upload.run,
    "📊 Reporting & Sage Export": reporting.run,
}

exec_tabs = {
    **base_tabs,
    "📦 Super Request": super_request.run,
    "🛠️ Warehouse Kitting": warehouse_kitting.run,
    "🔁 Backorder Kitting": backorder_kitting.run,
    "👤 User Management": user_management.run,
    "🧾 Items Master Editor": items_editor.run,
    "🏠 Roof Types Editor": roof_editor.run,
}

tabs_by_role = {
    "exec": exec_tabs,
    "admin": base_tabs,
    "super": {
        "📦 Super Request": super_request.run,
    },
    "warehouse": {
        "🛠️ Warehouse Kitting": warehouse_kitting.run,
        "🔁 Backorder Kitting": backorder_kitting.run,
    },
}

# 🧭 Sidebar Navigation
tabs = tabs_by_role.get(role, {})
if tabs:
    st.sidebar.title("📚 Menu")
    choice = st.sidebar.radio("Go to", list(tabs.keys()))
    tabs[choice]()
else:
    st.error("You do not have access to this app.")
