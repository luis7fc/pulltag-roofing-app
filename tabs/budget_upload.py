import streamlit as st
import pandas as pd
import uuid
import math
from datetime import datetime
from supabase import create_client
import os
import pdfplumber
import re


# --- Supabase connection ---
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

#Budget Parser
def parse_pdf_budget_all_lots(pdf_path: str) -> pd.DataFrame:
    records = []
    job_number = None
    community = None
    current_lot = None
    last_known_lot = None

    lot_header_pattern = re.compile(r"^(\d{4})\s+[\d\s\w]+?\(\w+\)")
    flex_item_pattern = re.compile(
        r"^\s*([A-Za-z0-9\(\)\+\"'#\/\-]{2,})\s+(.+?)\s+([\d.]+)\s+(EA|SQ|BNDL|ROLL|PC|BUND|BOX)\s*$"
    )

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            lines = page.extract_text().splitlines()
            if not lines:
                print(f"[DEBUG] No text found on page {page.page_number}")

            for idx, line in enumerate(lines):
                if re.match(r"^\d{5}-\d{3}\s", line.strip()):
                    job_number = re.match(r"^(\d{5}-\d{3})", line.strip()).group(1)
                    community = line.strip().split(job_number)[-1].strip()

                lot_match = lot_header_pattern.match(line)
                if lot_match:
                    current_lot = lot_match.group(1)
                    last_known_lot = current_lot

                if line.strip().startswith("L"):
                    continue

                match = flex_item_pattern.match(line)
                if match and last_known_lot:
                    code, desc, qty, uom = match.groups()
                    records.append({
                        "Community": community,
                        "Job Number": job_number,
                        "Lot Number": last_known_lot,
                        "Cost Code": code.strip().upper(),
                        "Description": desc.strip(),
                        "Units Budget": float(qty),
                        "UOM": uom
                    })
                    
                    print(f"[DEBUG] Parsed: job={job_number}, lot={last_known_lot}, code={code}, desc={desc}, qty={qty}, uom={uom}")


    return pd.DataFrame(records)



# Load mock or production data
@st.cache_data
def load_communities():
    try:
        res = supabase.table("communities").select("*").execute()
        if res.data:
            return pd.DataFrame(res.data)
        else:
            st.warning("Communities table is empty.")
            return pd.DataFrame()
    except Exception as e:
        st.error(f"Failed to load communities: {e}")
        return pd.DataFrame()


@st.cache_data
def load_items_master():
    res = supabase.table("items_master").select("item_code, description, uom").execute()
    return pd.DataFrame(res.data)

@st.cache_data
def load_roof_type():
    res = supabase.table("roof_type").select("roof_type, cost_code").execute()
    return pd.DataFrame(res.data)

# Quantity logic parser
def compute_quantity(units_budget, logic):
    try:
        if isinstance(logic, str) and 'Units Budget' in logic:
            if '*' in logic:
                factor = float(logic.split('*')[-1].strip())
                return math.ceil(units_budget * factor)
            elif '/' in logic:
                divisor = float(logic.split('/')[-1].strip())
                return math.ceil(units_budget / divisor)
            else:
                return math.ceil(units_budget)
        else:
            # Try to cast any other numeric value (int or float)
            return float(logic)
    except:
        return None


def run():
    st.title("📄 Budget Upload")

    username = st.session_state.get("username", "unknown_user")
    pdf_file = st.file_uploader("Upload Budget PDF", type="pdf")

    if pdf_file:
        with st.spinner("Parsing and processing..."):
            df_budget = parse_pdf_budget_all_lots(pdf_file)
            st.write("✅ Parsed PDF preview:")
            st.dataframe(df_budget.head(50))
            st.write("Columns:", df_budget.columns.tolist())

            communities_df = load_communities()
            items_master_df = load_items_master()
            roof_type_df = load_roof_type()

            results = []
            grouped = df_budget.groupby(['Job Number', 'Lot Number'])
            for (job_number, lot_number), lot_df in grouped:
                extracted_cost_codes = set(lot_df['Cost Code'].str.upper())

                #here!
                matched_roof_type = None
                for rt in roof_type_df['roof_type'].unique():
                    roof_codes = set(roof_type_df[roof_type_df['roof_type'] == rt]['cost_code'].str.upper())
                    if extracted_cost_codes & roof_codes:  # <-- matches at least one
                        matched_roof_type = rt
                        break
                        
                if not matched_roof_type:
                    st.warning(f"No roof type match for Job {job_number}, Lot {lot_number}")
                    continue

                job_prefix = job_number[:5]
                for _, budget_row in lot_df.iterrows():
                    budget_cost_code = budget_row['Cost Code'].upper()
                    units_budget = budget_row['Units Budget']

                    community_rows = communities_df[
                        (communities_df['job_number'].str.startswith(job_prefix)) &
                        (communities_df['roof_type'] == matched_roof_type) &
                        (communities_df['cost_code'].str.upper() == budget_cost_code)
                    ]

                    for _, comm_row in community_rows.iterrows():
                        item_code = comm_row['item_code']
                        logic = comm_row['item_code_qty']
                        qty = compute_quantity(units_budget, logic)
                        if qty is None:
                            continue

                        desc_row = items_master_df[items_master_df['item_code'] == item_code]
                        if desc_row.empty:
                            continue
                        desc_row = desc_row.iloc[0]

                        results.append({
                            'uid': str(uuid.uuid4()),
                            'job_number': job_number,
                            'lot_number': lot_number,
                            'roof_type': matched_roof_type,
                            'item_code': item_code,
                            'cost_code': budget_cost_code,
                            'description': desc_row['description'],
                            'quantity': qty,
                            'kitted_qty': 0,
                            'shorted': None,
                            'backorder_qty': 0,
                            'backorder_status': 'none',
                            'status': 'pending',
                            'uploaded_on': datetime.now().isoformat(),
                            'requested_on': None,
                            'kitted_on': None,
                            'resolved_on': None,
                            'exported_on': None,
                            'warehouse': None,
                            'uom': desc_row['uom'],
                            'batch_id': None,
                            'updated_by': username,
                            'requested_by': None
                        })


            pulltags_df = pd.DataFrame(results)
            if pulltags_df.empty:
                st.warning("No pulltags generated. Please check input PDF and community config")
            else:
                st.success(f"✅ Generated {len(pulltags_df)} pulltag rows.")
                st.dataframe(pulltags_df)
                st.download_button("Download CSV", pulltags_df.to_csv(index=False), file_name="pulltags_generated.csv")

                if st.button("📤 Submit to Supabase"):
                    try:
                        insert_data = pulltags_df.to_dict(orient='records')
                        res = supabase.table("pulltags").insert(insert_data).execute()
                        if res.data:
                            st.success(f"✅ Successfully inserted {len(res.data)} rows to Supabase.")
                        else:
                            st.error("❌ Insertion failed or returned no data.")
                    except Exception as e:
                        st.error(f"🚫 Supabase insert failed: {e}")
