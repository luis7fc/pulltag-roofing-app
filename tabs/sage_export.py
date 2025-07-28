# ─────────────────────────────────────────────────────────────────────────────
# pages/sage_export.py – FINAL VERSION with batch export logic and filters
# ─────────────────────────────────────────────────────────────────────────────
import io, os, re, uuid, random
from datetime import date, datetime
from pytz import timezone
import pandas as pd
import streamlit as st
from supabase import create_client, Client

# ─────────────────────────────────────────────────────────────────────────────
# Supabase client
# ─────────────────────────────────────────────────────────────────────────────
SB_URL = os.environ["SUPABASE_URL"]
SB_KEY = os.environ["SUPABASE_KEY"]
supabase: Client = create_client(SB_URL, SB_KEY)

# ─────────────────────────────────────────────────────────────────────────────
# Init session state
# ─────────────────────────────────────────────────────────────────────────────
def _init_state():
    ss = st.session_state
    ss.setdefault("loaded_df", pd.DataFrame())
    ss.setdefault("edited_df", pd.DataFrame())
    ss.setdefault("grid_ready", False)
    ss.setdefault("download_clicked", False)

# ─────────────────────────────────────────────────────────────────────────────
# DB Helpers
# ─────────────────────────────────────────────────────────────────────────────
def distinct_values(field: str, table: str) -> list[str]:
    res = supabase.table(table).select(field).execute()
    vals = {r[field] for r in res.data if r[field] is not None}
    return sorted(vals)

def fetch_kitting_logs(
    batch_ids: list[str] | None = None,
    warehouses: list[str] | None = None,
    k_types: list[str] | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    export_batch_ids: list[str] | None = None,
) -> pd.DataFrame:
    if not any([batch_ids, warehouses, k_types, start_date, end_date, export_batch_ids]):
        raise ValueError("Add at least one filter before querying.")

    qb = supabase.table("kitting_logs").select("*")

    if batch_ids:
        qb = qb.in_("batch_id", batch_ids)
    if warehouses:
        qb = qb.in_("warehouse", warehouses)
    if k_types:
        qb = qb.in_("kitting_type", k_types)
    if export_batch_ids:
        qb = qb.in_("export_batch_id", export_batch_ids)
    if start_date:
        qb = qb.gte("kitted_on", start_date.isoformat())
    if end_date:
        qb = qb.lt("kitted_on", end_date.isoformat())

    logs = qb.execute().data or []
    if not logs:
        return pd.DataFrame()

    df_logs = pd.DataFrame(logs)
    item_codes = df_logs["item_code"].unique().tolist()
    items = supabase.table("items_master").select("item_code,uom").in_("item_code", item_codes).execute().data
    df_items = pd.DataFrame(items) if items else pd.DataFrame(columns=["item_code", "uom"])
    df = df_logs.merge(df_items, how="left", on="item_code")

    if "uom" not in df.columns:
        df["uom"] = "EA"
    else:
        df["uom"].fillna("EA", inplace=True)

    cols = [
        "id", "batch_id", "job_number", "lot_number",
        "item_code", "quantity", "uom", "description",
        "cost_code", "warehouse", "kitting_type", "kitted_on"
    ]
    return df[cols]

# ─────────────────────────────────────────────────────────────────────────────
# TXT Builder
# ─────────────────────────────────────────────────────────────────────────────
def build_txt(header: dict, df: pd.DataFrame) -> str:
    kit  = header["kit_date"].strftime("%m-%d-%y")
    acct = header["acct_date"].strftime("%m-%d-%y")
    buf = io.StringIO()
    buf.write(f"I,{header['batch']},{kit},{acct}\n")
    for r in df.itertuples():
        desc = (r.description or "").replace('"', "'")
        buf.write(
            f"IL,{r.warehouse},{r.item_code},{r.quantity},{r.uom},\"{desc}\",1,,,,"
            f"{r.job_number},{r.lot_number},{r.cost_code},M,,{kit}\n"
        )
    return buf.getvalue()

# ─────────────────────────────────────────────────────────────────────────────
# Main UI
# ─────────────────────────────────────────────────────────────────────────────
def run():
    _init_state()
    ss = st.session_state
    st.title("📤 Sage Export")

    if st.button("🔄 Reset tab"):
        for k in ["loaded_df", "edited_df", "grid_ready", "download_clicked"]:
            ss.pop(k, None)
        st.rerun()

    # Filters
    st.subheader("Filters")
    colA, colB, colC = st.columns(3)
    batch_filter = colA.text_input("Kitting Batch ID(s)", placeholder="comma-separated")
    export_batch_filter = colB.text_input("Export Batch ID(s)", placeholder="comma-separated")
    warehouses = colC.multiselect("Warehouse filter", distinct_values("warehouse", "kitting_logs"))

    colD, colE = st.columns(2)
    start_date = colD.date_input("Start date (≥)", value=None)
    end_date = colE.date_input("End date (<)", value=None)
    k_types = st.multiselect("Kitting Type filter", distinct_values("kitting_type", "kitting_logs"))

    if start_date:
        start_date = datetime.combine(start_date, datetime.min.time())
    if end_date:
        end_date = datetime.combine(end_date, datetime.min.time()) + pd.Timedelta(days=1)

    if st.button("🔍 Load logs"):
        try:
            batches = [b.strip() for b in batch_filter.split(",") if b.strip()] or None
            export_batches = [b.strip() for b in export_batch_filter.split(",") if b.strip()] or None

            df = fetch_kitting_logs(
                batch_ids=batches,
                warehouses=warehouses or None,
                k_types=k_types or None,
                start_date=start_date,
                end_date=end_date,
                export_batch_ids=export_batches,
            )
            if df.empty:
                st.warning("No records match those filters.")
            else:
                ss.loaded_df = df
                ss.edited_df = df.copy()
                ss.grid_ready = True
                st.rerun()
        except ValueError as e:
            st.error(str(e))

    # Assign export_batch_id
    if "username" not in st.session_state:
        st.warning("User session not found. Cannot assign export_batch_id.")
        st.stop()
    
    username = st.session_state["username"]
    export_batch_id = f"{username}_{random.randint(10000,99999)}"
    ss.export_batch_id = export_batch_id
    st.info(f"🧾 Export batch ID assigned: `{export_batch_id}`")

    # Grid
    if ss.get("grid_ready"):
        st.subheader("Review / edit")
        lock = {"id", "batch_id", "job_number", "lot_number", "item_code", "warehouse"}
        cfg = {c: {"disabled": True} for c in lock}
        ss.edited_df = st.data_editor(ss.edited_df, num_rows="dynamic", column_config=cfg, key="edit_grid")
        st.markdown("---")

    # Header + Export
    st.subheader("Generate Sage TXT")
    c1, c2, c3 = st.columns(3)
    batch_name = c1.text_input("Batch name (header)")
    kit_date = c2.date_input("Kit date", value=date.today())
    acct_date = c3.date_input("Accounting date", value=date.today())

    if st.button("🚀 Download TXT", disabled=ss.download_clicked):
        if ss.edited_df.empty:
            st.warning("Load data first.")
            st.stop()
        if not batch_name.strip():
            st.warning("Batch name is required.")
            st.stop()

        ss.download_clicked = True
        txt = build_txt({"batch": batch_name.strip(), "kit_date": kit_date, "acct_date": acct_date}, ss.edited_df)
        fname = re.sub(r"\W+", "_", batch_name.strip()) + ".txt"
        st.download_button("📥 Download file", txt, file_name=fname, mime="text/plain")

        # Writebacks
        export_time = datetime.now(timezone("US/Pacific")).isoformat()
        export_ids = ss.edited_df["id"].tolist()

        # ────────────────────────────────────────────────────────────────
        # Update pulltags
        # ────────────────────────────────────────────────────────────────
        matches = [
            {"job_number": r.job_number,
             "lot_number": r.lot_number,
             "item_code":  r.item_code}
            for r in ss.edited_df.itertuples()
        ]
        
        for match in matches:
            res = (supabase.table("pulltags")
                            .update({"status": "exported"})
                            .match(match)
                            .execute())
        
            if res.error:                        # works for every supabase-py version
                st.warning(f"⚠️ Pulltag update failed: {match} → {res.error}")
        
        # ────────────────────────────────────────────────────────────────
        # Update kitting_logs
        # ────────────────────────────────────────────────────────────────
        res = (supabase.table("kitting_logs")
                        .update({
                            "last_exported_on": export_time,
                            "export_batch_id": ss.export_batch_id
                        })
                        .in_("id", export_ids)
                        .execute())
        
        if res.error:
            st.error(f"❌ Failed to update kitting_logs → {res.error}")
            st.stop()


        st.success(f"TXT generated and exported as batch `{ss.export_batch_id}`.")
        st.balloons
        st.info("Re-export using Export Batch ID filter above.")
