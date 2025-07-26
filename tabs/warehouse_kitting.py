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
#helper function to make a pdf
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
    st.title("🏗️ Warehouse Kitting")

    user = st.session_state.get("username", "unknown")
    now = datetime.now(ZoneInfo("America/Los_Angeles")).isoformat()
    
    # Handle cached success state + PDF after submission
    if st.session_state.get("last_kitted_pdf"):
        pdf_info = st.session_state.pop("last_kitted_pdf")
        st.download_button(
            label="📄 Download Kitting Summary PDF",
            data=pdf_info["data"],
            file_name=pdf_info["filename"],
            mime="application/pdf"
        )
    
    if st.session_state.pop("show_success", False):
        st.success("✅ Batch kitting complete!")
        st.toast("🎉 Kitting data submitted successfully.")
        st.balloons()

    
    #reprint older batches section, only initial kits here

    st.header("📄 Reprint Kitting Summary")
    
    reprint_batch = st.text_input("Enter a batch ID to reprint:")
    st.caption("Reprints only show original kits from this tab (not backorders).")
    
    if reprint_batch:
        result = supabase.table("kitting_logs").select("*") \
            .eq("batch_id", reprint_batch).eq("kitting_type", "initial").execute()
        data = result.data or []
    
        if not data:
            st.warning("No initial kitting logs found for this batch.")
        else:
            #here
            df = pd.DataFrame([
                {
                    "job_number": r["job_number"],
                    "lot_number": r["lot_number"],
                    "cost_code": r["cost_code"],
                    "item_code": r["item_code"],
                    "quantity": r["quantity"],
                    "kitted_by": r.get("kitted_by", ""),
                    "kitted_on": r.get("kitted_on", "")
                }
                for r in data
            ])
            
            pdf_bytes = generate_pulltag_pdf(df, title=f"Reprint: Batch {reprint_batch}")
            st.download_button(
                label="Download Reprint PDF",
                data=pdf_bytes,
                file_name=f"kitting_{reprint_batch}_reprint.pdf",
                mime="application/pdf"
            )
    
    st.markdown("---")  # Divider before the actual kitting workflow

    
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
    #enter warehouse
    warehouses = supabase.table("warehouses").select("name").order("name").execute().data
    warehouse_options = [w["name"] for w in warehouses]
    selected_warehouse = st.selectbox("Select Warehouse", warehouse_options)

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
    summary_df = []

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
                        "fulfilled_qty": 0,
                        "warehouse": selected_warehouse,
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
                    "warehouse": selected_warehouse,
                    "kitting_type": "initial",
                    "kitted_by": user,
                    "kitted_on": now
                }).execute()

                # Update pulltag snapshot
                supabase.table("pulltags").update({
                    "kitted_qty": qty,
                    "shorted": shorted,
                    "backorder_qty": shorted,
                    "warehouse": selected_warehouse,
                    "backorder_status": "pending" if shorted > 0 else "none",
                    "status": "kitted",
                    "kitted_on": now,
                    "updated_by": user
                }).eq("uid", uid).execute()

                #here
                summary_df.append({
                    "job_number": job,
                    "lot_number": lot,
                    "cost_code": cost_code,
                    "item_code": item_code,
                    "quantity": qty,
                    "kitted_by": user,
                    "kitted_on": now
                })
        
        pdf_df = pd.DataFrame(summary_df)
        pdf_bytes = generate_pulltag_pdf(pdf_df, title=f"Kitting Summary for Batch {batch_id}")

        #here
        st.session_state["last_kitted_pdf"] = {
            "data": pdf_bytes,
            "filename": f"kitting_{batch_id}.pdf",
            "title": f"Kitting Summary for Batch {batch_id}"
        }
        st.session_state["show_success"] = True
        st.rerun()
        

    except Exception as e:
        st.error(f"❌ Error during submission: {e}")
