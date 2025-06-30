import streamlit as st
import streamlit_authenticator as stauth
from supabase import create_client
import os
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

# 🔐 Supabase + streamlit-authenticator login setup
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

response = supabase.table("users").select("username, password, role").execute()
users = response.data or []

credentials = {
    "usernames": {
        user["username"]: {
            "name": user["username"],
            "password": user["password"],
            "role": user["role"]
        }
        for user in users
    }
}


authenticator = stauth.Authenticate(
    credentials,
    cookie_name="roofing_auth",
    key=os.environ.get("AUTH_COOKIE_KEY", "default_fallback_key"),
    cookie_expiry_days=30
)

name, auth_status, username = authenticator.login("main", "Login")

if not auth_status:
    st.stop()

role = credentials[username]["role"]

# Sidebar context
st.sidebar.markdown(f"**Logged in as:** `{username}` ({role})")
authenticator.logout("Log out", "sidebar")
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
