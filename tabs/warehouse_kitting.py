import streamlit as st
import pandas as pd
from datetime import datetime
from zoneinfo import ZoneInfo
from supabase import create_client
import os

# Supabase client
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

def run():
    st.title("🏗️ Warehouse Kitting")

    user = st.session_state.get("username", "unknown")
    now = datetime.now(ZoneInfo("America/Los_Angeles")).isoformat()

    # 1. Filter for un-kitted batches only
    batch_data = (
        supabase.table("pulltags")
        .select("batch_id", "status")
        .neq("status", "kitted")
        .not_.is_("batch_id", None)
        .execute()
    )
    batches = sorted({row["batch_id"] for row in batch_data.data})
    batch_id = st.selectbox("Select a batch to kit", batches)

    if not batch_id:
        st.stop()

    # 2. Load all pulltags for selected batch
    res = supabase.table("pulltags").select("*").eq("batch_id", batch_id).execute()
    df = pd.DataFrame(res.data)
    if df.empty:
        st.warning("No pulltags found for this batch.")
        return

    # 3. Generate master item summary
    master = (
        df.groupby(["item_code", "description", "cost_code", "uom"])
        .agg(requested_qty=("quantity", "sum"))
        .reset_index()
    )
    master["kitted_qty"] = master["requested_qty"]
    master["note"] = ""

    st.subheader("📦 Kit Master List")
    with st.form("kitting_form"):
        editable_df = st.data_editor(master, use_container_width=True, key="kitting_edit")
        submitted = st.form_submit_button("✅ Submit Kitting")

    if not submitted:
        return

    # 4. Validation: No kitted qty over requested
    overkits = editable_df[editable_df["kitted_qty"] > editable_df["requested_qty"]]
    if not overkits.empty:
        st.error("❌ One or more items exceed the requested quantity. Please correct.")
        st.stop()

    # 5. Group original pulltags by item_code
    pulltags_dict = df.groupby("item_code")

    try:
        for _, row in editable_df.iterrows():
            item_code = row["item_code"]
            desc = row["description"]
            cost_code = row["cost_code"]
            uom = row["uom"]
            total_requested = row["requested_qty"]
            total_kitted = int(row["kitted_qty"])
            note = row.get("note", "")

            matching_rows = pulltags_dict.get_group(item_code).copy()
            allocations = matching_rows["quantity"].tolist()
            total_alloc = sum(allocations)

            # Avoid divide-by-zero
            if total_alloc == 0:
                proportions = [1 / len(allocations)] * len(allocations)
            else:
                proportions = [q / total_alloc for q in allocations]

            # Floor-based distribution
            base_alloc = [int(p * total_kitted) for p in proportions]
            distributed_total = sum(base_alloc)
            remainder = total_kitted - distributed_total
            for i in range(remainder):
                base_alloc[i] += 1
            dist_kitted = base_alloc

            # Log any shortfall
            shortfall = max(total_requested - total_kitted, 0)
            if shortfall > 0:
                existing_bo = supabase.table("batch_backorders").select("*") \
                    .eq("batch_id", batch_id).eq("item_code", item_code).execute().data
                if not existing_bo:
                    supabase.table("batch_backorders").insert({
                        "batch_id": batch_id,
                        "item_code": item_code,
                        "shorted_qty": shortfall,
                        "fulfilled_qty": 0
                    }).execute()

            # Insert logs + update pulltags
            for i, (_, tag_row) in enumerate(matching_rows.iterrows()):
                uid = tag_row["uid"]
                job = tag_row["job_number"]
                lot = tag_row["lot_number"]
                qty = dist_kitted[i]
                shorted = max(tag_row["quantity"] - qty, 0)

                # Log
                supabase.table("kitting_logs").insert({
                    "pulltag_uid": uid,
                    "batch_id": batch_id,
                    "item_code": item_code,
                    "description": desc,
                    "cost_code": cost_code,
                    "job_number": job,
                    "lot_number": lot,
                    "quantity": qty,
                    "note": note,
                    "kitting_type": "initial",
                    "kitted_by": user,
                    "kitted_on": now
                }).execute()

                # Update pulltag snapshot
                supabase.table("pulltags").update({
                    "kitted_qty": qty,
                    "shorted": shorted,
                    "backorder_qty": shorted,
                    "status": "kitted",
                    "kitted_on": now,
                    "updated_by": user
                }).eq("uid", uid).execute()

        st.success("✅ Batch kitting complete!")
        st.experimental_rerun()  # Prevent double submission on reload

    except Exception as e:
        st.error(f"❌ Error during submission: {e}")
