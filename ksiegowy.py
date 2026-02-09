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

# --- UI & STYLING (Financial Terminal v2) ---
st.set_page_config(page_title="Global Finance OS | v3.9", layout="wide")

st.markdown("""
    <style>
    .stApp { background-color: #0E1117; color: #C9D1D9; }
    .stMetric { background-color: #161B22; border: 1px solid #30363D; padding: 15px; border-radius: 10px; }
    .stButton>button { 
        background-color: #238636; color: white; border-radius: 6px; 
        font-weight: bold; width: 100%; border: none; height: 48px;
        transition: 0.3s;
    }
    .stButton>button:hover { background-color: #2EA043; transform: translateY(-2px); }
    .stepper { display: flex; justify-content: space-between; margin-bottom: 30px; }
    .step { color: #8B949E; font-size: 0.8rem; font-weight: bold; border-bottom: 2px solid #30363D; width: 32%; text-align: center; padding-bottom: 10px; }
    .step-active { color: #58A6FF; border-bottom: 2px solid #58A6FF; }
    /* Data Editor tweak */
    div[data-testid="stDataEditor"] { background-color: #161B22; border-radius: 8px; }
    </style>
    """, unsafe_allow_html=True)

# --- LOCALIZATION (SaaS Sales Optimized) ---
TRANSLATIONS = {
    "PL": {
        "title": "⚡ Zrób paczkę dla księgowej w minutę",
        "subtitle": "Koniec z ręcznym przepisywaniem faktur. Inteligentny audyt kosztów.",
        "sidebar": "Ustawienia Systemu",
        "clear": "🗑️ Resetuj Sesję",
        "upload": "Wgraj faktury lub screenshoty (Bulk)",
        "process": "⚙️ PRZYGOTUJ PACZKĘ DLA KSIĘGOWEJ",
        "ledger": "📝 Rejestr Dokumentów",
        "insights": "🧠 Analiza CFO (AI)",
        "download": "📦 POBIERZ GOTOWY ZIP",
        "categories": "TOWAR, MEDIA, PALIWO, USŁUGI, INNE",
        "dup_msg": "⚠️ Duplikat pominięty: "
    },
    "EN": {
        "title": "⚡ One-minute accounting pack",
        "subtitle": "Zero manual entry. Intelligent expense auditing.",
        "sidebar": "System Settings",
        "clear": "🗑️ Factory Reset",
        "upload": "Upload Documents (Invoices, Receipts)",
        "process": "⚙️ PREPARE ACCOUNTANT PACKAGE",
        "ledger": "📝 Financial Ledger",
        "insights": "🧠 CFO Insights (AI)",
        "download": "📦 DOWNLOAD FINAL ZIP",
        "categories": "COGS, OPEX, CAPEX, SERVICES, OTHER",
        "dup_msg": "⚠️ Duplicate skipped: "
    }
}

# --- SURGICAL ATOMIC PARSER (The "Extra Data" Killer) ---
def atomic_json_parser(text):
    """
    Wykorzystuje JSONDecoder do pobrania tylko pierwszego poprawnego obiektu.
    Całkowicie eliminuje błąd 'Extra data'.
    """
    try:
        # Usuń bloki kodu markdown jeśli istnieją
        text = re.sub(r'```json\s*|```', '', text)
        # Znajdź początek JSONa
        start_idx = text.find('{')
        if start_idx == -1: return None
        
        relevant_content = text[start_idx:]
        # Użyj dekodera do wycięcia dokładnie jednego obiektu
        decoder = json.JSONDecoder()
        data, end_idx = decoder.raw_decode(relevant_content)
        return data
    except Exception:
        return None

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
    region = st.selectbox("Format Excel:", ["EU (Przecinki ,)", "US (Kropki .)"])
    is_pl_format = ("EU" in region)
    if st.button(t["clear"]):
        st.session_state['vault'] = pd.DataFrame(columns=COLS)
        st.session_state['storage'] = {}
        st.rerun()
    api_key = st.secrets.get("api_key", "") or st.text_input("Gemini API Key", type="password")

# --- STEPPER UX ---
s1, s2 = "step", "step"
if st.session_state['vault'].empty: s1 = "step step-active"
else: s2 = "step step-active"
st.markdown(f'<div class="stepper"><div class="{s1}">1. WGRAJ PLIKI</div><div class="{s2}">2. WERYFIKACJA</div><div class="step">3. GOTOWY ZIP</div></div>', unsafe_allow_html=True)

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
            
            if not st.session_state['vault'].empty and f_hash in st.session_state['vault']['hash'].values:
                st.warning(f"{t['dup_msg']} {f.name}")
                continue

            try:
                prompt = f"Extract to JSON. Categories: {t['categories']}. Schema: {{\"date\":\"YYYY-MM-DD\", \"vendor\":\"Name\", \"category\":\"...\", \"currency\":\"PLN\", \"net_amount\":0.0, \"tax_amount\":0.0, \"gross_amount\":0.0}}. Return ONLY the JSON."
                
                # Obsługa MIME-type dla screenshotów
                m_type = f.type if f.type else "image/png"
                file_part = types.Part.from_bytes(data=f_bytes, mime_type=m_type)
                
                res = client.models.generate_content(model='gemini-2.0-flash', contents=[prompt, file_part])
                
                # ATOMIC PARSING
                data = atomic_json_parser(res.text)
                
                if data:
                    if isinstance(data, list): data = data[0]
                    
                    # Logic Duplicate Check
                    if not st.session_state['vault'].empty:
                        is_dup = ((st.session_state['vault']['date'] == data['date']) & 
                                  (st.session_state['vault']['gross_amount'] == float(data['gross_amount']))).any()
                        if is_dup:
                            st.error(f"Pominięto duplikat logiczny: {data.get('vendor')} ({f.name})")
                            continue

                    f_id = str(uuid.uuid4())
                    st.session_state['storage'][f_id] = {"data": f_bytes, "name": f.name}
                    data['id'], data['hash'] = f_id, f_hash
                    
                    new_row = pd.DataFrame([data])
                    for col in COLS:
                        if col not in new_row.columns: new_row[col] = "N/A"
                    st.session_state['vault'] = pd.concat([st.session_state['vault'], new_row], ignore_index=True)
                    time.sleep(0.4)
                else:
                    st.error(f"Nie udało się wyodrębnić danych z pliku: {f.name}")

            except Exception as e:
                st.error(f"Błąd krytyczny pliku {f.name}: {e}")
        st.rerun()

# --- LEDGER & EXPORT ---
if not st.session_state['vault'].empty:
    df = st.session_state['vault']
    for c in ["net_amount", "tax_amount", "gross_amount"]:
        df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0).round(2)

    st.divider()
    curr = df['currency'].mode()[0] if not df['currency'].empty else "PLN"
    c1, c2, c3 = st.columns(3)
    c1.metric("Wydatki Brutto", f"{df['gross_amount'].sum():,.2f} {curr}")
    c2.metric("Podatek VAT", f"{df['tax_amount'].sum():,.2f} {curr}")
    c3.metric("Ilość faktur", len(df))

    st.subheader(t["ledger"])
    disp = ["date", "vendor", "category", "net_amount", "tax_amount", "gross_amount"]
    edited = st.data_editor(df[disp], num_rows="dynamic", width='stretch', key="editor")
    for c in disp: st.session_state['vault'][c] = edited[c]

    if st.button(t["insights"]):
        with st.spinner("Analiza strategiczna..."):
            summary = edited.groupby('vendor')['gross_amount'].sum().to_string()
            p = f"Analizuj wydatki: {summary}. Daj 3 krótkie, brutalne rady biznesowe po polsku."
            st.info(client.models.generate_content(model='gemini-2.0-flash', contents=p).text)

    # --- ZIP EXPORT ---
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        ex_buf = io.BytesIO()
        export_df = edited.copy()
        if is_pl_format:
            for c in ["net_amount", "tax_amount", "gross_amount"]:
                export_df[c] = export_df[c].apply(lambda x: str(f"{x:.2f}").replace('.', ','))
        with pd.ExcelWriter(ex_buf, engine='openpyxl') as wr: export_df.to_excel(wr, index=False)
        ts = datetime.now().strftime("%H%M")
        zf.writestr(f"Raport_Finansowy_{ts}.xlsx", ex_buf.getvalue())
        for _, r in st.session_state['vault'].iterrows():
            if r['id'] in st.session_state['storage']:
                f_data = st.session_state['storage'][r['id']]
                zf.writestr(f"Pliki_Zrodlowe/{r['date']}_{r['vendor']}.pdf", f_data['data'])

    st.download_button(t["download"], buf.getvalue(), f"Paczka_Finansowa.zip")
else:
    st.info("Wrzuć faktury, aby wygenerować rejestr dla księgowości.")
    
