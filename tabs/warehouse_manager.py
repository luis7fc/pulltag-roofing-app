import streamlit as st
import pandas as pd
from supabase import create_client
import os

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

def run():
    st.title("🏢 Manage Warehouses")

    # Load current warehouses
    data = supabase.table("warehouses").select("id", "name").order("name").execute()
    warehouses = pd.DataFrame(data.data)

    if warehouses.empty:
        st.info("No warehouses found. Add one below.")
    else:
        st.subheader("📋 Existing Warehouses")
        st.dataframe(warehouses, use_container_width=True)

    st.markdown("---")
    st.subheader("➕ Add New Warehouse")

    with st.form("add_warehouse_form"):
        new_name = st.text_input("Warehouse Name")
        submitted = st.form_submit_button("Add Warehouse")

        if submitted:
            if not new_name.strip():
                st.warning("Warehouse name cannot be empty.")
            else:
                existing = supabase.table("warehouses").select("id").eq("name", new_name.strip()).execute()
                if existing.data:
                    st.warning("Warehouse already exists.")
                else:
                    supabase.table("warehouses").insert({"name": new_name.strip()}).execute()
                    st.success(f"Warehouse '{new_name}' added successfully!")
                    st.experimental_rerun()

    st.markdown("---")
    st.subheader("🗑️ Delete Warehouse")

    if not warehouses.empty:
        to_delete = st.selectbox("Select warehouse to delete", warehouses["name"])
        if st.button("Delete Selected Warehouse"):
            warehouse_id = warehouses.loc[warehouses["name"] == to_delete, "id"].values[0]
            supabase.table("warehouses").delete().eq("id", warehouse_id).execute()
            st.success(f"Warehouse '{to_delete}' deleted.")
            st.experimental_rerun()
