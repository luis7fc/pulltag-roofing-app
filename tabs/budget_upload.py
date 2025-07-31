import streamlit as st
import pandas as pd
import uuid, math, os, re, pdfplumber
from datetime import datetime
from supabase import create_client

# ──────────────────────────────────────────────────────────────────────────
# Supabase connection
# ──────────────────────────────────────────────────────────────────────────
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# ──────────────────────────────────────────────────────────────────────────
# Helper: fraction-friendly quantity logic
# ──────────────────────────────────────────────────────────────────────────
NO_ROUND_ITEMS = {"NC134", "NC34"}

def compute_quantity(units_budget: float, logic, item_code: str | None = None):
    """Return qty, keeping fractions for NO_ROUND_ITEMS, ceilling for others."""
    try:
        if isinstance(logic, str) and "Units Budget" in logic:
            if "*" in logic:
                factor = float(logic.split("*")[-1].strip())
                raw_qty = units_budget * factor
            elif "/" in logic:
                divisor = float(logic.split("/")[-1].strip())
                raw_qty = units_budget / divisor
            else:
                raw_qty = units_budget
        else:
            raw_qty = float(logic)

        if item_code and item_code.upper() in NO_ROUND_ITEMS:
            return round(raw_qty, 2)
        return float(math.ceil(raw_qty))
    except Exception:
        return None

# ──────────────────────────────────────────────────────────────────────────
# PDF budget parser  (unchanged except for lot-regex upgrade)
# ──────────────────────────────────────────────────────────────────────────
LOT_RE = re.compile(r"""^\s*(?P<lot>\d{1,4}[A-Z]?)\s+\d+\s+.+?\(\w+\)""", re.VERBOSE)
ITEM_RE = re.compile(
    r"""^\s*([A-Za-z0-9()+\"'#/\-]{2,})\s+(.+?)\s+([\d.]+)\s+"""
    r"""(EA|SQ|LF|ROLL|BNDL|BUND|PC|BOX)(?:\s+.+)?$"""
)

def parse_pdf_budget_all_lots(pdf_path) -> pd.DataFrame:
    rows, job_number, community, last_lot = [], None, None, None
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text:
                continue
            for line in text.splitlines():
                if re.match(r"^\d{5}-\d{3}\s", line.strip()):
                    job_number = re.match(r"^(\d{5}-\d{3})", line.strip()).group(1)
                    community = line.strip().split(job_number)[-1].strip()
                lot_match = LOT_RE.match(line)
                if lot_match:
                    last_lot = lot_match.group("lot")
                if line.strip().startswith("L"):
                    continue
                m = ITEM_RE.match(line)
                if m and last_lot:
                    code, desc, qty, uom = m.groups()
                    rows.append(
                        dict(
                            Community=community,
                            Job_Number=job_number,
                            Lot_Number=last_lot,
                            Cost_Code=code.strip().upper(),
                            Description=desc.strip(),
                            Units_Budget=float(qty),
                            UOM=uom,
                        )
                    )
    return pd.DataFrame(rows)

# ──────────────────────────────────────────────────────────────────────────
# Cached lookups  (5-min TTL + manual refresh)
# ─────────────────────────────────────────────────────────────────────────
@st.cache_data(ttl=300, show_spinner=False)
def load_communities():
    return pd.DataFrame(supabase.table("communities").select("*").execute().data)

@st.cache_data(ttl=300, show_spinner=False)
def load_items_master():
    return pd.DataFrame(
        supabase.table("items_master").select("item_code, description, uom").execute().data
    )

@st.cache_data(ttl=300, show_spinner=False)
def load_roof_type():
    return pd.DataFrame(
        supabase.table("roof_type").select("roof_type, cost_code").execute().data
    )

# ──────────────────────────────────────────────────────────────────────────
# Main Streamlit page
# ──────────────────────────────────────────────────────────────────────────
def run():
    st.title("📄 Budget Upload")
 
    # Manual cache-bust
    if st.button("🔄 Refresh communities cache"):
        load_communities.clear(); st.rerun()

    username = st.session_state.get("username", "unknown_user")
    pdf_file = st.file_uploader("Upload Budget PDF", type="pdf")

    if not pdf_file:
        return

    with st.spinner("Parsing and processing…"):
        # Step-1 ─ Parser output
        df_budget = parse_pdf_budget_all_lots(pdf_file)
        df_budget.columns = [col.strip().replace(" ", "_").lower() for col in df_budget.columns]
        st.write("🟢 **Step-1 Parsed NPC rows** →", 
                 df_budget[df_budget["cost_code"] == "NPC"])
        # ─── FINAL DEBUG 🔍
        raw = supabase.table("communities").select("*").eq("item_code", "NPC").execute()
        
        st.write("🧨 RAW Supabase NPC rows (no cache):", raw.data)
        if raw.error:
            st.error(f"🧨 Supabase Error: {raw.error}")
        elif not raw.data:
            st.warning("🧨 Supabase returned no data for item_code = 'NPC'")
        else:
            st.success(f"🧨 Supabase returned {len(raw.data)} NPC rows.")

        # Load reference tables (fresh)
        load_communities.clear();  # ensure new SQL is seen immediately
        communities_df   = load_communities()
        items_master_df  = load_items_master()
        roof_type_df     = load_roof_type()
        # 🔧 Normalize string columns to prevent pandas matching bugs
        communities_df["job_number"]  = communities_df["job_number"].astype(str).str.strip()
        communities_df["roof_type"]   = communities_df["roof_type"].astype(str).str.strip()
        communities_df["cost_code"]   = communities_df["cost_code"].astype(str).str.strip().str.upper()
        communities_df["item_code"]   = communities_df["item_code"].astype(str).str.strip()

        st.write("🟢 **Step-2 Community NPC rows** →", 
                 communities_df[communities_df["item_code"].str.strip() == "NPC"]
                 [["job_number","roof_type","cost_code","item_code_qty"]])

        results = []
        grouped = df_budget.groupby(["job_number", "lot_number"])

        for (job_number, lot_number), lot_df in grouped:
            extracted_codes  = set(lot_df["cost_code"].str.upper())
            matched_roof     = None
            for rt in roof_type_df["roof_type"].unique():
                if extracted_codes & set(
                    roof_type_df[roof_type_df["roof_type"] == rt]["cost_code"].str.upper()
                ):
                    matched_roof = rt; break
            if not matched_roof:
                continue

            st.write(f"📄 **Lot {lot_number} / Job {job_number} roof={matched_roof}**")

            job_prefix = job_number[:5]
            for _, budget_row in lot_df.iterrows():
                budget_code   = budget_row["cost_code"].upper()
                units_budget  = budget_row["units_budget"]
                job_prefix     = str(job_number)[:5]
                matched_roof   = str(matched_roof).strip()
                budget_code    = str(budget_code).strip().upper()
                
                if budget_code == "NPC":
                    debug_rows = communities_df[
                        communities_df["item_code"] == "NPC"
                    ]
                
                    st.write("🧪 NPC filter debug", {
                        "job_prefix": job_prefix,
                        "matched_roof": matched_roof,
                        "budget_code": budget_code,
                    })
                
                    test_filtered = debug_rows[
                        debug_rows["job_number"].str.startswith(job_prefix) &
                        (debug_rows["roof_type"] == matched_roof) &
                        (debug_rows["cost_code"] == budget_code)
                    ]
                
                    st.write("🧪 NPC test_filtered rows:", test_filtered)

                community_rows = communities_df[
                    (communities_df["job_number"].str.startswith(job_prefix)) &
                    (communities_df["roof_type"] == matched_roof) &
                    (communities_df["cost_code"].str.strip().str.upper() == budget_code)
                ]

                # Step-3
                if budget_code == "NPC":
                    st.write("🟡 **Step-3 community_rows len** →", len(community_rows))

                for _, comm_row in community_rows.iterrows():
                    item_code = comm_row["item_code"].strip()
                    logic     = comm_row["item_code_qty"]
                    qty       = compute_quantity(units_budget, logic, item_code)

                    # Step-4
                    if item_code == "NPC":
                        st.write("🟡 **Step-4 qty debug** →", {"logic": logic, "qty": qty})

                    if qty is None:
                        continue

                    desc_row = items_master_df[
                        items_master_df["item_code"].str.strip() == item_code
                    ]
                    # Step-5
                    if item_code == "NPC":
                        st.write("🟡 **Step-5 desc_row empty?**", desc_row.empty)

                    if desc_row.empty:
                        continue
                    desc_row = desc_row.iloc[0]

                    # Step-6  (will append)
                    if item_code == "NPC":
                        st.write("🟢 **Step-6 append row**", 
                                 {"item_code": item_code, "qty": qty})

                    results.append(
                        dict(
                            uid=str(uuid.uuid4()),
                            job_number=job_number,
                            lot_number=lot_number,
                            roof_type=matched_roof,
                            item_code=item_code,
                            cost_code=budget_code,
                            description=desc_row["description"],
                            quantity=qty,
                            kitted_qty=0,
                            shorted=0,
                            backorder_qty=0,
                            backorder_status="none",
                            status="pending",
                            uploaded_on=datetime.utcnow().isoformat(),
                            requested_on=None,
                            kitted_on=None,
                            resolved_on=None,
                            exported_on=None,
                            warehouse=None,
                            uom=desc_row["uom"],
                            batch_id=None,
                            updated_by=username,
                            requested_by=None,
                        )
                    )

        # ------------------ preview & submit ------------------
        pulltags_df = pd.DataFrame(results)
        if pulltags_df.empty:
            st.error("🚫 No pulltags generated.")
            return

        st.success(f"✅ Generated {len(pulltags_df)} rows.")
        st.dataframe(pulltags_df)
        st.download_button("Download CSV",
                           pulltags_df.to_csv(index=False),
                           "pulltags_generated.csv")

        if st.button("📤 Submit to Supabase"):
            try:
                res = supabase.table("pulltags").insert(pulltags_df.to_dict("records")).execute()
                st.success(f"Inserted {len(res.data or [])} rows.")
            except Exception as e:
                st.error(f"Supabase insert failed: {e}")

