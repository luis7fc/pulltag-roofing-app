import streamlit as st
import pandas as pd
import os
import uuid
from postgrest.exceptions import APIError   # add near your imports
from datetime import datetime, timezone
from fpdf import FPDF
from supabase import create_client, Client
try:
    # supabase‑py ≥ 2.0
    from postgrest.exceptions import APIError
except ImportError:
    # Fallback for supabase‑py 1.x
    from supabase.lib.postgrest import APIError# ─────────────────────────────────────────────

# Helpers
def get_supabase_client() -> Client:
    """Create a Supabase client using **only** environment variables (Render safe)."""
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if not url or not key:
        st.error("Supabase credentials not set in environment variables.")
        st.stop()
    return create_client(url, key)

@st.cache_data(ttl=300)
def get_lookup_df(_client):
    try:
        res = (
            _client.table("pulltags")
            .select("job_number, lot_number, status")
            .execute()
        )
        # v2.x succeeds → res is APIResponse, just grab .data
        return pd.DataFrame(res.data)
    except APIError as e:
        st.error(f"Supabase error {e.code}: {e.message}")
        st.stop()

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
    headers     = ["Job", "Lot", "Cost", "Item", "Qty"]
    col_widths  = [28,    28,   28,    40,    20]   # keep page width ≈ 144 mm
    for header, w in zip(headers, col_widths):
        pdf.cell(w, 8, header, border=1, align="C")
    pdf.ln()

    for _, row in df_sorted.iterrows():
        pdf.cell(col_widths[0], 8, row.get("job_number",  ""), border=1)
        pdf.cell(col_widths[1], 8, row.get("lot_number",  ""), border=1)
        pdf.cell(col_widths[2], 8, row.get("cost_code",   ""), border=1)   # 👈
        pdf.cell(col_widths[3], 8, row.get("item_code",  ""), border=1)
        pdf.cell(col_widths[4], 8, str(row.get("quantity", "")), border=1, ln=1)

    return pdf.output(dest="S").encode("latin1")

# ─────────────────────────────────────────────
# Streamlit Entry Point
# ─────────────────────────────────────────────

def run():
    st.header("Super Request")

    # --- Init session state ---
    st.session_state.setdefault("req_pairs", [])  # list[dict(job_number, lot_number)]

    # --- DB client and cache ---
    client = get_supabase_client()
    lookup_df = get_lookup_df(client)

    if st.button("🔄 Refresh cache", type="secondary"):
        get_lookup_df.clear()
        lookup_df = get_lookup_df(client)
        st.success("Cache refreshed ✅")

    tab_new, tab_reprint = st.tabs(["🆕 New Request", "🔁 Re‑print Batch"])

    # ─────────────────────────────────────────────
    # NEW REQUEST TAB
    # ─────────────────────────────────────────────
    with tab_new:
        st.subheader("Create new batch request")
        user = st.session_state.get("username") or st.session_state.get("user")
        if not user:
            st.warning("User not found in session_state. Ensure login sets 'username'.")
    
        # ---------- lot selection ----------
        job_input = st.text_input(
            "Job number",
            key="newreq_job_number",      # 👈  unique key
        ).strip().upper()
        
        if job_input:
            lots_available = (
                lookup_df.query("job_number == @job_input and status == 'pending'")
                .lot_number.unique()
                .tolist()
            )
        
            if not lots_available:
                st.info("No pending lots for this job.")
            else:
                lots_selected = st.multiselect(
                    "Select lot(s) to add",
                    options=lots_available,
                    key="lots_select",         # persistent key
                )
        
                if st.button("➕ Add selected", disabled=len(lots_selected) == 0):
                    added = 0
                    for lot in lots_selected:
                        pair = {"job_number": job_input, "lot_number": str(lot)}
                        if pair not in st.session_state["req_pairs"]:
                            st.session_state["req_pairs"].append(pair)
                            added += 1
        
                    if added:
                        st.success(f"Added {added} lot(s) from job {job_input}")
        
                    # ✅ clear the selection *after* widget is used
                    st.session_state["lots_select"].clear()
                    st.rerun()   # refresh UI so the multiselect shows empty
        
        # ─────────────────────────────────────────────
        # Display current list & multi‑delete UI
        # ─────────────────────────────────────────────
        pairs_df = pd.DataFrame(st.session_state["req_pairs"])
        
        if pairs_df.empty:
            st.caption("No lots added yet.")
        else:
            st.table(pairs_df)   # read‑only view of current selections
        
            # Build human‑readable labels → "JOB | LOT"
            labels = [
                f"{row.job_number} | {row.lot_number}"
                for row in pairs_df.itertuples()
            ]
        
            # Slim one‑line dropdown with pill chips after selection
            remove_choices = st.multiselect(
                "Select lot(s) to remove",
                options=labels,
                key="rm_select",
            )
        
            if st.button("🗑 Remove selected", disabled=not remove_choices):
                # Remove selected rows (reverse order keeps indices valid)
                for lbl in sorted(remove_choices, key=labels.index, reverse=True):
                    idx = labels.index(lbl)
                    st.session_state["req_pairs"].pop(idx)
                st.success(f"Removed {len(remove_choices)} lot(s)")
                st.rerun()  # refresh UI so the table re‑renders without removed rows
        
        # ────────── Submit section ──────────
        from postgrest.exceptions import APIError   # add near your imports
        
        # ────────── Submit section ──────────
        disabled_submit = len(st.session_state["req_pairs"]) == 0 or not user
        if st.button("🚀 Submit requests", disabled=disabled_submit):
            batch_id = f"{user}-{uuid.uuid4().hex[:5].upper()}"
            with st.spinner("Validating & committing…"):
                # Re‑query live statuses to avoid race conditions
                filters = " | ".join(
                    [f"(job_number == '{p['job_number']}' and lot_number == '{p['lot_number']}')"
                     for p in st.session_state["req_pairs"]]
                )
                if filters:
                    live_res = client.table("pulltags") \
                                     .select("job_number, lot_number, status") \
                                     .execute()
                    live_df = pd.DataFrame(live_res.data).query(filters)
                else:
                    live_df = pd.DataFrame()
        
                warnings, to_update = [], []
                for p in st.session_state["req_pairs"]:
                    row = live_df[
                        (live_df.job_number == p["job_number"])
                        & (live_df.lot_number == p["lot_number"])
                    ]
                    if row.empty:
                        warnings.append({**p, "reason": "not found"})
                    elif row.iloc[0].status != "pending":
                        warnings.append({**p, "reason": f"already {row.iloc[0].status}"})
                    else:
                        to_update.append(p)
        
                if warnings:
                    st.warning("Some pairs were skipped:")
                    st.table(pd.DataFrame(warnings))
        
                # ───── perform updates ─────
                if to_update:
                    utc_now = datetime.now(timezone.utc).isoformat()
                    payload = {
                        "status": "requested",
                        "requested_by": user,
                        "requested_on": utc_now,
                        "batch_id": batch_id,
                    }
        
                    errors = []
                    for p in to_update:
                        try:
                            client.table("pulltags") \
                                  .update(payload) \
                                  .eq("job_number", p["job_number"]) \
                                  .eq("lot_number",  p["lot_number"]) \
                                  .eq("status",      "pending") \
                                  .execute()
                        except APIError as e:
                            errors.append({
                                "job_number": p["job_number"],
                                "lot_number": p["lot_number"],
                                "reason": f"{e.code}: {e.message}"
                            })
        
                    if errors:
                        st.error("Some updates failed:")
                        st.table(pd.DataFrame(errors))
        
                    # fetch rows for PDF (only if at least one succeeded)
                    if len(errors) < len(to_update):
                        #here
                        pdf_res = (
                            client.table("pulltags")
                                  .select("job_number, lot_number, cost_code, item_code, quantity")  # 👈 added
                                  .eq("batch_id", batch_id)
                                  .order("job_number")
                                  .execute()
                        )
                        
                        pdf_df = pd.DataFrame(pdf_res.data)
                        st.success(f"Queued {len(to_update) - len(errors)} lot(s) under batch {batch_id}")
        
                        pdf_bytes = generate_pulltag_pdf(pdf_df, title=f"Batch {batch_id}")
                        st.download_button(
                            "📄 Download summary PDF",
                            data=pdf_bytes,
                            file_name=f"{batch_id}.pdf",
                            mime="application/pdf",
                        )
        
                    st.session_state["req_pairs"] = []  # reset selection

    # ─────────────────────────────────────────────
    # RE‑PRINT BATCH TAB
    # ─────────────────────────────────────────────
    with tab_reprint:
        st.subheader("Re‑print existing batch")
    
        # --- input fields ---
        batch_input = st.text_input("Enter batch_id (optional)").strip()
        st.markdown("— or —")
        
        job_lookup = st.text_input(
            "Job number",
            key="reprint_job_number",     # 👈  different key
        ).strip().upper()
        
        lot_lookup = st.text_input(
            "Lot number",
            key="reprint_lot_number",     # 👈  give the lot box a key too
        ).strip()
    
        if st.button("🔍 Fetch"):
    
            # --------------------------------------------------
            # CASE 1: user gave an explicit batch_id
            # --------------------------------------------------
            if batch_input:
                batch_ids = [batch_input]
    
            # --------------------------------------------------
            # CASE 2: user gave job + lot only
            # --------------------------------------------------
            elif job_lookup and lot_lookup:
                try:
                    resp = (
                        client.table("pulltags")
                              .select("batch_id")
                              .eq("job_number", job_lookup)
                              .eq("lot_number", lot_lookup)
                              .neq("batch_id", None)          # ignore nulls
                              .execute()
                    )
                    batch_ids = sorted({row["batch_id"] for row in resp.data})
                except APIError as e:
                    st.error(f"Supabase error {e.code}: {e.message}")
                    batch_ids = []
    
                if len(batch_ids) == 0:
                    st.info("No batch_id found for that job / lot.")
                    st.stop()
    
                if len(batch_ids) > 1:
                    chosen = st.selectbox(
                        "Multiple batches found – select one",
                        batch_ids,
                        key="batch_pick",
                    )
                    if not chosen:
                        st.stop()
                    batch_ids = [chosen]
    
            else:
                st.warning("Please enter either a batch_id *or* a job & lot.")
                st.stop()
    
            # --------------------------------------------------
            # Fetch rows for the chosen batch_id
            # --------------------------------------------------
            batch_id = batch_ids[0]
    
            try:
                res = (
                    client.table("pulltags")
                          .select("job_number, lot_number, cost_code, item_code, quantity")  # 👈 added
                          .eq("batch_id", batch_id)
                          .order("lot_number")
                          .execute()
                )
                data = res.data
            except APIError as e:
                st.error(f"Supabase error {e.code}: {e.message}")
                st.stop()
    
            if not data:
                st.info(f"No rows found for batch {batch_id}.")
            else:
                df = pd.DataFrame(data)
                st.table(df)
    
                pdf_bytes = generate_pulltag_pdf(df, title=f"Batch {batch_id}")
                st.download_button(
                    "📄 Download batch PDF",
                    data=pdf_bytes,
                    file_name=f"{batch_id}.pdf",
                    mime="application/pdf",
                )
