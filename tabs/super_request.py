import streamlit as st
import pandas as pd
import os
import uuid
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
# ─────────────────────────────────────────────

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
    """Return PDF bytes summarising requested pulltags."""
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    title_text = title or "Pulltag Request Summary"
    pdf.cell(0, 10, txt=title_text, ln=True, align="C")
    pdf.ln(4)

    headers = ["Job", "Lot", "Item", "Qty"]
    col_widths = [30, 30, 40, 20]
    for header, w in zip(headers, col_widths):
        pdf.cell(w, 8, header, border=1, align="C")
    pdf.ln()

    for _, row in df.iterrows():
        pdf.cell(col_widths[0], 8, row.get("job_number", ""), border=1)
        pdf.cell(col_widths[1], 8, row.get("lot_number", ""), border=1)
        pdf.cell(col_widths[2], 8, row.get("item_code", ""), border=1)
        pdf.cell(col_widths[3], 8, str(row.get("quantity", "")), border=1, ln=1)

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

        job_input = st.text_input("Job number").strip().upper()
        if job_input:
            lots_available = (
                lookup_df.query("job_number == @job_input and status == 'pending'")
                .lot_number.unique()
                .tolist()
            )
            if not lots_available:
                st.info("No pending lots for this job.")
            else:
                lot_selected = st.selectbox("Select lot", lots_available, key="lot_select")
                if st.button("➕ Add") and lot_selected:
                    pair = {"job_number": job_input, "lot_number": str(lot_selected)}
                    if pair not in st.session_state["req_pairs"]:
                        st.session_state["req_pairs"].append(pair)

        # Display current list
        pairs_df = pd.DataFrame(st.session_state["req_pairs"])
        if not pairs_df.empty:
            st.table(pairs_df)
            # Remove buttons
            for i, row in pairs_df.iterrows():
                key = f"del_{row['job_number']}_{row['lot_number']}_{i}"
                if st.button("🗑", key=key):
                    st.session_state["req_pairs"].pop(i)
                    st.rerun()


        # Submit section
        disabled_submit = len(st.session_state["req_pairs"]) == 0 or not user
        if st.button("🚀 Submit requests", disabled=disabled_submit):
            batch_id = f"{user}-{uuid.uuid4().hex[:5].upper()}"
            with st.spinner("Validating & committing…"):
                # Re‑query live statuses to avoid race conditions
                filters = " | ".join(
                    [f"(job_number == '{p['job_number']}' and lot_number == '{p['lot_number']}')" for p in st.session_state["req_pairs"]]
                )
                live_df = (
                    client.table("pulltags")
                    .select("job_number, lot_number, status")
                    .execute()
                    .df()
                    .query(filters)
                ) if filters else pd.DataFrame()

                warnings = []
                to_update = []
                for p in st.session_state["req_pairs"]:
                    row = live_df[(live_df.job_number == p["job_number"]) & (live_df.lot_number == p["lot_number"])]
                    if row.empty:
                        warnings.append((p, "not found"))
                    elif row.iloc[0].status != "pending":
                        warnings.append((p, f"already {row.iloc[0].status}"))
                    else:
                        to_update.append(p)

                if warnings:
                    st.warning("Some pairs were skipped:")
                    st.table(pd.DataFrame([{**w[0], "reason": w[1]} for w in warnings]))

                if to_update:
                    utc_now = datetime.now(timezone.utc).isoformat()
                    rows = [{
                        **p,
                        "status": "requested",
                        "requested_by": user,
                        "requested_on": utc_now,
                        "batch_id": batch_id,
                    } for p in to_update]
                    res = client.table("pulltags").upsert(rows).execute()
                    if res.error:
                        st.error(res.error.message)
                    else:
                        st.success(f"Queued {len(rows)} lot(s) under batch {batch_id}")
                        pdf_bytes = generate_pulltag_pdf(pd.DataFrame(rows), title=f"Batch {batch_id}")
                        st.download_button(
                            "📄 Download summary PDF",
                            data=pdf_bytes,
                            file_name=f"{batch_id}.pdf",
                            mime="application/pdf",
                        )
                        st.session_state["req_pairs"] = []  # reset

    # ─────────────────────────────────────────────
    # RE‑PRINT BATCH TAB
    # ─────────────────────────────────────────────
    with tab_reprint:
        st.subheader("Re‑print existing batch")
        batch = st.text_input("Enter batch_id to re‑print").strip()
        if st.button("🔍 Fetch batch") and batch:
            res = (
                client.table("pulltags")
                .select("job_number, lot_number, item_code, quantity")
                .eq("batch_id", batch)
                .order("job_number")
                .execute()
            )
            if res.error:
                st.error(res.error.message)
            elif not res.data:
                st.info("No rows found for that batch_id.")
            else:
                df = pd.DataFrame(res.data)
                st.table(df)
                pdf_bytes = generate_pulltag_pdf(df, title=f"Batch {batch}")
                st.download_button(
                    "📄 Download batch PDF",
                    data=pdf_bytes,
                    file_name=f"{batch}.pdf",
                    mime="application/pdf",
                )

# Allow running standalone for local dev\if __name__ == "__main__":
    run()
