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

# --- KONFIGURACJA ---
st.set_page_config(page_title="Global Finance OS | Enterprise v3.4", layout="wide")

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
        "dup_file": "⚠️ Pominięto (Plik już istnieje):",
        "dup_data": "🛑 Wykryto duplikat logiczny (To samo w bazie):",
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
        "dup_file": "⚠️ Skipping (File already processed):",
        "dup_data": "🛑 Logical duplicate detected (Same data):",
        "categories": "COGS, OPEX, CAPEX, SERVICES, OTHER",
        "empty_msg": "System Ready. Please upload documents."
    }
}

# --- NARZĘDZIA ---
def calculate_file_hash(data):
    return hashlib.md5(data).hexdigest()

def robust_json_parser(text):
    """Eliminuje błędy 'Extra data' i Markdown, wycinając czysty JSON."""
    try:
        # 1. Usuń bloki kodu markdown
        text = re.sub(r'```json\s*|```', '', text)
        # 2. Znajdź skrajne klamry
        start = text.find('{')
        end = text.rfind('}')
        if start != -1 and end != -1:
            return text[start:end+1].strip()
    except: pass
    return text.strip()

def normalize_name(name):
    if not name: return "UNKNOWN"
    n = str(name).upper()
    trash = [r'\bSP\. Z O\.O\b', r'\bS\.A\b', r'\bINC\b', r'\bLTD\b', r'\bLLC\b']
    for t in trash: n = re.sub(t, '', n)
    return re.sub(r'[^\w\s]', '', n).strip()

# --- INICJALIZACJA ---
REQUIRED_COLS = ["id", "date", "vendor", "category", "currency", "net_amount", "tax_amount", "gross_amount", "hash"]
if 'vault' not in st.session_state:
    st.session_state['vault'] = pd.DataFrame(columns=REQUIRED_COLS)
if 'storage' not in st.session_state:
    st.session_state['storage'] = {}

# --- SIDEBAR ---
with st.sidebar:
    selected_lang = st.radio("Language", ["PL", "EN"], horizontal=True)
    t = TRANSLATIONS[selected_lang]
    st.header(t["sidebar_header"])
    region = st.radio(t["region_label"], [t["region_pl"], t["region_us"]])
    is_pl = (region == t["region_pl"])
    
    if st.button(t["clear_btn"]):
        st.session_state['vault'] = pd.DataFrame(columns=REQUIRED_COLS)
        st.session_state['storage'] = {}
        st.rerun()

    api_key = st.secrets.get("api_key", "") or st.text_input("Gemini API Key", type="password")

# --- UI ---
st.title(t["title"])
st.markdown(f"*{t['subtitle']}*")

files = st.file_uploader(t["upload_label"], accept_multiple_files=True)

if files and api_key:
    client = genai.Client(api_key=api_key)
    if st.button(f"{t['analyze_btn']} ({len(files)})"):
        pb = st.progress(0)
        for i, f in enumerate(files):
            pb.progress((i + 1) / len(files))
            
            f_bytes = f.getvalue()
            f_hash = calculate_file_hash(f_bytes)
            
            # TEST DUPLIKATU PLIKU
            if not st.session_state['vault'].empty and f_hash in st.session_state['vault']['hash'].values:
                st.warning(f"{t['dup_file']} {f.name}")
                continue

            try:
                prompt = f"""Extract to JSON. Categories: {t['categories']}. 
                Format: {{"date":"YYYY-MM-DD", "vendor":"Name", "category":"...", "currency":"Code", "net_amount":0.0, "tax_amount":0.0, "gross_amount":0.0}}
                Return ONLY pure JSON object."""
                
                file_part = types.Part.from_bytes(data=f_bytes, mime_type=f.type)
                resp = client.models.generate_content(model='gemini-2.0-flash', contents=[prompt, file_part])
                
                # CHIRURGICZNE WYCINANIE JSON
                cleaned_text = robust_json_parser(resp.text)
                data = json.loads(cleaned_text)
                if isinstance(data, list): data = data[0]
                
                data['vendor'] = normalize_name(data.get('vendor'))
                # Konwersja kwoty na float dla porównania
                current_gross = float(data.get('gross_amount', 0))

                # TEST DUPLIKATU DANYCH (Logiczny)
                if not st.session_state['vault'].empty:
                    # Rzutowanie kolumny na float dla pewności porównania
                    temp_df = st.session_state['vault']
                    is_dup = ((temp_df['date'] == data['date']) & 
                              (temp_df['vendor'] == data['vendor']) & 
                              (pd.to_numeric(temp_df['gross_amount']) == current_gross)).any()
                    if is_dup:
                        st.error(f"{t['dup_data']} {data['vendor']} | {data['date']} | {current_gross}")
                        continue

                f_id = str(uuid.uuid4())
                st.session_state['storage'][f_id] = {"data": f_bytes, "name": f.name}
                data['id'], data['hash'] = f_id, f_hash
                
                new_row = pd.DataFrame([data])
                for col in REQUIRED_COLS:
                    if col not in new_row.columns: new_row[col] = "N/A"
                
                st.session_state['vault'] = pd.concat([st.session_state['vault'], new_row], ignore_index=True)
                time.sleep(0.4)
            except Exception as e: st.error(f"Error {f.name}: {e}")
        st.rerun()

# --- DASHBOARD ---
if not st.session_state['vault'].empty:
    df = st.session_state['vault']
    for c in ["net_amount", "tax_amount", "gross_amount"]:
        df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0).round(2)

    st.divider()
    curr = df['currency'].mode()[0] if not df['currency'].empty else "PLN"
    c1, c2, c3 = st.columns(3)
    c1.metric(t["total_gross"], f"{df['gross_amount'].sum():,.2f} {curr}")
    c2.metric(t["total_tax"], f"{df['tax_amount'].sum():,.2f} {curr}")
    c3.metric("Records", len(df))

    st.subheader(t["table_header"])
    disp = ["date", "vendor", "category", "net_amount", "tax_amount", "gross_amount"]
    edited = st.data_editor(df[disp], num_rows="dynamic", width='stretch')
    for c in disp: st.session_state['vault'][c] = edited[c]

    if st.button(t["ai_btn"]):
        with st.spinner("Analyzing..."):
            p = f"Act as CFO. Language: {selected_lang}. Analyze this spend: {edited.groupby('vendor')['gross_amount'].sum().to_string()}. Give 3 insights."
            st.info(client.models.generate_content(model='gemini-2.0-flash', contents=p).text)

    # EXPORT
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        ex_buf = io.BytesIO()
        export_df = edited.copy()
        if is_pl:
            for c in ["net_amount", "tax_amount", "gross_amount"]:
                export_df[c] = export_df[c].apply(lambda x: str(f"{x:.2f}").replace('.', ','))
        with pd.ExcelWriter(ex_buf, engine='openpyxl') as wr: export_df.to_excel(wr, index=False)
        zf.writestr("Audit_Report.xlsx", ex_buf.getvalue())
        for _, r in st.session_state['vault'].iterrows():
            if r['id'] in st.session_state['storage']:
                f_data = st.session_state['storage'][r['id']]
                zf.writestr(f"Docs/{r['date']}_{r['vendor']}.pdf", f_data['data'])

    st.download_button(t["download_btn"], buf.getvalue(), "Finance_Package.zip")
else:
    st.info(t["empty_msg"])
    
