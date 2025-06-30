import streamlit as st
import pandas as pd
import requests
import json
import io
import os
from supabase import create_client, Client

# ————— Environment / Supabase setup —————
SUPABASE_URL = os.environ.get("SUPABASE_URL") or st.secrets.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or st.secrets.get("SUPABASE_SERVICE_ROLE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
SUPABASE_EDGE_URL = "https://sxozcdzexeveaqxtgfit.functions.supabase.co/insert_communities"

def run():
    st.title("🏘️ Community Creation")
    user = st.session_state.get("user", {})
    st.markdown(f"Logged in as: `{user.get('username','Unknown')}` | Role: `{user.get('role','N/A')}`")
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
                            "Roof_Type":"roof_type",
                            "Cost_Code":"cost_code",
                            "Item_Code":"item_code",
                            "UOM":"uom",
                            "Item_Code_Qty":"item_code_qty",
                            "Job_Number":"job_number"
                        })
                        .fillna("")
                     )
                cols = ["job_number","roof_type","cost_code","item_code","uom","item_code_qty"]
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
                                    "Content-Type":"application/json",
                                    "Authorization":f"Bearer {SUPABASE_KEY}"
                                },
                                data=json.dumps({"records": df.to_dict("records")})
                            )
                            if resp.status_code==200:
                                res = resp.json()
                                st.success(f"✅ {res['inserted']} row(s) inserted/updated")
                                if res.get("errors"):
                                    err_df = pd.DataFrame([
                                        {**e["row"], "error_reason":e["error"]}
                                        for e in res["errors"]
                                    ])
                                    st.error("⚠️ Some rows failed:")
                                    st.dataframe(err_df, use_container_width=True)
                                    buf = io.StringIO()
                                    err_df.to_csv(buf, index=False)
                                    st.download_button("⬇️ Download Errors CSV", buf.getvalue(), "errors.csv", "text/csv")
                            else:
                                st.error(f"❌ Upload failed: {resp.status_code}")
                                st.code(resp.text)
            except Exception as e:
                st.error(f"⚠️ Could not read file: {e}")

    # ——— Tab 2: Edit Existing ———
    with tab2:
        st.subheader("✏️ Edit or Add Inline")
        q = st.text_input("Search job_number or roof_type")
        if st.button("🔍 Search"):
            query = supabase.table("communities").select("*").limit(500)
            if q:
                query = query.or_(f"job_number.ilike.*{q}*,roof_type.ilike.*{q}*")
            res = query.execute()
            if res.data:
                df = pd.DataFrame(res.data)
                # add one blank row for new entry
                df = pd.concat([df, pd.DataFrame([{
                    "job_number":"", "roof_type":"", "cost_code":"",
                    "item_code":"","uom":"","item_code_qty":""
                }])], ignore_index=True)
                edited = st.data_editor(
                    df,
                    use_container_width=True,
                    num_rows="dynamic",
                    key="editor"
                )
                with st.expander("⚠️ Review & Submit Changes"):
                    confirm = st.checkbox("I have reviewed all edits/new rows")
                    if confirm and st.button("💾 Save Changes"):
                        # validate & cast
                        updates, errors = [], []
                        for row in edited.to_dict("records"):
                            if not (row["job_number"] and row["roof_type"] and row["cost_code"]):
                                errors.append({"row":row, "error":"Missing required field"})
                                continue
                            try:
                                row["item_code_qty"] = float(row["item_code_qty"]) if row["item_code_qty"]!="" else None
                                updates.append(row)
                            except:
                                errors.append({"row":row, "error":"Qty must be numeric"})
                        # send to edge function
                        resp = requests.post(
                            SUPABASE_EDGE_URL,
                            headers={
                                "Content-Type":"application/json",
                                "Authorization":f"Bearer {SUPABASE_KEY}"
                            },
                            data=json.dumps({"records": updates})
                        )
                        if resp.status_code==200:
                            r=resp.json()
                            st.success(f"✅ {r['inserted']} row(s) processed")
                            if errors or r.get("errors"):
                                all_err = errors + r.get("errors",[])
                                err_df=pd.DataFrame([
                                    {**e["row"], "error_reason":e["error"]} for e in all_err
                                ])
                                st.error("⚠️ Issues detected")
                                st.dataframe(err_df, use_container_width=True)
                                buf=io.StringIO(); err_df.to_csv(buf,index=False)
                                st.download_button("⬇️ Download Errors CSV", buf.getvalue(), "errors.csv", "text/csv")
                        else:
                            st.error(f"❌ Submit failed: {resp.status_code}")
                            st.code(resp.text)
            else:
                st.info("No matching communities found.")

    # ——— Tab 3: Manually Create ———
    with tab3:
        st.subheader("🧾 Manually Build New Community")
        if "new_rows" not in st.session_state:
            st.session_state.new_rows = []
        with st.form("manual_form", clear_on_submit=True):
            job = st.text_input("Job Number")
            roof = st.text_input("Roof Type")
            cost = st.text_input("Cost Code")
            item = st.text_input("Item Code")
            uom = st.text_input("UOM")
            qty = st.text_input("Qty")
            add = st.form_submit_button("➕ Add Row")
            if add:
                # basic validation
                if not (job and roof and cost):
                    st.error("Job, Roof Type & Cost Code required.")
                else:
                    st.session_state.new_rows.append({
                        "job_number": job.upper(),
                        "roof_type": roof.upper(),
                        "cost_code": cost.upper(),
                        "item_code": item.upper() or None,
                        "uom": uom.upper() or None,
                        "item_code_qty": float(qty) if qty else None
                    })
                    st.success("Row added.")

        if st.session_state.new_rows:
            df_new = pd.DataFrame(st.session_state.new_rows)
            st.dataframe(df_new, use_container_width=True)
            with st.expander(f"⚠️ Submit {len(df_new)} new rows?"):
                confirm = st.checkbox("I have reviewed and wish to submit")
                if confirm and st.button("🚀 Submit All"):
                    resp = requests.post(
                        SUPABASE_EDGE_URL,
                        headers={
                            "Content-Type":"application/json",
                            "Authorization":f"Bearer {SUPABASE_KEY}"
                        },
                        data=json.dumps({"records": st.session_state.new_rows})
                    )
                    if resp.status_code==200:
                        r=resp.json()
                        st.success(f"✅ {r['inserted']} row(s) processed")
                        if r.get("errors"):
                            err_df = pd.DataFrame([
                                {**e["row"], "error_reason":e["error"]} for e in r["errors"]
                            ])
                            st.error("⚠️ Some rows failed:")
                            st.dataframe(err_df, use_container_width=True)
                            buf=io.StringIO(); err_df.to_csv(buf,index=False)
                            st.download_button("⬇️ Download Errors CSV", buf.getvalue(), "errors.csv", "text/csv")
                        # clear on success
                        st.session_state.new_rows = []
                    else:
                        st.error(f"❌ Submit failed: {resp.status_code}")
                        st.code(resp.text)

    # ——— Refresh ———
    if st.button("🔄 Refresh Page"):
        st.rerun()
