import streamlit as st
import pandas as pd
import os
from supabase import create_client, Client

# Initialize Supabase
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def load_roof_types():
    result = supabase.table("roof_type").select("*").order("roof_type", asc=True).execute()
    return result.data if result.data else []

def add_roof_type(roof_type, cost_code):
    return supabase.table("roof_type").insert({"roof_type": roof_type, "cost_code": cost_code}).execute()

def delete_roof_type(roof_type, cost_code):
    return supabase.table("roof_type").delete().match({"roof_type": roof_type, "cost_code": cost_code}).execute()

def run():
    st.title("🏗️ Roof Types Editor")

    user = st.session_state.get("user", {})
    username = user.get("username", "Unknown")
    role = user.get("role", "N/A")

    st.markdown(f"Logged in as: `{username}` | Role: `{role}`")
    st.divider()

    st.subheader("📋 Current Roof Type Rules")
    data = load_roof_types()
    df = pd.DataFrame(data)
    st.dataframe(df, use_container_width=True)

    st.divider()
    st.subheader("➕ Add New Roof Type Rule")

    with st.form("add_roof_type_form", clear_on_submit=True):
        roof_type = st.text_input("Roof Type").strip().upper()
        cost_code = st.text_input("Cost Code").strip().upper()
        submitted = st.form_submit_button("Add Entry")

        if submitted:
            if not roof_type or not cost_code:
                st.warning("Both fields are required.")
            else:
                try:
                    add_roof_type(roof_type, cost_code)
                    st.success(f"✅ Added `{roof_type} - {cost_code}`")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {e}")

    st.divider()
    st.subheader("🗑️ Delete Roof Type Rule")

    with st.form("delete_roof_type_form"):
        roof_type_del = st.text_input("Roof Type to Delete").strip().upper()
        cost_code_del = st.text_input("Cost Code to Delete").strip().upper()
        submitted_del = st.form_submit_button("Delete Entry")

        if submitted_del:
            if not roof_type_del or not cost_code_del:
                st.warning("Both fields are required.")
            else:
                try:
                    delete_roof_type(roof_type_del, cost_code_del)
                    st.success(f"🗑️ Deleted `{roof_type_del} - {cost_code_del}`")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {e}")

    if st.button("🔄 Refresh Page"):
        st.rerun()
