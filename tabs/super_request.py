import streamlit as st
import pandas as pd
from datetime import datetime
from supabase import create_client
import os
import uuid
from fpdf import FPDF
import tempfile
import json

def run():
    st.header('Super Request')
    user = st.session_state.get("username")
    supabase = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])  # anon key OK
    
    def get_statuses(pairs: list[dict[str, str]]) -> pd.DataFrame:
        supabase = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])
        try:
            # Invoke the edge function with the correct payload
            res = supabase.functions().invoke("pulltag-statuses", json.dumps(pairs))
            if res.get("error"):
                raise RuntimeError(res["error"])
            return pd.DataFrame(res["data"])  # columns: job_number | lot_number | status
        except Exception as e:
            raise RuntimeError(f"Failed to invoke edge function: {str(e)}")
            
    # --- PDF Generation Function ---
    def generate_pulltag_pdf(dataframe, filename="pulltag_request_summary.pdf"):
        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.add_page()
        pdf.set_font("Arial", size=12)
        pdf.cell(200, 10, txt="Pulltag Request Summary", ln=True, align='C')
        pdf.ln(5)

        for _, row in dataframe.iterrows():
            line = f"Job: {row['job_number']} | Lot: {row['lot_number']} | Item: {row['item_code']} | Qty: {row['quantity']} | Status: {row['status']}"
            pdf.multi_cell(0, 10, line)

        temp_path = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
        pdf.output(temp_path.name)
        return temp_path.name

    # --- Supabase Init ---
    SUPABASE_URL = os.environ["SUPABASE_URL"]
    SUPABASE_KEY = os.environ["SUPABASE_KEY"]

    # --- Language Setup ---
    if 'language' not in st.session_state:
        st.session_state.language = 'en'

    lang = st.session_state.language

    # --- Language Toggle ---
    toggle = "Cambiar a Español Mexicano" if lang == 'en' else "Switch to English"
    if st.button(toggle):
        st.session_state.language = 'es' if lang == 'en' else 'en'
        st.rerun()

    # --- Labels ---
    labels = {
        'en': {
            'title': "📦 Request Pulltags by Job & Lot",
            'instructions': "Enter multiple job and lot numbers below. Add rows as needed.",
            'submit': "Submit Requests",
            'processing': "Processing",
            'none_found': "❌ Not Found",
            'already_kitted': "✅ Already Kitted",
            'already_requested': "🕒 Already Requested",
            'submitted': "✅ Request Submitted",
            'invalid_status': "⚠️ Invalid Status",
            'duplicates_found': "🚫 Duplicate entries found. Please remove them before submitting.",
            'no_entries': "⚠️ No entries to submit!",
            'error': "❌ Error",
            'confirm_button': "✅ Confirm and submit valid requests",
            'submitted_success': "✅ Requests submitted!",
            'download_pdf': "📄 Download Request Summary PDF",
            'reprint_title': "### 🔁 Reprint a Previous Batch",
            'select_recent': "Select one of your recent batches",
            'find_expander': "🔍 Find Batch by Job + Lot",
            'job_label': "Job Number",
            'lot_label': "Lot Number",
            'found_batch': "✅ Found batch: {}",
            'no_batch_found': "❌ No batch found for this job-lot.",
            'manual_input': "Or enter a Batch ID manually",
            'no_pulltags': "❌ No pulltags found for that batch.",
            'download_reprint': "📄 Download Reprint PDF",
        },
        'es': {
            'title': "📦 Solicitar Pulltags por Trabajo y Lote",
            'instructions': "Ingresa múltiples números de trabajo y lote abajo. Agrega filas según sea necesario.",
            'submit': "Enviar Solicitudes",
            'processing': "Procesando",
            'none_found': "❌ No Encontrado",
            'already_kitted': "✅ Ya Kitted",
            'already_requested': "🕒 Ya Solicitado",
            'submitted': "✅ Solicitud Enviada",
            'invalid_status': "⚠️ Estado Inválido",
            'duplicates_found': "🚫 Hay duplicados. Elimínalos antes de continuar.",
            'no_entries': "⚠️ ¡No hay entradas para enviar!",
            'error': "❌ Error",
            'confirm_button': "✅ Confirmar y enviar solicitudes válidas",
            'submitted_success': "✅ Solicitudes enviadas!",
            'download_pdf': "📄 Descargar Resumen de Solicitud PDF",
            'reprint_title': "### 🔁 Reimprimir un Lote Anterior",
            'select_recent': "Selecciona uno de tus lotes recientes",
            'find_expander': "🔍 Buscar Lote por Trabajo + Lote",
            'job_label': "Número de Trabajo",
            'lot_label': "Número de Lote",
            'found_batch': "✅ Encontrado lote: {}",
            'no_batch_found': "❌ No se encontró lote para este trabajo-lote.",
            'manual_input': "O ingresa un ID de Lote manualmente",
            'no_pulltags': "❌ No se encontraron pulltags para ese lote.",
            'download_reprint': "📄 Descargar PDF de Reimpresión",
        }
    }[lang]

    # --- UI ---
    st.title(labels['title'])
    st.write(labels['instructions'])

    # --- Data Editor ---
    column_config = {
        "job_number": st.column_config.TextColumn(
            label=labels['job_label'],
            help="Enter the job number (e.g., JOB123 or 11100-029)" if lang == 'en' else "Ingresa el número de trabajo (ej. JOB123 o 11100-029)",
            required=True,
            validate="^[A-Za-z0-9\-]+$",
        ),
        "lot_number": st.column_config.NumberColumn(
            label=labels['lot_label'],
            help="Enter the lot number (numeric)" if lang == 'en' else "Ingresa el número de lote (numérico)",
            required=True,
            min_value=1,
            step=1,
        )
    }

    with st.form("super_request_form", clear_on_submit=False):
        job_entries = st.data_editor(
            pd.DataFrame(columns=["job_number", "lot_number"]),
            use_container_width=True,
            num_rows="dynamic",
            column_config=column_config,
            key="job_lot_input",
            hide_index=True,
        )

        submitted = st.form_submit_button(labels['submit'])

    # ─────────────────────────────────────────────
    # SUBMIT HANDLER  (Edge Function version)
    # ─────────────────────────────────────────────
    if submitted:
        raw = job_entries.copy()
    
        # 1) Remove fully blank rows
        pf = raw.dropna(how="all")
        if pf.empty:
            st.warning(labels['no_entries'])
            st.stop()
    
        # 2) Split valid / invalid
        valid_entries = pf.dropna().copy()
        invalid_rows  = pf.loc[~pf.index.isin(valid_entries.index)]
    
        # 3) Normalize keys
        def norm(x): return str(x).strip().replace(".0", "")
        for c in ("job_number", "lot_number"):
            valid_entries[c] = valid_entries[c].map(norm)
    
        # 4) Warn on invalids
        if not invalid_rows.empty:
            st.warning(f"⚠️ {len(invalid_rows)} row(s) have missing job or lot number.")
            st.dataframe(invalid_rows)
    
        # 5) Dedupe after normalization
        dup_mask = valid_entries.duplicated(["job_number", "lot_number"])
        if dup_mask.any():
            st.error(labels['duplicates_found'])
            st.dataframe(valid_entries[dup_mask])
            st.stop()
    
        # 6) Build payload for Edge Function
        pairs = valid_entries[["job_number", "lot_number"]].to_dict("records")
    
        results, to_update = [], []
        with st.spinner(f"{labels['processing']} {len(valid_entries)}..."):
            progress = st.progress(0)
            try:
                # ---- call edge function ----
                import json
                res = supabase.functions.invoke(
                    "pulltag-statuses",
                    body=json.dumps(pairs)
                )
                if res.error:
                    raise Exception(res.error)
    
                df_status = pd.DataFrame(res.data)  # job_number | lot_number | status
                progress.progress(0.5)
    
                # ---- OPTIONAL DEBUG ----
                if st.checkbox("🔧 debug rows", key="sr_debug"):
                    st.write("raw:", raw)
                    st.write("valid_entries:", valid_entries.dtypes, valid_entries)
                    st.write("df_status:", df_status.dtypes, df_status)
                    st.stop()
    
                # 7) Build result lists
                for _, r in df_status.iterrows():
                    job, lot, status = r["job_number"], r["lot_number"], r["status"]
    
                    if status is None:
                        results.append((job, lot, labels['none_found']))
                    elif status == "kitted":
                        results.append((job, lot, labels['already_kitted']))
                    elif status == "requested":
                        results.append((job, lot, labels['already_requested']))
                    elif status == "pending":
                        results.append((job, lot, labels['submitted']))
                        to_update.append({
                            "job_number": job,
                            "lot_number": lot,
                            "requested_by": st.session_state["username"]
                        })
                    else:
                        results.append((job, lot, labels['invalid_status']))
    
                progress.progress(1.0)
                st.session_state.results = results
                st.session_state.to_update = to_update
    
            except Exception as e:
                st.error(f"{labels['error']}: {e}")
                fail = [(j["job_number"], j["lot_number"], f"{labels['error']}: Failed to process")
                        for j in pairs]
                st.session_state.results = fail
                progress.progress(1.0)

    # -----------------------------
    st.divider()
    st.markdown(labels['reprint_title'])

    # 1️⃣ Dropdown of recent batches by user
    user = st.session_state["username"]
    recent_data = supabase.table("pulltags") \
        .select("batch_id") \
        .eq("requested_by", user) \
        .not_.is_("batch_id", "null") \
        .order("requested_on", desc=True) \
        .limit(25).execute()

    recent_batch_ids = list(dict.fromkeys(row["batch_id"] for row in recent_data.data if row["batch_id"]))

    selected_batch = st.selectbox(labels['select_recent'], recent_batch_ids, index=0 if recent_batch_ids else None)

    # 2️⃣ Lookup batch by job-lot
    with st.expander(labels['find_expander']):
        job_lookup = st.text_input(labels['job_label'], key="lookup_job")
        lot_lookup = st.text_input(labels['lot_label'], key="lookup_lot")

        input_batch_id = None
        if job_lookup and lot_lookup:
            lookup_res = supabase.table("pulltags") \
                .select("batch_id") \
                .eq("job_number", job_lookup) \
                .eq("lot_number", lot_lookup) \
                .not_.is_("batch_id", "null").execute()
            found_batches = list(dict.fromkeys(r["batch_id"] for r in lookup_res.data if r["batch_id"]))
            if found_batches:
                input_batch_id = found_batches[0]
                st.success(labels['found_batch'].format(input_batch_id))
            else:
                st.error(labels['no_batch_found'])

    # 3️⃣ Manual entry fallback
    manual_batch_id = st.text_input(labels['manual_input'])

    # Choose which batch_id to use
    final_batch_id = input_batch_id or manual_batch_id or selected_batch

    # 🔄 Reprint if batch_id resolved
    if final_batch_id:
        batch_data = supabase.table("pulltags") \
            .select("job_number, lot_number, item_code, quantity, status") \
            .eq("batch_id", final_batch_id).execute()

        if batch_data.data:
            df_batch = pd.DataFrame(batch_data.data)
            reprint_path = generate_pulltag_pdf(df_batch, filename=f"{final_batch_id}.pdf")
            st.download_button(labels['download_reprint'], open(reprint_path, "rb"), file_name=f"{final_batch_id}.pdf")
        else:
            st.error(labels['no_pulltags'])
