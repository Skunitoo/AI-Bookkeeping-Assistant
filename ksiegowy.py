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

# --- UI & STYLING (Professional Dark Mode) ---
st.set_page_config(page_title="Global Finance OS | v3.8", layout="wide")

st.markdown("""
    <style>
    .stApp { background-color: #0E1117; color: #C9D1D9; }
    .stMetric { background-color: #161B22; border: 1px solid #30363D; padding: 15px; border-radius: 10px; }
    .stButton>button { 
        background-color: #238636; color: white; border-radius: 5px; 
        font-weight: bold; width: 100%; border: none; height: 45px;
    }
    .stepper { display: flex; justify-content: space-between; margin-bottom: 25px; }
    .step { color: #8B949E; font-size: 0.85rem; font-weight: bold; border-bottom: 2px solid #30363D; width: 32%; text-align: center; padding-bottom: 8px; }
    .step-active { color: #58A6FF; border-bottom: 2px solid #58A6FF; }
    </style>
    """, unsafe_allow_html=True)

# --- LOCALIZATION ---
TRANSLATIONS = {
    "PL": {
        "title": "🚀 Paczka księgowa w minutę",
        "subtitle": "Koniec z ręcznym przepisywaniem. System gotowy do pracy.",
        "sidebar": "Ustawienia",
        "clear": "🗑️ Resetuj system",
        "upload": "Wgraj faktury lub screenshoty",
        "process": "⚙️ PRZYGOTUJ PLIKI",
        "ledger": "📝 Rejestr dokumentów",
        "insights": "🧠 Analiza strategiczna",
        "download": "📦 POBIERZ ZIP",
        "categories": "TOWAR, MEDIA, PALIWO, USŁUGI, INNE",
        "dup_msg": "⚠️ Plik pominięty (Duplikat): "
    },
    "EN": {
        "title": "🚀 One-minute accounting pack",
        "subtitle": "Zero manual entry. System ready.",
        "sidebar": "Settings",
        "clear": "🗑️ Factory Reset",
        "upload": "Upload invoices or screenshots",
        "process": "⚙️ PREPARE PACKAGE",
        "ledger": "📝 Financial Ledger",
        "insights": "🧠 Strategic Insights",
        "download": "📦 DOWNLOAD ZIP",
        "categories": "COGS, OPEX, CAPEX, SERVICES, OTHER",
        "dup_msg": "⚠️ Skipping duplicate: "
    }
}

# --- SURGICAL TOOLS ---
def robust_json_parser(text):
    """Deep extraction logic to prevent 'Extra data' errors."""
    try:
        # 1. Clean Markdown code blocks
        text = re.sub(r'```json\s*|```', '', text)
        # 2. Find the outermost braces
        start = text.find('{')
        end = text.rfind('}')
        if start != -1 and end != -1:
            json_str = text[start:end+1].strip()
            # 3. Final sanitization (remove trailing newlines)
            return json_str
    except Exception:
        pass
    return text.strip()

def get_hash(data): return hashlib.md5(data).hexdigest()

# --- INITIALIZATION ---
COLS = ["id", "date", "vendor", "category", "currency", "net_amount", "tax_amount", "gross_amount", "hash"]
if 'vault' not in st.session_state: st.session_state['vault'] = pd.DataFrame(columns=COLS)
if 'storage' not in st.session_state: st.session_state['storage'] = {}

# --- SIDEBAR ---
with st.sidebar:
    lang = st.radio("Language", ["PL", "EN"], horizontal=True)
    t = TRANSLATIONS[lang]
    st.header(t["sidebar"])
    region = st.selectbox("Format Excel:", ["Polska (,)", "International (.)"])
    is_pl = ("," in region)
    if st.button(t["clear"]):
        st.session_state['vault'] = pd.DataFrame(columns=COLS)
        st.session_state['storage'] = {}
        st.rerun()
    api_key = st.secrets.get("api_key", "") or st.text_input("Gemini API Key", type="password")

# --- STEPPER ---
s1, s2 = "step", "step"
if st.session_state['vault'].empty: s1 = "step step-active"
else: s2 = "step step-active"
st.markdown(f'<div class="stepper"><div class="{s1}">1. WGRAJ</div><div class="{s2}">2. SPRAWDŹ</div><div class="step">3. POBIERZ</div></div>', unsafe_allow_html=True)

# --- MAIN ENGINE ---
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
            
            if not st.session_state['vault'].empty and f_hash in st.session_state['vault']['hash'].values:
                st.warning(f"{t['dup_msg']} {f.name}")
                continue

            try:
                # Optimized prompt for mobile screenshots
                prompt = f"Act as an OCR auditor. Extract document data into JSON. Use categories: {t['categories']}. Schema: {{\"date\":\"YYYY-MM-DD\", \"vendor\":\"Name\", \"category\":\"...\", \"currency\":\"PLN\", \"net_amount\":0.0, \"tax_amount\":0.0, \"gross_amount\":0.0}}"
                
                # Dynamic mime_type handling
                m_type = f.type if f.type else "image/png"
                file_part = types.Part.from_bytes(data=f_bytes, mime_type=m_type)
                
                res = client.models.generate_content(model='gemini-2.0-flash', contents=[prompt, file_part])
                
                clean_text = robust_json_parser(res.text)
                data = json.loads(clean_text)
                if isinstance(data, list): data = data[0]
                
                # Logic Duplicate Check
                if not st.session_state['vault'].empty:
                    is_dup = ((st.session_state['vault']['date'] == data['date']) & 
                              (st.session_state['vault']['gross_amount'] == float(data['gross_amount']))).any()
                    if is_dup:
                        st.error(f"Duplikat logiczny: {data.get('vendor')} ({f.name})")
                        continue

                f_id = str(uuid.uuid4())
                st.session_state['storage'][f_id] = {"data": f_bytes, "name": f.name}
                data['id'], data['hash'] = f_id, f_hash
                
                new_row = pd.DataFrame([data])
                for col in COLS:
                    if col not in new_row.columns: new_row[col] = "N/A"
                
                st.session_state['vault'] = pd.concat([st.session_state['vault'], new_row], ignore_index=True)
                time.sleep(0.4)
                
            except Exception as e:
                st.error(f"❌ Błąd pliku {f.name}: {e}")
                with st.expander("Szczegóły błędu (Debug)"):
                    st.code(res.text if 'res' in locals() else "Brak odpowiedzi")
        st.rerun()

# --- TABLE & EXPORT ---
if not st.session_state['vault'].empty:
    df = st.session_state['vault']
    for c in ["net_amount", "tax_amount", "gross_amount"]:
        df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0).round(2)

    st.divider()
    c1, c2, c3 = st.columns(3)
    main_curr = df['currency'].mode()[0] if not df['currency'].empty else "PLN"
    c1.metric("Brutto", f"{df['gross_amount'].sum():,.2f} {main_curr}")
    c2.metric("Podatek", f"{df['tax_amount'].sum():,.2f} {main_curr}")
    c3.metric("Ilość", len(df))

    st.subheader(t["ledger"])
    disp = ["date", "vendor", "category", "net_amount", "tax_amount", "gross_amount"]
    edited = st.data_editor(df[disp], num_rows="dynamic", width='stretch')
    for c in disp: st.session_state['vault'][c] = edited[c]

    if st.button(t["insights"]):
        with st.spinner("Analiza portfela..."):
            summary = edited.groupby('vendor')['gross_amount'].sum().to_string()
            p = f"Analiza wydatków: {summary}. Daj 3 konkretne rady biznesowe po polsku."
            st.info(client.models.generate_content(model='gemini-2.0-flash', contents=p).text)

    # ZIP LOGIC
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        ex_buf = io.BytesIO()
        export_df = edited.copy()
        if is_pl:
            for c in ["net_amount", "tax_amount", "gross_amount"]:
                export_df[c] = export_df[c].apply(lambda x: str(f"{x:.2f}").replace('.', ','))
        with pd.ExcelWriter(ex_buf, engine='openpyxl') as wr: export_df.to_excel(wr, index=False)
        ts = datetime.now().strftime("%H%M")
        zf.writestr(f"Raport_{ts}.xlsx", ex_buf.getvalue())
        for _, r in st.session_state['vault'].iterrows():
            if r['id'] in st.session_state['storage']:
                f_data = st.session_state['storage'][r['id']]
                zf.writestr(f"Pliki/{r['date']}_{r['vendor']}.pdf", f_data['data'])

    st.download_button(t["download"], buf.getvalue(), f"Paczka_{datetime.now().strftime('%d_%m')}.zip")
else:
    st.info("System gotowy. Wgraj faktury.")
        
