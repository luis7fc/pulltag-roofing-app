import streamlit as st
import pandas as pd
from datetime import datetime
from zoneinfo import ZoneInfo
from supabase import create_client
import os

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

def run():
    st.title("➕ Add-On Kitting")

    user = st.session_state.get("username", "unknown")
    now = datetime.now(ZoneInfo("America/Los_Angeles")).isoformat()

    # Load warehouses
    warehouses = supabase.table("warehouses").select("name").order("name").execute().data
    warehouse_options = [w["name"] for w in warehouses]
    selected_warehouse = st.selectbox("Warehouse", warehouse_options)

    # Load item codes from items_master
    items = supabase.table("items_master").select("item_code", "description").order("item_code").execute().data
    item_df = pd.DataFrame(items)
    item_lookup = {row["item_code"]: row.get("description", "") for row in items}

    # Entry form for multiple items
    st.subheader("📝 Enter Add-On Kitting Items")
    with st.form("addon_form"):
        input_rows = st.experimental_data_editor(
            pd.DataFrame([{ "item_code": "", "cost_code": "", "job_number": "", "lot_number": "", "quantity": 0 }]),
            num_rows="dynamic",
            use_container_width=True,
            key="addon_table"
        )
        submitted = st.form_submit_button("✅ Submit Add-On Kit")

    if not submitted:
        return

    try:
        for _, row in input_rows.iterrows():
            if not row["item_code"] or not row["job_number"] or not row["lot_number"] or row["quantity"] <= 0:
                continue

            description = item_lookup.get(row["item_code"], "")

            supabase.table("kitting_logs").insert({
                "pulltag_uid": f"addon::{row['item_code']}::{row['job_number']}::{row['lot_number']}",
                "item_code": row["item_code"],
                "description": description,
                "cost_code": row["cost_code"],
                "job_number": row["job_number"],
                "lot_number": row["lot_number"],
                "quantity": int(row["quantity"]),
                "note": "addon",
                "kitting_type": "addon",
                "kitted_by": user,
                "warehouse": selected_warehouse,
                "kitted_on": now
            }).execute()

        st.success("✅ Add-on items logged successfully!")

    except Exception as e:
        st.error(f"❌ Error during submission: {e}")
