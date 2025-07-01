from field_tracker import tracked_input
import streamlit as st
from supabase import create_client, Client
import os
import pandas as pd

# --- Supabase Setup ---
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

TAB_NAME = "items_editor"

def run():
    st.title("📦 Items Master Editor")

    username = st.session_state.get("username")

    subtab = st.tabs([
        "➕ Add / ❌ Delete Items",
        "✏️ Edit Existing Item",
        "📄 View & Filter Table"
    ])

    # --- Add/Delete Subtab ---
    with subtab[0]:
        st.subheader("➕ Add New Item")

        with st.form("add_item_form"):
            item_code = tracked_input("Item Code", "add_item_code", username, TAB_NAME).strip().upper()
            description = tracked_input("Description", "add_description", username, TAB_NAME)
            uom = tracked_input("Unit of Measure", "add_uom", username, TAB_NAME)
            submitted = st.form_submit_button("Add Item")

            if submitted:
                if not item_code:
                    st.warning("Item Code is required.")
                else:
                    exists = supabase.table("items_master") \
                        .select("item_code") \
                        .eq("item_code", item_code).execute()
                    if exists.data:
                        st.error("❌ Item Code already exists.")
                    else:
                        supabase.table("items_master").insert({
                            "item_code": item_code,
                            "description": description,
                            "uom": uom
                        }).execute()
                        st.success(f"✅ Item '{item_code}' added.")

        st.divider()

        # Unchanged delete section
        st.subheader("❌ Delete Existing Item")
        items = supabase.table("items_master").select("item_code").order("item_code").execute().data
        item_codes = [item["item_code"] for item in items]
        if item_codes:
            selected_item = st.selectbox("Select Item Code to Delete", item_codes)
            if st.button("Delete Selected Item"):
                supabase.table("items_master").delete().eq("item_code", selected_item).execute()
                st.success(f"🗑️ Item '{selected_item}' deleted.")
        else:
            st.info("No items available to delete.")

    # --- Edit Subtab ---
    with subtab[1]:
        st.subheader("✏️ Edit Existing Item")

        items = supabase.table("items_master").select("*").order("item_code").execute().data
        df = pd.DataFrame(items)

        if df.empty:
            st.info("No items found.")
        else:
            selected_code = st.selectbox("Select Item Code to Edit", df["item_code"].tolist(), key="edit_selectbox")
            selected_row = df[df["item_code"] == selected_code].iloc[0]

            with st.form("edit_item_form"):
                desc_key = f"edit_desc_{selected_code}"
                uom_key = f"edit_uom_{selected_code}"

                new_description = tracked_input("Description", desc_key, username, TAB_NAME, default=selected_row["description"] or "")
                new_uom = tracked_input("Unit of Measure", uom_key, username, TAB_NAME, default=selected_row["uom"] or "")
                submitted = st.form_submit_button("Update Item")

                if submitted:
                    supabase.table("items_master") \
                        .update({
                            "description": new_description,
                            "uom": new_uom
                        }) \
                        .eq("item_code", selected_code) \
                        .execute()
                    st.success(f"✅ Item '{selected_code}' updated.")
