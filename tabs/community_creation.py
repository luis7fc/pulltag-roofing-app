import streamlit as st
import pandas as pd
import requests
import json
import io
import os
from supabase import create_client, Client
from field_tracker import tracked_input

# ————— Environment / Supabase setup —————
SUPABASE_URL      = os.environ.get("SUPABASE_URL") or st.secrets.get("SUPABASE_URL")
SUPABASE_KEY      = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or st.secrets.get("SUPABASE_SERVICE_ROLE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
SUPABASE_EDGE_URL = "https://sxozcdzexeveaqxtgfit.functions.supabase.co/insert_communities"

def run():
    st.title("🏘️ Community Creation")
    user     = st.session_state.get("user", {})
    username = user.get("username", "Unknown")

    st.markdown(f"Logged in as: `{username}` | Role: `{user.get('role','N/A')}`")
    st.divider()

    tab1, tab2, tab3 = st.tabs([
        "📤 Upload CSV",
        "✏️ Edit Existing",
        "🧾 Manually Create"
    ])

    # ——— Tab 1: Upload CSV ———
    with tab1:
        st.info("Upload a CSV with headers: `Roof_Type, Cost_Code, Item_Code, UOM, Item_Code_Qty, Job_Number`")
        f = st.file_uploader("", type="csv")
        if f:
            try:
                df = (pd.read_csv(f)
                        .rename(columns={
                            "Roof_Type":    "roof_type",
                            "Cost_Code":    "cost_code",
                            "Item_Code":    "item_code",
                            "UOM":          "uom",
                            "Item_Code_Qty":"item_code_qty",
                            "Job_Number":   "job_number"
                        })
                        .fillna("")
                     )
                cols    = ["job_number","roof_type","cost_code","item_code","uom","item_code_qty"]
                missing = set(cols) - set(df.columns)
                if missing:
                    st.error(f"❌ Missing columns: {missing}")
                else:
                    df = df[cols]
                    st.dataframe(df, use_container_width=True)

                    with st.expander(f"⚠️ Submit {len(df)} rows?"):
                        confirm = st.checkbox("I have reviewed the data and wish to proceed")
                        if confirm and st.button("🚀 Submit CSV"):
                            resp = requests.post(
                                SUPABASE_EDGE_URL,
                                headers={
                                    "Content-Type": "application/json",
                                    "Authorization": f"Bearer {SUPABASE_KEY}"
                                },
                                data=json.dumps({"records": df.to_dict("records")})
                            )
                            if resp.status_code == 200:
                                res = resp.json()
                                st.success(f"✅ {res['inserted']} row(s) inserted/updated")
                                if res.get("errors"):
                                    err_df = pd.DataFrame([
                                        {**e["row"], "error_reason": e["error"]}
                                        for e in res["errors"]
                                    ])
                                    st.error("⚠️ Some rows failed:")
                                    st.dataframe(err_df, use_container_width=True)
                                    buf = io.StringIO()
                                    err_df.to_csv(buf, index=False)
                                    st.download_button(
                                        "⬇️ Download Errors CSV",
                                        buf.getvalue(),
                                        "community_upload_errors.csv",
                                        "text/csv"
                                    )
                            else:
                                st.error(f"❌ Upload failed: {resp.status_code}")
                                st.code(resp.text)
            except Exception as e:
                st.error(f"⚠️ Could not read file: {e}")
                
    # ——— Tab 2: Edit Existing ———
    with tab2:
        st.subheader("✏️ Edit or Add Inline")
    
        # 1️⃣ Persist the search query itself
        q = tracked_input(
            "Search job_number or roof_type",
            key="search_query",
            username=username,
            tab="community_creation",
            supabase=supabase,
        )
    
        # 2️⃣ Fetch from Supabase only when user clicks Search
        if st.button("🔍 Search", key="search_btn"):
            query = supabase.table("communities").select("*").limit(500)
            if q:
                query = query.or_(f"job_number.ilike.*{q}*,roof_type.ilike.*{q}*")
            res = query.execute()
    
            if res.data:                                   # found rows
                df = pd.DataFrame(res.data)
                # add one blank row so users can insert a brand‑new record
                df = pd.concat(
                    [
                        df,
                        pd.DataFrame(
                            [
                                dict(
                                    job_number="",
                                    roof_type="",
                                    cost_code="",
                                    item_code="",
                                    uom="",
                                    item_code_qty="",
                                )
                            ]
                        ),
                    ],
                    ignore_index=True,
                )
                st.session_state["comm_df"] = df           # 🔒 cache it
            else:
                st.warning("No matching communities found.")
                st.session_state.pop("comm_df", None)      # clear stale cache
    
        # 3️⃣ Show the editor only if we have something cached
        if "comm_df" in st.session_state:
            with st.form("editor_form", clear_on_submit=False):
                edited = st.data_editor(
                    st.session_state["comm_df"],
                    use_container_width=True,
                    num_rows="dynamic",
                    key="editor",
                )
    
                submitted = st.form_submit_button("💾 Save Changes")
                if submitted:
                    updates, errors = [], []
                    for row in edited.to_dict("records"):
                        # required fields
                        if not (row["job_number"] and row["roof_type"] and row["cost_code"]):
                            errors.append({"row": row, "error": "Missing required field"})
                            continue
                        updates.append(row)
    
                    if updates:
                        resp = requests.post(
                            SUPABASE_EDGE_URL,
                            headers={
                                "Content-Type": "application/json",
                                "Authorization": f"Bearer {SUPABASE_KEY}",
                            },
                            data=json.dumps({"records": updates}),
                        )
                        if resp.status_code == 200:
                            r = resp.json()
                            st.success(f"✅ {r['inserted']} row(s) processed")
                            errors.extend(r.get("errors", []))
                        else:
                            st.error(f"❌ Submit failed: {resp.status_code}")
                            st.code(resp.text)
    
                    # show any client‑side or server‑side issues
                    if errors:
                        err_df = pd.DataFrame(
                            [{**e["row"], "error_reason": e["error"]} for e in errors]
                        )
                        st.error("⚠️ Issues detected while saving:")
                        st.dataframe(err_df, use_container_width=True)
    
                    # always keep latest edits in cache so grid never disappears
                    st.session_state["comm_df"] = edited

    # ——— Tab 3: Manually Create ———
    with tab3:
        st.subheader("🧾 Manually Build New Community")

        job  = tracked_input("Job Number",    "manual_job",  username, "community_creation", supabase)
        roof = tracked_input("Roof Type",     "manual_roof", username, "community_creation", supabase)
        cost = tracked_input("Cost Code",     "manual_cost", username, "community_creation", supabase)
        item = tracked_input("Item Code",     "manual_item", username, "community_creation", supabase)
        uom  = tracked_input("UOM",           "manual_uom",  username, "community_creation", supabase)
        qty  = tracked_input("Qty",           "manual_qty",  username, "community_creation", supabase)

        if st.button("➕ Add Row"):
            if not (job and roof and cost):
                st.error("Job, Roof Type & Cost Code required.")
            else:
                row = {
                    "job_number":    job.upper(),
                    "roof_type":     roof.upper(),
                    "cost_code":     cost.upper(),
                    "item_code":     item.upper() or None,
                    "uom":           uom.upper() or None,
                    "item_code_qty": qty or None
                }
                st.session_state.setdefault("new_rows", []).append(row)
                st.success("Row added.")

        new_rows = st.session_state.get("new_rows", [])
        if new_rows:
            df_new = pd.DataFrame(new_rows)
            st.dataframe(df_new, use_container_width=True)

            with st.expander(f"⚠️ Submit {len(df_new)} new rows?"):
                confirm3 = st.checkbox("I have reviewed and wish to submit")
                if confirm3 and st.button("🚀 Submit All"):
                    resp = requests.post(
                        SUPABASE_EDGE_URL,
                        headers={
                            "Content-Type": "application/json",
                            "Authorization": f"Bearer {SUPABASE_KEY}"
                        },
                        data=json.dumps({"records": new_rows})
                    )
                    if resp.status_code == 200:
                        r = resp.json()
                        st.success(f"✅ {r['inserted']} row(s) processed")
                        if r.get("errors"):
                            err_df = pd.DataFrame([
                                {**e["row"], "error_reason": e["error"]}
                                for e in r["errors"]
                            ])
                            st.error("⚠️ Some rows failed:")
                            st.dataframe(err_df, use_container_width=True)
                            buf = io.StringIO()
                            err_df.to_csv(buf, index=False)
                            st.download_button(
                                "⬇️ Download Errors CSV",
                                buf.getvalue(),
                                "community_manual_errors.csv",
                                "text/csv"
                            )
                        st.session_state.new_rows = []
                    else:
                        st.error(f"❌ Submit failed: {resp.status_code}")
                        st.code(resp.text)

    # ——— Refresh ———
    if st.button("🔄 Refresh Page"):
        st.rerun()
