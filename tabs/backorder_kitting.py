import streamlit as st
import pandas as pd
from datetime import datetime
from zoneinfo import ZoneInfo
from supabase import create_client
import os
from fpdf import FPDF

# Supabase client
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# Assumes you already defined generate_pulltag_pdf somewhere
from warehouse_kitting import generate_pulltag_pdf

def run():
    st.title("🔁 Backorder Kitting")

    user = st.session_state.get("username", "unknown")
    now = datetime.now(ZoneInfo("America/Los_Angeles")).isoformat()

    # Show last success + PDF if applicable
    if st.session_state.get("last_bo_pdf"):
        pdf_info = st.session_state.pop("last_bo_pdf")
        st.download_button("📄 Download Backorder Kitting PDF", pdf_info["data"], pdf_info["filename"], mime="application/pdf")

    if st.session_state.pop("bo_success", False):
        st.success("✅ Backorder batch submitted!")
        st.toast("🎉 Backorder data submitted successfully.")
        st.balloons()

    # Warehouse selection
    warehouses = supabase.table("warehouses").select("name").order("name").execute().data
    warehouse_options = [w["name"] for w in warehouses]
    selected_warehouse = st.selectbox("Select Warehouse", warehouse_options)

    # Fetch batch_ids with unresolved backorders
    batch_results = (
        supabase.table("batch_backorders")
        .select("batch_id", "shorted_qty", "fulfilled_qty")
        .gt("shorted_qty", "fulfilled_qty")
        .execute()
    )
    
    open_batches = sorted(set(row["batch_id"] for row in batch_results.data))
    if not open_batches:
        st.info("No batches with open backorders.")
        return
    
    selected_batch = st.selectbox("Select a Backorder Batch", open_batches)
    
    # Load open backorders
    result = supabase.table("batch_backorders").select("*") \
        .eq("batch_id", selected_batch) \
        .gt("shorted_qty", "fulfilled_qty") \
        .order("item_code") \
        .execute()

    rows = result.data or []
    if not rows:
        st.info("No open backorders.")
        return

    df = pd.DataFrame(rows)
    df["remaining"] = df["shorted_qty"] - df["fulfilled_qty"]
    df["kitted_qty"] = 0

    st.subheader("📦 Backorders to Fulfill")
    with st.form("backorder_form"):
        edited = st.data_editor(df[["batch_id", "item_code", "shorted_qty", "fulfilled_qty", "remaining", "kitted_qty", "note"]],
                                use_container_width=True, key="bo_table")
        submitted = st.form_submit_button("✅ Submit Backorder Fulfillment")

    if not submitted:
        return

    #prevent against empty submissions
    if edited["kitted_qty"].sum() <= 0:
        st.warning("⚠️ No backorder quantities were entered. Nothing to submit.")
        return

    try:
        summary_logs = []
        for _, row in edited.iterrows():
            qty = int(row["kitted_qty"])
            remaining = row["remaining"]
            if qty <= 0:
                continue

            if qty > remaining:
                st.warning(f"❌ Cannot kit more than remaining ({remaining}) for item {row['item_code']}.")
                st.stop()

            # Update batch_backorders
            total_fulfilled = row["fulfilled_qty"] + qty
            is_resolved = total_fulfilled >= row["shorted_qty"]
            update_data = {
                "fulfilled_qty": total_fulfilled,
                "note": row.get("note", "")
            }
            if is_resolved:
                update_data["resolved_by"] = user
                update_data["fulfillment_time"] = now

            supabase.table("batch_backorders").update(update_data).eq("id", row["id"]).execute()

            # Get matching pulltags with backorder_qty > 0
            tag_rows = supabase.table("pulltags").select("*") \
                .eq("batch_id", row["batch_id"]).eq("item_code", row["item_code"]).gt("backorder_qty", 0).execute().data
            tags_df = pd.DataFrame(tag_rows)
            tags_df = tags_df.sort_values("backorder_qty", ascending=False)

            # Distribute qty proportionally
            total_bo = tags_df["backorder_qty"].sum()
            proportions = [q / total_bo for q in tags_df["backorder_qty"]]
            alloc = [int(p * qty) for p in proportions]
            diff = qty - sum(alloc)
            for i in range(diff):
                alloc[i % len(alloc)] += 1

            for i, (_, tag) in enumerate(tags_df.iterrows()):
                pulled = alloc[i]
                new_kitted = tag["kitted_qty"] + pulled
                new_bo_qty = tag["backorder_qty"] - pulled
                new_status = "resolved" if new_bo_qty == 0 else "partially resolved"

                supabase.table("pulltags").update({
                    "kitted_qty": new_kitted,
                    "backorder_qty": new_bo_qty,
                    "backorder_status": new_status,
                    "resolved_on": now if new_bo_qty == 0 else None,
                    "updated_by": user
                }).eq("uid", tag["uid"]).execute()

                supabase.table("kitting_logs").insert({
                    "pulltag_uid": tag["uid"],
                    "batch_id": tag["batch_id"],
                    "item_code": tag["item_code"],
                    "description": tag["description"],
                    "cost_code": tag["cost_code"],
                    "job_number": tag["job_number"],
                    "lot_number": tag["lot_number"],
                    "quantity": pulled,
                    "note": row.get("note", ""),
                    "warehouse": selected_warehouse,
                    "kitting_type": "backorder",
                    "kitted_by": user,
                    "kitted_on": now
                }).execute()

                summary_logs.append({
                    "job_number": tag["job_number"],
                    "lot_number": tag["lot_number"],
                    "cost_code": tag["cost_code"],
                    "item_code": tag["item_code"],
                    "quantity": pulled,
                    "kitted_by": user,
                    "kitted_on": now
                })

        if summary_logs:
            df_summary = pd.DataFrame(summary_logs)
            pdf_bytes = generate_pulltag_pdf(df_summary, title="Backorder Kitting Summary")
            st.session_state["last_bo_pdf"] = {
                "data": pdf_bytes,
                "filename": f"backorder_kitting_{now[:10]}.pdf"
            }
            st.session_state["bo_success"] = True
            st.rerun()

    except Exception as e:
        st.error(f"❌ Error during submission: {e}")
