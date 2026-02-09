import streamlit as st
from google import genai
from google.genai import types
from PIL import Image
import pandas as pd
import io
import json
import zipfile
import uuid
import time
import re

# --- KONFIGURACJA STRONY ---
st.set_page_config(page_title="Global Finance OS | SaaS Edition", layout="wide")

# --- SŁOWNIK TŁUMACZEŃ ---
TRANSLATIONS = {
    "PL": {
        "title": "📊 Global Finance OS",
        "subtitle": "System SaaS: Autonomiczna Analiza i Ochrona Przed Duplikatami",
        "sidebar_header": "Panel Sterowania",
        "lang_label": "🗣️ Język interfejsu:",
        "region_label": "🌍 Region (Format liczb):",
        "region_pl": "Polska (Przecinki ,)",
        "region_us": "International (Kropki .)",
        "clear_btn": "🗑️ Resetuj System",
        "upload_label": "Wgraj dokumenty (PDF, JPG, PNG)",
        "analyze_btn": "🚀 Przetwórz pliki",
        "table_header": "📝 Rejestr Finansowy",
        "summary_header": "💡 Executive Insights",
        "total_gross": "Suma Brutto",
        "total_tax": "Podatek (VAT/GST)",
        "ai_btn": "🧠 Strategiczna Analiza AI",
        "download_btn": "📦 Pobierz Paczkę (.ZIP)",
        "categories": "TOWAR, MEDIA, PALIWO, USŁUGI, INNE",
        "empty_msg": "System gotowy. Wgraj faktury."
    },
    "EN": {
        "title": "📊 Global Finance OS",
        "subtitle": "SaaS Engine: Autonomous Audit & Duplicate Prevention",
        "sidebar_header": "Control Panel",
        "lang_label": "🗣️ Language:",
        "region_label": "🌍 Region (Number Format):",
        "region_pl": "Europe (Commas ,)",
        "region_us": "USA / Global (Dots .)",
        "clear_btn": "🗑️ Factory Reset",
        "upload_label": "Upload Documents (Invoices, Receipts)",
        "analyze_btn": "🚀 Process Documents",
        "table_header": "📝 Financial Ledger",
        "summary_header": "💡 Executive Insights",
        "total_gross": "Gross Spend",
        "total_tax": "Total Tax",
        "ai_btn": "🧠 Generate AI Insights",
        "download_btn": "📦 Download Package (.ZIP)",
        "categories": "COGS, OPEX, CAPEX, SERVICES, OTHER",
        "empty_msg": "System Ready. Please upload documents."
    }
}

# --- ROBUST UTILITIES ---
def robust_json_parser(text):
    """
    Wyłuskuje czysty JSON z tekstu, ignorując wszystko co przed i po klamrach.
    Rozwiązuje błąd 'Extra data'.
    """
    try:
        start = text.find('{')
        end = text.rfind('}')
        if start != -1 and end != -1:
            return text[start:end+1]
    except Exception:
        pass
    return text

def normalize_entity_name(name):
    if not name: return "UNKNOWN_ENTITY"
    n = str(name).upper()
    trash = [r'\bSP\. Z O\.O\b', r'\bSPÓŁKA Z O\.O\b', r'\bS\.A\b', r'\bINC\b', r'\bLTD\b', r'\bLLC\b']
    for t in trash: n = re.sub(t, '', n)
    return re.sub(r'[^\w\s]', '', n).strip()

# --- INITIALIZATION ---
REQUIRED_COLS = ["id", "date", "vendor", "category", "currency", "net_amount", "tax_amount", "gross_amount", "type"]
if 'vault' not in st.session_state:
    st.session_state['vault'] = pd.DataFrame(columns=REQUIRED_COLS)
if 'storage' not in st.session_state:
    st.session_state['storage'] = {}

# --- SIDEBAR ---
with st.sidebar:
    selected_lang = st.radio("Language", ["PL", "EN"], horizontal=True)
    t = TRANSLATIONS[selected_lang]
    st.header(t["sidebar_header"])
    
    region_choice = st.radio(t["region_label"], [t["region_pl"], t["region_us"]], index=0)
    is_pl_format = (region_choice == t["region_pl"])
    
    if st.button(t["clear_btn"]):
        st.session_state['vault'] = pd.DataFrame(columns=REQUIRED_COLS)
        st.session_state['storage'] = {}
        st.rerun()

    api_key = st.secrets.get("api_key", "")
    if not api_key:
        api_key = st.text_input("Gemini API Key", type="password")

# --- UI ---
st.title(t["title"])
st.markdown(f"*{t['subtitle']}*")

files = st.file_uploader(t["upload_label"], type=["jpg", "jpeg", "png", "pdf"], accept_multiple_files=True)

if files and api_key:
    client = genai.Client(api_key=api_key)
    if st.button(f"{t['analyze_btn']} ({len(files)})"):
        pb = st.progress(0)
        for i, f in enumerate(files):
            pb.progress((i + 1) / len(files))
            try:
                prompt = f"""
                Act as a Financial Auditor. Extract data from the document into JSON.
                Use ONLY these categories: {t['categories']}.
                Format: {{"date":"YYYY-MM-DD", "vendor":"Name", "category":"...", "currency":"Code", "net_amount":0.0, "tax_amount":0.0, "gross_amount":0.0, "type":"Invoice"}}
                Return ONLY the JSON object. No commentary.
                """
                
                # Konwersja do Part (wymagane w nowym SDK)
                file_part = types.Part.from_bytes(data=f.getvalue(), mime_type=f.type)
                
                response = client.models.generate_content(
                    model='gemini-2.0-flash',
                    contents=[prompt, file_part]
                )

                # Naprawa błędu 'Extra data'
                cleaned_json = robust_json_parser(response.text)
                data = json.loads(cleaned_json)
                
                if isinstance(data, list): data = data[0]
                data['vendor'] = normalize_entity_name(data.get('vendor'))
                f_id = str(uuid.uuid4())
                st.session_state['storage'][f_id] = {"data": f.getvalue(), "name": f.name}
                data['id'] = f_id
                
                # Bezpieczny concat
                new_row = pd.DataFrame([data])
                for col in REQUIRED_COLS:
                    if col not in new_row.columns: new_row[col] = "N/A"
                st.session_state['vault'] = pd.concat([st.session_state['vault'], new_row], ignore_index=True)
                
                time.sleep(0.4)
            except Exception as e:
                st.error(f"Error {f.name}: {e}")
        st.rerun()

# --- ANALITYKA ---
if not st.session_state['vault'].empty:
    df = st.session_state['vault']
    for c in ["net_amount", "tax_amount", "gross_amount"]:
        df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0).round(2)

    st.divider()
    c1, c2, c3, c4 = st.columns(4)
    main_curr = df['currency'].mode()[0] if not df['currency'].empty else "PLN"
    
    total_gross = df["gross_amount"].sum()
    total_tax = df["tax_amount"].sum()
    
    c1.metric(t["total_gross"], f"{total_gross:,.2f} {main_curr}")
    c2.metric(t["total_tax"], f"{total_tax:,.2f} {main_curr}")
    c3.metric("Entities", len(df['vendor'].unique()))
    c4.metric("Docs", len(df))

    st.subheader(t["table_header"])
    disp_cols = ["date", "vendor", "category", "net_amount", "tax_amount", "gross_amount"]
    edited = st.data_editor(df[disp_cols], num_rows="dynamic", width='stretch')
    
    for c in disp_cols: st.session_state['vault'][c] = edited[c]

    # INSIGHTS
    st.header(t["summary_header"])
    tab1, tab2 = st.tabs(["📊 Distribution", "🏆 Top Vendors"])
    with tab1: st.bar_chart(edited.groupby("category")["gross_amount"].sum())
    with tab2: st.bar_chart(edited.groupby("vendor")["gross_amount"].sum().sort_values(ascending=False).head(10))

    if st.button(t["ai_btn"]):
        with st.spinner("AI analyzing..."):
            model_id = 'gemini-2.0-flash'
            summary = edited.groupby("vendor")["gross_amount"].sum().to_string()
            p = f"Act as a CFO. Language: {selected_lang}. Analyze this spend: {summary}. Give 3 professional business insights."
            st.info(client.models.generate_content(model=model_id, contents=p).text)

    # EXPORT
    st.divider()
    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w") as zf:
        excel_buf = io.BytesIO()
        export_df = edited.copy()
        
        if is_pl_format:
            for c in ["net_amount", "tax_amount", "gross_amount"]:
                export_df[c] = export_df[c].apply(lambda x: str(f"{x:.2f}").replace('.', ','))
        
        with pd.ExcelWriter(excel_buf, engine='openpyxl') as writer:
            export_df.to_excel(writer, index=False)
        
        zf.writestr("Audit_Report.xlsx", excel_buf.getvalue())
        for _, r in st.session_state['vault'].iterrows():
            if r['id'] in st.session_state['storage']:
                f_data = st.session_state['storage'][r['id']]
                safe_name = f"{r['date']}_{r['vendor']}_{r['gross_amount']}.pdf".replace(" ", "_")
                zf.writestr(f"Source_Documents/{safe_name}", f_data['data'])

    st.download_button(t["download_btn"], zip_buf.getvalue(), "Finance_Audit_Package.zip")
else:
    st.info(t["empty_msg"])
    
