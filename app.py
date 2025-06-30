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

# Supabase setup
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# Debug environment variables
st.write(f"SUPABASE_URL: {SUPABASE_URL}, SUPABASE_KEY: {SUPABASE_KEY}, AUTH_COOKIE_KEY: {os.environ.get('AUTH_COOKIE_KEY')}")

# Fetch users
response = supabase.table("users").select("username, password, role").execute()
st.write(f"Supabase Response: {response.data}")  # Debug: Check data
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
st.write(f"Credentials: {credentials}")  # Debug: Inspect credentials

authenticator = stauth.Authenticate(
    credentials,
    cookie_name="roofing_auth",
    key=os.environ.get("AUTH_COOKIE_KEY", "default_fallback_key"),
    cookie_expiry_days=30
)

# Login with error handling
login_result = authenticator.login("main", "Login")
if login_result is None:
    st.error("Authentication failed. Please check your credentials or Supabase connection.")
    st.stop()
name, auth_status, username = login_result

if not auth_status:
    st.stop()

role = credentials["usernames"][username]["role"]  # Fixed: Access role safely
