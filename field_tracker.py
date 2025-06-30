import streamlit as st
from supabase import create_client
import os

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


def _load_from_supabase(username, tab, key):
    response = supabase.table("drafts").select("value").eq("username", username).eq("tab", tab).eq("key", key).single().execute()
    return response.data["value"] if response.data else ""


def _save_to_supabase(username, tab, key, value):
    supabase.table("drafts").upsert({
        "username": username,
        "tab": tab,
        "key": key,
        "value": value
    }).execute()


# === TRACKED INPUT ===
def tracked_input(label, key, username, tab, default="", **kwargs):
    if key not in st.session_state:
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
    st.session_state[key] = _load_from_supabase(username, tab, key) or default

    value = st.text_input(label, value=st.session_state[key], key=key, **kwargs)

    if value != st.session_state[key]:
        st.session_state[key] = value
        _save_to_supabase(username, tab, key, value)

    return value


# === TRACKED TEXT AREA ===
def tracked_text_area(label, key, username, tab, default="", **kwargs):
    if key not in st.session_state:
        st.session_state[key] = _load_from_supabase(username, tab, key) or default

    value = st.text_area(label, value=st.session_state[key], key=key, **kwargs)

    if value != st.session_state[key]:
        st.session_state[key] = value
        _save_to_supabase(username, tab, key, value)

    return value


# === TRACKED SELECTBOX ===
def tracked_selectbox(label, options, key, username, tab, default=None, **kwargs):
    if key not in st.session_state:
        stored = _load_from_supabase(username, tab, key)
        st.session_state[key] = stored if stored in options else default or options[0]

    value = st.selectbox(label, options, index=options.index(st.session_state[key]), key=key, **kwargs)

    if value != st.session_state[key]:
        st.session_state[key] = value
        _save_to_supabase(username, tab, key, value)

    return value
