import streamlit as st
import streamlit_authenticator as stauth
from supabase import create_client
import os
from system_monitor import show_system_metrics

# Tab scripts
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
if not SUPABASE_URL or not SUPABASE_KEY:
    st.error("❌ Missing SUPABASE_URL or SUPABASE_KEY")
    st.stop()

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
rows = supabase.table("users").select("username,password,role").execute().data or []

# Build credential dicts
stauth_credentials = {}
user_roles = {}
for u in rows:
    u_name = u.get("username", "").strip()
    u_pw   = (u.get("password") or "").replace("\n", "").strip()
    u_role = (u.get("role")     or "").strip()
    if u_name and u_pw:
        stauth_credentials[u_name] = {"name": u_name, "password": u_pw}
        user_roles[u_name] = u_role

if not stauth_credentials:
    st.error("❌ No valid users in Supabase `users` table.")
    st.stop()

# --- Authenticator setup -----------------------------------------------------
authenticator = stauth.Authenticate(
    {"usernames": stauth_credentials},
    cookie_name="roofing_auth",
    key=os.getenv("AUTH_COOKIE_KEY", "fallback_key"),
    cookie_expiry_days=30,
)

# --- Authentication flow ------------------------------------------------------
# Call login exactly once
login_result = authenticator.login("main")

# If it returned a tuple, unpack it; otherwise fall back to session_state
if isinstance(login_result, tuple):
    name, auth_status, username = login_result
else:
    name        = st.session_state.get("name")
    auth_status = st.session_state.get("authentication_status")
    username    = st.session_state.get("username")

# Now handle each case
if auth_status is False:
    st.error("❌ Incorrect username or password.")
    st.stop()
elif auth_status is None:
    st.warning("⚠ Please enter your credentials.")
    st.stop()

# --- Post-login --------------------------------------------------------------
role = user_roles.get(username, "")
st.sidebar.markdown(f"**Logged in as:** `{username}` ({role})")
authenticator.logout("Log out", "sidebar")
show_system_metrics(role)

# Define tabs per role
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

available = tabs_by_role.get(role, {})
if not available:
    st.error(f"🚫 Role '{role}' has no available tabs.")
    st.stop()

st.sidebar.title("📚 Menu")
choice = st.sidebar.radio("Go to", list(available.keys()))
available[choice]()
