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
def generate_pulltag_pdf(df: pd.DataFrame, title: str | None = None) -> bytes:
    """Return PDF bytes summarising requested pulltags, ordered by lot."""
    df_sorted = (
        df.assign(lot_number_num=pd.to_numeric(df["lot_number"], errors="ignore"))
          .sort_values(["lot_number_num", "item_code"], kind="stable")
          .drop(columns="lot_number_num")
    )

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    title_text = title or "Pulltag Request Summary"
    pdf.cell(0, 10, txt=title_text, ln=True, align="C")
    pdf.ln(4)

    # 👇  add Cost column
    headers     = ["Job", "Lot", "Cost", "Item", "Qty", "By", "Time"]
    col_widths  = [25,    25,   25,    30,    15,   24,   40]

    for header, w in zip(headers, col_widths):
        pdf.cell(w, 8, header, border=1, align="C")
    pdf.ln()
    #here
    # Add row data
    for _, row in df_sorted.iterrows():
        pdf.cell(col_widths[0], 8, str(row["job_number"]), border=1)
        pdf.cell(col_widths[1], 8, str(row["lot_number"]), border=1)
        pdf.cell(col_widths[2], 8, str(row["cost_code"]), border=1)
        pdf.cell(col_widths[3], 8, str(row["item_code"]), border=1)
        pdf.cell(col_widths[4], 8, str(row["quantity"]), border=1, align="R")
        pdf.cell(col_widths[5], 8, str(row.get("kitted_by", "")), border=1)
        pdf.cell(col_widths[6], 8, str(row.get("kitted_on", ""))[:16], border=1)  # truncate for fit
        pdf.ln()
        
    return pdf.output(dest="S").encode("latin1")


def run():
    st.title("🔁 Backorder Kitting")

    user = st.session_state.get("username", "unknown")
    now = datetime.now(ZoneInfo("America/Los_Angeles")).isoformat()
 
    warehouses = supabase.table("warehouses").select("name").order("name").execute().data
    warehouse_options = [w["name"] for w in warehouses]
 
    # Show last success + PDF if applicable
    if st.session_state.get("last_bo_pdf"):
        pdf_info = st.session_state.pop("last_bo_pdf")
        st.download_button("📄 Download Backorder Kitting PDF", pdf_info["data"], pdf_info["filename"], mime="application/pdf")

    if st.session_state.pop("bo_success", False):
        st.success("✅ Backorder batch submitted!")
        st.toast("🎉 Backorder data submitted successfully.")
        st.balloons()
    #print old backorder batches:

    st.header("📄 Reprint Backorder Kitting Summary")
    
    with st.expander("Show backorder reprint options"):
        #update here
        with st.expander("📅 Reprint by Date"):
            date_range = st.date_input("Filter by date range", [], format="YYYY-MM-DD")
        
        filter_warehouse = st.selectbox("Filter by warehouse (optional)", ["All"] + warehouse_options)
        filter_batch = st.text_input("Filter by Batch ID (optional)")
        
        query = supabase.table("kitting_logs").select("*").eq("kitting_type", "backorder")
        
        if filter_batch:
            query = query.eq("batch_id", filter_batch)
        if filter_warehouse != "All":
            query = query.eq("warehouse", filter_warehouse)
        
        logs = query.execute().data or []
        
        if logs and len(date_range) == 2:
            start, end = pd.to_datetime(date_range[0]), pd.to_datetime(date_range[1])
            logs = [r for r in logs if start <= pd.to_datetime(r["kitted_on"]) <= end]
        
        if not logs:
            st.info("No matching backorder logs found.")
        else:
            df_logs = pd.DataFrame(logs)
            df_logs = df_logs[[
                "job_number", "lot_number", "cost_code", "item_code",
                "quantity", "kitted_by", "kitted_on"
            ]]

            #items total summary
            # 📊 Summary by item_code
            summary_by_item = (
                df_logs.groupby("item_code")
                .agg(total_kitted=("quantity", "sum"))
                .reset_index()
                .sort_values("item_code")
            )
            
            st.caption("Item Summary from Filtered Reprint Logs")
            st.dataframe(summary_by_item, use_container_width=True)

            
            pdf_bytes = generate_pulltag_pdf(df_logs, title="Backorder Kitting Reprint")
            st.download_button("📥 Download Reprint PDF", pdf_bytes, file_name="backorder_kitting_reprint.pdf", mime="application/pdf")


    # Warehouse selection
    selected_warehouse = st.selectbox("Select Warehouse", warehouse_options)

    # Fetch batch_ids with unresolved backorders
    batch_results = (
        supabase.table("batch_backorders")
        .select("batch_id", "shorted_qty", "fulfilled_qty")
        .execute()
    )
    
    # Filter in Python
    batch_data = [r for r in batch_results.data or [] if r["shorted_qty"] > r["fulfilled_qty"]]
    open_batches = sorted(set(row["batch_id"] for row in batch_data))

    if not open_batches:
        st.info("No batches with open backorders.")
        return
    
    selected_batch = st.selectbox("Select a Backorder Batch", open_batches)
    
    # Load open backorders
    # Fetch all backorders for selected batch, then filter manually
    result = supabase.table("batch_backorders").select("*").eq("batch_id", selected_batch).order("item_code").execute()
    rows = result.data or []
    rows = [r for r in rows if r["shorted_qty"] > r["fulfilled_qty"]]

    if not rows:
        st.info("No open backorders.")
        return

    df = pd.DataFrame(rows)
    df["remaining"] = df["shorted_qty"] - df["fulfilled_qty"]
    df["kitted_qty"] = 0

    st.subheader("📦 Backorders to Fulfill")
    editable_cols = ["id", "batch_id", "item_code", "shorted_qty", "fulfilled_qty", "remaining", "kitted_qty", "note"]
    with st.form("backorder_form"):
        edited = st.data_editor(df[editable_cols], use_container_width=True, key="bo_table", column_config={
            "id": st.column_config.TextColumn(disabled=True, label=""),
            "shorted_qty": st.column_config.NumberColumn(disabled=True),
            "fulfilled_qty": st.column_config.NumberColumn(disabled=True),
            "remaining": st.column_config.NumberColumn(disabled=True),
        })

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
