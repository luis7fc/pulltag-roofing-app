# ─────────────────────────────────────────────────────────────────────────────
# pages/sage_export.py  –  Supabase version (no psycopg cursor)
# ─────────────────────────────────────────────────────────────────────────────
import io, os, re
from datetime import date, datetime

import pandas as pd
import streamlit as st
from supabase import create_client, Client

# ─────────────────────────────────────────────────────────────────────────────
# Supabase client  (anon key is fine for read-only queries)
# ─────────────────────────────────────────────────────────────────────────────
SB_URL = os.environ["SUPABASE_URL"]
SB_KEY = os.environ["SUPABASE_KEY"]
supabase: Client = create_client(SB_URL, SB_KEY)

# ─────────────────────────────────────────────────────────────────────────────
# Session-state bootstrap
# ─────────────────────────────────────────────────────────────────────────────
def _init_state() -> None:
    ss = st.session_state
    ss.setdefault("loaded_df",  pd.DataFrame())
    ss.setdefault("edited_df",  pd.DataFrame())
    ss.setdefault("grid_ready", False)


# ─────────────────────────────────────────────────────────────────────────────
# DB helpers (Supabase-style)
# ─────────────────────────────────────────────────────────────────────────────
def distinct_values(field: str, table: str) -> list[str]:
    """Fetch distinct values for a field from Supabase."""
    res = supabase.table(table).select(field).execute()
    vals = {r[field] for r in res.data if r[field] is not None}
    return sorted(vals)


def fetch_kitting_logs(
    batch_ids:   list[str] | None = None,
    warehouses:  list[str] | None = None,
    k_types:     list[str] | None = None,
    start_date:  datetime | None  = None,
    end_date:    datetime | None  = None,
) -> pd.DataFrame:
    """
    Query kitting_logs with optional filters (at least one required),
    then left-join items_master in pandas to pick up UOM/Description.
    """
    if not any([batch_ids, warehouses, k_types, start_date, end_date]):
        raise ValueError("Add at least one filter before querying.")

    qb = supabase.table("kitting_logs").select("*")

    if batch_ids:
        qb = qb.in_("batch_id", batch_ids)
    if warehouses:
        qb = qb.in_("warehouse", warehouses)
    if k_types:
        qb = qb.in_("kitting_type", k_types)
    if start_date:
        qb = qb.gte("kitted_on", start_date.isoformat())
    if end_date:
        qb = qb.lt("kitted_on",  end_date.isoformat())

    logs = qb.execute().data or []
    if not logs:
        return pd.DataFrame()

    df_logs = pd.DataFrame(logs)

    # Grab only the item_codes we need, fetch their UOM/description once
    item_codes = df_logs["item_code"].unique().tolist()
    items = (
        supabase.table("items_master")
        .select("item_code,uom,description")
        .in_("item_code", item_codes)
        .execute()
        .data
    )
    df_items = pd.DataFrame(items) if items else pd.DataFrame(columns=["item_code", "uom", "description"])

    # Left-join (default uom = EA, description = "")
    df = df_logs.merge(df_items, how="left", on="item_code")
    df["uom"].fillna("EA", inplace=True)
    df["description"].fillna("",   inplace=True)

    # Re-order for nice display
    cols = [
        "id", "batch_id", "job_number", "lot_number",
        "item_code", "quantity", "uom", "description",
        "cost_code", "warehouse", "kitting_type", "kitted_on"
    ]
    return df[cols]


# ─────────────────────────────────────────────────────────────────────────────
# TXT builder (unchanged from solar exporter)
# ─────────────────────────────────────────────────────────────────────────────
def build_txt(header: dict, df: pd.DataFrame) -> str:
    kit  = header["kit_date"].strftime("%m-%d-%y")
    acct = header["acct_date"].strftime("%m-%d-%y")

    buf = io.StringIO()
    buf.write(f"I,{header['batch']},{kit},{acct}\n")
    for r in df.itertuples():
        desc = (r.description or "").replace('"', "'")
        buf.write(
            f"IL,{r.warehouse},{r.item_code},{r.quantity},{r.uom},"
            f"\"{desc}\",1,,,"
            f"{r.job_number},{r.lot_number},{r.cost_code},M,,{kit}\n"
        )
    return buf.getvalue()


# ─────────────────────────────────────────────────────────────────────────────
# Main Streamlit tab
# ─────────────────────────────────────────────────────────────────────────────
def run() -> None:
    _init_state()
    ss = st.session_state
    st.title("📤 Sage Export")

    if st.button("🔄 Reset tab"):
        for k in ["loaded_df", "edited_df", "grid_ready"]:
            ss.pop(k, None)
        st.rerun()

    # 1) Filters
    st.subheader("1 • Filters")
    colA, colB = st.columns(2)
    batch_filter = colA.text_input("Batch-ID(s) (comma-separated)", key="batch_filter")
    warehouses   = colB.multiselect("Warehouse filter", distinct_values("warehouse", "kitting_logs"))

    colC, colD = st.columns(2)
    k_types     = colC.multiselect("Kitting Type filter", distinct_values("kitting_type", "kitting_logs"))
    start_date  = colD.date_input("Start date (≥)", value=None)
    end_date    = st.date_input("End date (<)", value=None)

    # Convert dates to datetimes; end_date is exclusive so +1 day
    if start_date:
        start_date = datetime.combine(start_date, datetime.min.time())
    if end_date:
        end_date = datetime.combine(end_date, datetime.min.time()) + pd.Timedelta(days=1)

    if st.button("🔍 Load logs"):
        try:
            batches = [b.strip() for b in batch_filter.split(",") if b.strip()] or None
            df = fetch_kitting_logs(
                batch_ids  = batches,
                warehouses = warehouses or None,
                k_types    = k_types   or None,
                start_date = start_date,
                end_date   = end_date,
            )
            if df.empty:
                st.warning("No records match those filters.")
            else:
                ss.loaded_df  = df
                ss.edited_df  = df.copy()
                ss.grid_ready = True
                st.rerun()
        except ValueError as e:
            st.error(str(e))

    # 2) Editable preview
    if ss.get("grid_ready"):
        st.subheader("2 • Review / edit")
        lock = {"id", "batch_id", "job_number", "lot_number",
                "item_code", "warehouse"}
        cfg = {c: {"disabled": True} for c in lock}

        ss.edited_df = st.data_editor(
            ss.edited_df,
            num_rows="dynamic",
            column_config=cfg,
            key="edit_grid",
        )
        st.markdown("---")

    # 3) Header + export
    st.subheader("3 • Generate Sage TXT")
    c1, c2, c3 = st.columns(3)
    batch_name = c1.text_input("Batch name (header)")
    kit_date   = c2.date_input("Kit date",  value=date.today())
    acct_date  = c3.date_input("Accounting date", value=date.today())

    if st.button("🚀 Download TXT"):
        if ss.edited_df.empty:
            st.warning("Load data first.")
            st.stop()
        if not batch_name.strip():
            st.warning("Batch name is required.")
            st.stop()

        txt = build_txt(
            {"batch": batch_name.strip(), "kit_date": kit_date, "acct_date": acct_date},
            ss.edited_df,
        )
        fname = re.sub(r"\W+", "_", batch_name.strip()) + ".txt"
        st.download_button("📥 Download file", txt, file_name=fname, mime="text/plain")
        st.success(f"TXT generated for {len(ss.edited_df)} lines.")

