import streamlit as st
import streamlit_authenticator as stauth
from supabase import create_client
import os
from system_monitor import show_system_metrics

from tabs import (
    community_creation, budget_upload, reporting,
    super_request, warehouse_kitting, backorder_kitting,
    user_management, items_editor, roof_editor,
)

st.set_page_config(page_title="Roofing Pulltag System", layout="wide")
st.write("🚦 Script reached top-level.")

# --- Supabase setup ---
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# Fetch & sanitize users
users = supabase.table("users").select("username,password,role").execute().data or []
credentials = {
    "usernames": {
        u["username"]: {
            "name":     u["username"],
            "password": (u.get("password") or "").replace("\n", "").strip(),
            "role":     (u.get("role")     or "").strip(),
        }
        for u in users
    }
}
st.write("🔐 Loaded credentials:", credentials)

# --- Authenticator setup ---
authenticator = stauth.Authenticate(
    credentials,
    cookie_name="roofing_auth",
    key=os.getenv("AUTH_COOKIE_KEY", "fallback_key"),
    cookie_expiry_days=30,
)

# 🔐 Render login form (label first, then location) — **this is the fix** 👇
login_result = authenticator.login("Login", "main")

if login_result is not None:
    name, auth_status, username = login_result
else:
    st.error("Login failed to load. Check credentials or Supabase response.")
    st.stop()

if auth_status is False:
    st.error("Incorrect username or password.")
    st.stop()
elif auth_status is None:
    st.warning("Please enter your credentials.")
    st.stop()

# --- Role & tabs ---
role = credentials["usernames"][username]["role"]
st.write(f"✅ Authenticated as `{username}` ({role})")
st.sidebar.markdown(f"**Logged in as:** `{username}` ({role})")
authenticator.logout("Log out", "sidebar")
show_system_metrics(role)

base_tabs = {
    "🏘️ Community Creation":      community_creation.run,
    "📄 Budget Upload":           budget_upload.run,
    "📊 Reporting & Sage Export": reporting.run,
}
exec_tabs = {
    **base_tabs,
    "📦 Super Request":        super_request.run,
    "🛠️ Warehouse Kitting":    warehouse_kitting.run,
    "🔁 Backorder Kitting":     backorder_kitting.run,
    "👤 User Management":       user_management.run,
    "🧾 Items Master Editor":   items_editor.run,
    "🏠 Roof Types Editor":     roof_editor.run,
}
tabs_by_role = {
    "exec":      exec_tabs,
    "admin":     base_tabs,
    "super":     {"📦 Super Request": super_request.run},
    "warehouse": {
        "🛠️ Warehouse Kitting": warehouse_kitting.run,
        "🔁 Backorder Kitting":  backorder_kitting.run,
    },
}

tabs = tabs_by_role.get(role, {})
st.write("📂 Tabs available:", list(tabs.keys()))

if tabs:
    st.sidebar.title("📚 Menu")
    choice = st.sidebar.radio("Go to", list(tabs.keys()))
    tabs[choice]()
else:
    st.error("You do not have access to this app.")
