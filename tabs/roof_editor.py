import streamlit as st
import pandas as pd
import os
from supabase import create_client, Client
from field_tracker import tracked_input  # persistence logic

# --- Constants ---
TAB_NAME = "roof_editor"

# --- Supabase Init ---
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- DB Functions ---
def load_roof_types():
    result = (
        supabase.table("roof_type")
        .select("*")
        .order("roof_type")
    ).execute()
    return result.data or []


def roof_type_exists(roof_type, cost_code):
    result = supabase.table("roof_type").select("*").match({
        "roof_type": roof_type,
        "cost_code": cost_code
    }).execute()
    return len(result.data) > 0


def add_roof_type(roof_type, cost_code):
    return supabase.table("roof_type").insert({
        "roof_type": roof_type,
        "cost_code": cost_code
    }).execute()


def delete_roof_type(roof_type, cost_code):
    return supabase.table("roof_type").delete().match({
        "roof_type": roof_type,
        "cost_code": cost_code
    }).execute()


# --- Tab Entrypoint ---
def run():
    st.title("🏠 Roof Types Editor")

    user = st.session_state.get("user", {})
    username = user.get("username", "Unknown")
    role = user.get("role", "N/A")

    st.markdown(f"Logged in as: `{username}` | Role: `{role}`")
    st.divider()

    # === Section: View Table ===
    st.subheader("📋 Current Roof Type Rules")
    data = load_roof_types()
    df = pd.DataFrame(data)
    st.dataframe(df, use_container_width=True)

    st.divider()
    st.subheader("➕ Add New Roof Type Rule")

    with st.form("add_roof_type_form", clear_on_submit=False):
        roof_type = tracked_input("Roof Type", "add_roof_type",
                                  username, TAB_NAME, supabase).strip().upper()
        cost_code = tracked_input("Cost Code", "add_cost_code",
                                  username, TAB_NAME, supabase).strip().upper()
        submitted = st.form_submit_button("Add Entry")

        if submitted:
            if not roof_type or not cost_code:
                st.warning("Both fields are required.")
            elif roof_type_exists(roof_type, cost_code):
                st.warning("❗This roof type and cost code combo already exists.")
            else:
                try:
                    response = add_roof_type(roof_type, cost_code)
                    if response.data:
                        st.success(f"✅ Added `{roof_type} - {cost_code}`")
                        st.rerun()
                    else:
                        st.error(f"Insert failed. Full response: {response}")
                except Exception as e:
                    st.error(f"Unexpected error: {e}")

    st.divider()
    st.subheader("🗑️ Delete Roof Type Rule")

    with st.form("delete_roof_type_form", clear_on_submit=False):
        roof_type_del = tracked_input("Roof Type to Delete", "delete_roof_type",
                                      username, TAB_NAME, supabase).strip().upper()
        cost_code_del = tracked_input("Cost Code to Delete", "delete_cost_code",
                                      username, TAB_NAME, supabase).strip().upper()
        submitted_del = st.form_submit_button("Delete Entry")

        if submitted_del:
            if not roof_type_del or not cost_code_del:
                st.warning("Both fields are required.")
            else:
                try:
                    response = delete_roof_type(roof_type_del, cost_code_del)
                    if response.data:
                        st.success(f"🗑️ Deleted `{roof_type_del} - {cost_code_del}`")
                        st.rerun()
                    else:
                        st.error(f"Delete failed. Full response: {response}")
                except Exception as e:
                    st.error(f"Unexpected error: {e}")

    if st.button("🔄 Refresh Page"):
        st.rerun()
