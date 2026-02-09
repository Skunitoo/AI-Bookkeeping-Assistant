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
import hashlib
from datetime import datetime

# --- KROK 1: DESIGN TERMINALA (CSS INJECTION) ---
st.set_page_config(page_title="Global Finance OS | Gold v3.6", layout="wide")

st.markdown("""
    <style>
    /* Terminal Background & Accents */
    .stApp { background-color: #0E1117; }
    .stMetric { background-color: #161B22; border: 1px solid #30363D; padding: 15px; border-radius: 10px; }
    .stButton>button { 
        background-color: #238636; color: white; border-radius: 5px; 
        font-weight: bold; width: 100%; border: none; height: 50px;
    }
    .stButton>button:hover { background-color: #2EA043; border: none; }
    /* Data Editor Styling */
    div[data-testid="stDataEditor"] { border: 1px solid #30363D; border-radius: 8px; }
    /* Custom Stepper */
    .stepper { display: flex; justify-content: space-between; margin-bottom: 30px; }
    .step { color: #8B949E; font-size: 0.8rem; font-weight: bold; border-bottom: 2px solid #30363D; width: 30%; text-align: center; padding-bottom: 10px; }
    .step-active { color: #58A6FF; border-bottom: 2px solid #58A6FF; }
    </style>
    """, unsafe_allow_html=True)

# --- TŁUMACZENIA SaaS ---
TRANSLATIONS = {
    "PL": {
        "title": "⚡ Zrób paczkę dla księgowej w minutę",
        "subtitle": "Koniec z ręcznym przepisywaniem faktur. Inteligentny audyt Twoich kosztów.",
        "sidebar": "Konfiguracja Systemu",
        "clear": "🗑️ Resetuj sesję",
        "upload": "Wgraj dokumenty (PDF, JPG, PNG)",
        "process": "🚀 PRZYGOTUJ PACZKĘ DLA KSIĘGOWEJ",
        "ledger": "📝 Twój Rejestr Finansowy",
        "insights": "🧠 Analiza CFO (AI)",
        "download": "📦 POBIERZ GOTOWY ZIP",
        "categories": "TOWAR, MEDIA, PALIWO, USŁUGI, INNE",
        "disclaimer": "System nie rozlicza podatków. Automatyzuje 90% pracy Twojej księgowej.",
        "dup_warning": "⚠️ Duplikat wykryty i pominięty: "
    },
    "EN": {
        "title": "⚡ Professional Accounting Pack in 60s",
        "subtitle": "Zero manual data entry. Intelligent expense auditing.",
        "sidebar": "System Settings",
        "clear": "🗑️ Reset Session",
        "upload": "Upload Documents (PDF, JPG, PNG)",
        "process": "🚀 PREPARE ACCOUNTANT PACKAGE",
        "ledger": "📝 Financial Ledger",
        "insights": "🧠 CFO Insights (AI)",
        "download": "📦 DOWNLOAD FINAL ZIP",
        "categories": "COGS, OPEX, CAPEX, SERVICES, OTHER",
        "disclaimer": "This system does not file taxes. It automates 90% of your bookkeeping manual work.",
        "dup_warning": "⚠️ Duplicate detected and skipped: "
    }
}

# --- NARZĘDZIA ---
def get_hash(data): return hashlib.md5(data).hexdigest()

def clean_json(text):
    try:
        text = re.sub(r'```json\s*|```', '', text)
        start, end = text.find('{'), text.rfind('}')
        if start != -1 and end != -1: return text[start:end+1].strip()
    except: pass
    return text.strip()

# --- INITIALIZATION ---
COLS = ["id", "date", "vendor", "category", "currency", "net_amount", "tax_amount", "gross_amount", "hash"]
if 'vault' not in st.session_state: st.session_state['vault'] = pd.DataFrame(columns=COLS)
if 'storage' not in st.session_state: st.session_state['storage'] = {}

# --- SIDEBAR & UX CONTROL ---
with st.sidebar:
    lang = st.radio("Language", ["PL", "EN"], horizontal=True)
    t = TRANSLATIONS[lang]
    st.header(t["sidebar"])
    region = st.selectbox("Format Excel:", ["EU (Przecinki ,)", "US (Kropki .)"])
    is_pl_format = ("EU" in region)
    if st.button(t["clear"]):
        st.session_state['vault'] = pd.DataFrame(columns=COLS)
        st.session_state['storage'] = {}
        st.rerun()
    api_key = st.secrets.get("api_key", "") or st.text_input("Gemini API Key", type="password")

# --- KROK 2: INTERACTIVE STEPPER ---
s1, s2, s3 = "step", "step", "step"
if st.session_state['vault'].empty: s1 = "step step-active"
elif not st.session_state['vault'].empty: s2 = "step step-active"

st.markdown(f"""
    <div class="stepper">
        <div class="{s1}">1. WGRAJ PLIKI</div>
        <div class="{s2}">2. WERYFIKACJA DANYCH</div>
        <div class="step">3. EKSPORT DO KSIĘGOWOŚCI</div>
    </div>
    """, unsafe_allow_html=True)

# --- MAIN UI ---
st.title(t["title"])
st.markdown(f"*{t['subtitle']}*")

files = st.file_uploader(t["upload"], accept_multiple_files=True)

if files and api_key:
    client = genai.Client(api_key=api_key)
    if st.button(t["process"]):
        pb = st.progress(0)
        for i, f in enumerate(files):
            pb.progress((i + 1) / len(files))
            f_bytes = f.getvalue()
            f_hash = get_hash(f_bytes)
            
            # Duplicate check
            if not st.session_state['vault'].empty and f_hash in st.session_state['vault']['hash'].values:
                st.warning(f"{t['dup_warning']} {f.name}")
                continue

            try:
                p = f"Audit this document. Categories: {t['categories']}. JSON: {{\"date\":\"YYYY-MM-DD\", \"vendor\":\"Name\", \"category\":\"...\", \"currency\":\"PLN\", \"net_amount\":0.0, \"tax_amount\":0.0, \"gross_amount\":0.0}}"
                part = types.Part.from_bytes(data=f_bytes, mime_type=f.type)
                res = client.models.generate_content(model='gemini-2.0-flash', contents=[p, part])
                
                data = json.loads(clean_json(res.text))
                if isinstance(data, list): data = data[0]
                
                f_id = str(uuid.uuid4())
                st.session_state['storage'][f_id] = {"data": f_bytes, "name": f.name}
                data['id'], data['hash'] = f_id, f_hash
                
                new_row = pd.DataFrame([data])
                for col in COLS:
                    if col not in new_row.columns: new_row[col] = "N/A"
                st.session_state['vault'] = pd.concat([st.session_state['vault'], new_row], ignore_index=True)
                time.sleep(0.4)
            except Exception as e: st.error(f"Error {f.name}: {e}")
        st.rerun()

# --- LEDGER & ANALYSIS ---
if not st.session_state['vault'].empty:
    df = st.session_state['vault']
    for c in ["net_amount", "tax_amount", "gross_amount"]:
        df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0).round(2)

    st.divider()
    curr = df['currency'].mode()[0] if not df['currency'].empty else "PLN"
    c1, c2, c3 = st.columns(3)
    c1.metric("Koszty Razem", f"{df['gross_amount'].sum():,.2f} {curr}")
    c2.metric("VAT do odzyskania", f"{df['tax_amount'].sum():,.2f} {curr}")
    c3.metric("Liczba rekordów", len(df))

    st.subheader(t["ledger"])
    disp = ["date", "vendor", "category", "net_amount", "tax_amount", "gross_amount"]
    edited = st.data_editor(df[disp], num_rows="dynamic", width='stretch')
    for c in disp: st.session_state['vault'][c] = edited[c]

    # Strategic Insight Button
    if st.button(t["insights"]):
        with st.spinner("CFO analizuje profil kosztowy..."):
            summary = edited.groupby('vendor')['gross_amount'].sum().to_string()
            p = f"Analizuj wydatki: {summary}. Daj 3 konkretne rady po polsku."
            st.info(client.models.generate_content(model='gemini-2.0-flash', contents=p).text)

    # --- PROFESSIONAL EXPORT ---
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        ex_buf = io.BytesIO()
        export_df = edited.copy()
        if is_pl_format:
            for c in ["net_amount", "tax_amount", "gross_amount"]:
                export_df[c] = export_df[c].apply(lambda x: str(f"{x:.2f}").replace('.', ','))
        with pd.ExcelWriter(ex_buf, engine='openpyxl') as wr: export_df.to_excel(wr, index=False)
        
        # Unique timestamp prevents OS lock
        ts = datetime.now().strftime("%H%M")
        zf.writestr(f"Raport_Księgowy_{ts}.xlsx", ex_buf.getvalue())
        for _, r in st.session_state['vault'].iterrows():
            if r['id'] in st.session_state['storage']:
                f_data = st.session_state['storage'][r['id']]
                zf.writestr(f"Dokumenty/{r['date']}_{r['vendor']}.pdf", f_data['data'])

    st.download_button(t["download"], buf.getvalue(), f"Paczka_Finansowa.zip")
    st.caption(t["disclaimer"])
else:
    st.info("Wgraj dokumenty powyżej, aby wygenerować rejestr.")
    
