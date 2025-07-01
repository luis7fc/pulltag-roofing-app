import streamlit as st
import streamlit_authenticator as stauth
from supabase import create_client
import os
from system_monitor import show_system_metrics

# Tab scripts (unchanged)
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

# --- Supabase setup -----------------------------------------------------------
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# Fetch users and build two dicts: one for stauth, one for roles
rows = supabase.table("users").select("username,password,role").execute().data or []

# 1. Build credentials for stauth (only name+password)
stauth_credentials = {}
# 2. Build lookup for roles
user_roles = {}

for u in rows:
    username = u.get("username", "").strip()
    raw_pw = (u.get("password") or "").replace("\n", "").strip()
    role = (u.get("role") or "").strip()

    # Only include if we have both fields
    if username and raw_pw:
        stauth_credentials[username] = {
            "name": username,
            "password": raw_pw,
        }
        user_roles[username] = role

# --- Streamlit-Authenticator setup -------------------------------------------
authenticator = stauth.Authenticate(
    {"usernames": stauth_credentials},
    cookie_name="roofing_auth",
    key=os.getenv("AUTH_COOKIE_KEY", "fallback_key"),
    cookie_expiry_days=30,
)

# Render the login form and get back (name, status, username) or None
login_tuple = authenticator.login("main", "Login")

if login_tuple is None:
    # Form is rendering or waiting for submit
    st.stop()

# We only reach here once the user has interacted:
name, auth_status, username = login_tuple

if auth_status is False:
    st.error("❌ Incorrect username or password.")
    st.stop()
elif auth_status is None:
    st.warning("⚠ Please enter your credentials.")
    st.stop()

# --- User is authenticated! --------------------------------------------
role = user_roles.get(username, "")

# Debug output (moved here, only shown after login)
if os.getenv("DEBUG_MODE") == "true":  # Only show in debug mode
    st.write("🔐 stauth credentials:", stauth_credentials)
    st.write("👥 user roles map:", user_roles)

st.write(f"✅ Logged in as `{username}` with role `{role}`")

# Sidebar context + logout
st.sidebar.markdown(f"**Logged in as:** `{username}` ({role})")
authenticator.logout("Log out", "sidebar")
show_system_metrics(role)

# --- Define tabs per role ----------------------------------------------------
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
    "super": {"📦 Super Request": super_request.run},
    "warehouse": {
        "🛠️ Warehouse Kitting": warehouse_kitting.run,
        "🔁 Backorder Kitting": backorder_kitting.run,
    },
}

available = tabs_by_role.get(role, {})
st.write("📂 Available tabs:", list(available.keys()))

if available:
    st.sidebar.title("📚 Menu")
    selection = st.sidebar.radio("Go to", list(available.keys()))
    available[selection]()
else:
    st.error("🚫 You do not have access to this app.")
