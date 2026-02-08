import streamlit as st
import google.generativeai as genai
from PIL import Image
import pandas as pd
import io
import json
import zipfile
import uuid
import time
import re
from datetime import datetime

# --- KONFIGURACJA STRONY ---
st.set_page_config(page_title="AI Bookkeeping Assistant", layout="wide")

# --- MAPOWANIE MIESIĘCY ---
MONTHS_PL = {
    1: "Styczeń", 2: "Luty", 3: "Marzec", 4: "Kwiecień", 5: "Maj", 6: "Czerwiec",
    7: "Lipiec", 8: "Sierpień", 9: "Wrzesień", 10: "Październik", 11: "Listopad", 12: "Grudzień"
}

# --- SMART NORMALIZACJA NAZW ---
def normalize_vendor_name(name):
    if not name: return "UNKNOWN"
    
    # Specjalna zasada dla Twojego biznesu - ujednolicenie Żabki
    if "ZABKA" in name.upper() or "ŻABKA" in name.upper():
        return "ŻABKA"
    
    # Usuwanie zbędnych członów prawnych i geograficznych
    trash = [
        r'\bsp\. z o\.o\b', r'\bspółka z o\.o\b', r'\bs\.a\b', 
        r'\bsp\.k\b', r'\bpolska\b', r'\bsa\b', r'\bgroup\b'
    ]
    clean_name = name.lower()
    for word in trash: 
        clean_name = re.sub(word, '', clean_name)
    
    # Czyszczenie znaków specjalnych i ujednolicenie wielkości liter
    clean_name = re.sub(r'[^\w\s]', '', clean_name).strip()
    return clean_name.upper()

# --- SŁOWNIK TŁUMACZEŃ ---
TRANSLATIONS = {
    "PL": {
        "title": "🌍 AI Asystent Księgowy (Smart Workflow)",
        "disclaimer": "⚠️ Ten system NIE rozlicza podatków. Służy do przygotowania Paczki Księgowej (ZIP).",
        "sidebar_header": "Panel Sterowania",
        "lang_label": "🗣️ Język:",
        "region_label": "🌍 Format Excela:",
        "clear_btn": "🗑️ Wyczyść wszystko",
        "upload_label": "Wgraj faktury (Hurtowo)",
        "analyze_btn": "🚀 Przetwórz pliki: ",
        "processing_single": "Analizuję: ",
        "table_header": "📊 Rejestr Dokumentów",
        "summary_header": "💰 Podsumowanie Kosztów",
        "total_label": "Suma kosztów",
        "download_btn": "📦 Pobierz PACZKĘ (.ZIP)",
        "empty_msg": "Wgraj pliki powyżej."
    },
    "EN": {
        "title": "🌍 AI Bookkeeping Assistant (Smart Workflow)",
        "disclaimer": "⚠️ Professional data preparation. Not a tax filing system.",
        "sidebar_header": "Control Panel",
        "lang_label": "🗣️ Language:",
        "region_label": "🌍 Excel Format:",
        "clear_btn": "🗑️ Clear All",
        "upload_label": "Upload Documents (Bulk)",
        "analyze_btn": "🚀 Process files: ",
        "processing_single": "Analyzing: ",
        "table_header": "📊 Document Register",
        "summary_header": "💰 Cost Insights",
        "total_label": "Total Costs",
        "download_btn": "📦 Download PACKAGE (.ZIP)",
        "empty_msg": "Upload files above."
    }
}

# --- INICJALIZACJA Z BEZPIECZNIKIEM KOLUMN ---
REQUIRED_COLS = ["id", "date", "vendor", "category", "currency", "amount", "type", "original_filename"]

if 'wszystkie_dokumenty' not in st.session_state:
    st.session_state['wszystkie_dokumenty'] = pd.DataFrame(columns=REQUIRED_COLS)
else:
    # Auto-fix dla starych sesji bez kolumny 'category'
    for col in REQUIRED_COLS:
        if col not in st.session_state['wszystkie_dokumenty'].columns:
            st.session_state['wszystkie_dokumenty'][col] = "INNE"

if 'file_storage' not in st.session_state:
    st.session_state['file_storage'] = {}

# --- SIDEBAR ---
with st.sidebar:
    selected_lang = st.radio("Language", ["PL", "EN"], horizontal=True)
    t = TRANSLATIONS[selected_lang]
    st.header(t["sidebar_header"])
    region_choice = st.radio(t["region_label"], ["Polska (,)", "USA (.)"], index=0)
    is_polish_format = ("Polska" in region_choice)
    
    if st.button(t["clear_btn"]):
        st.session_state['wszystkie_dokumenty'] = pd.DataFrame(columns=REQUIRED_COLS)
        st.session_state['file_storage'] = {}
        st.rerun()
    
    try: 
        api_key = st.secrets["api_key"]
    except: 
        api_key = st.text_input("Gemini API Key", type="password")

# --- UI GŁÓWNE ---
st.title(t["title"])
st.warning(t["disclaimer"])

uploaded_files = st.file_uploader(t["upload_label"], type=["jpg", "jpeg", "png", "pdf"], accept_multiple_files=True)

if uploaded_files and api_key:
    genai.configure(api_key=api_key)
    if st.button(f"{t['analyze_btn']} {len(uploaded_files)}"):
        progress_bar = st.progress(0)
        for i, uploaded_file in enumerate(uploaded_files):
            progress_bar.progress((i + 1) / len(uploaded_files))
            try:
                content = {"mime_type": "application/pdf", "data": uploaded_file.getvalue()} if uploaded_file.type == "application/pdf" else Image.open(uploaded_file)
                model = genai.GenerativeModel('gemini-2.0-flash')
                
                prompt = """
                Extract financial data into a single JSON:
                {
                    "date": "YYYY-MM-DD",
                    "vendor": "Short clean name",
                    "category": "TOWAR, MEDIA, PALIWO, USLUGI, INNE",
                    "currency": "Code",
                    "amount": 0.00,
                    "type": "Invoice/Receipt"
                }
                Return ONLY valid JSON.
                """
                response = model.generate_content([prompt, content])
                data = json.loads(response.text.replace('```json', '').replace('```', '').strip())
                if isinstance(data, list): data = data[0]

                # Normalizacja AI -> Python
                data['vendor'] = normalize_vendor_name(data.get('vendor', 'UNKNOWN'))
                
                f_id = str(uuid.uuid4())
                st.session_state['file_storage'][f_id] = {"data": uploaded_file.getvalue(), "name": uploaded_file.name}
                data['id'], data['original_filename'] = f_id, uploaded_file.name
                
                st.session_state['wszystkie_dokumenty'] = pd.concat([st.session_state['wszystkie_dokumenty'], pd.DataFrame([data])], ignore_index=True)
                time.sleep(0.3)
            except Exception as e: st.error(f"Error {uploaded_file.name}: {e}")
        st.rerun()

# --- WYNIKI I DASHBOARD ---
if not st.session_state['wszystkie_dokumenty'].empty:
    st.divider()
    df = st.session_state['wszystkie_dokumenty']
    
    # Detekcja okresu i dominującej waluty
    try:
        valid_dates = pd.to_datetime(df['date'], errors='coerce').dropna()
        first_date = valid_dates.min()
        period_text = f"{MONTHS_PL[first_date.month]} {first_date.year}" if selected_lang == "PL" else first_date.strftime("%B %Y")
    except: 
        period_text = "N/A"
    
    main_currency = df['currency'].mode()[0] if not df['currency'].empty else "PLN"
    
    # Nagłówek dynamiczny
    st.header(f"{t['total_label']} – {period_text} ({main_currency})")

    # Rejestr dokumentów
    display_cols = ["date", "vendor", "category", "currency", "amount", "type"]
    edited_df = st.data_editor(df[display_cols], num_rows="dynamic", width='stretch')
    
    # Czyszczenie i synchronizacja
    edited_df["amount"] = pd.to_numeric(edited_df["amount"], errors='coerce').fillna(0).round(2)
    for col in display_cols: 
        st.session_state['wszystkie_dokumenty'][col] = edited_df[col]

    # Podsumowania
    st.subheader(t["summary_header"])
    c1, c2 = st.columns(2)
    
    with c1:
        st.markdown("**🏢 Dostawcy (Posortowani)**")
        vend_sum = edited_df.groupby("vendor")[["amount"]].sum().sort_values(by="amount", ascending=False).round(2)
        st.dataframe(vend_sum, width='stretch')
        
    with c2:
        st.markdown("**📂 Kategorie wydatków**")
        cat_sum = edited_df.groupby("category")[["amount"]].sum().sort_values(by="amount", ascending=False).round(2)
        st.dataframe(cat_sum, width='stretch')
    
    total = edited_df["amount"].sum()
    st.metric(label=f"{t['total_label']} ({main_currency})", value=f"{total:,.2f}")

    # LOGIKA ZIP
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zf:
        excel_buf = io.BytesIO()
        export_df = edited_df.copy()
        if is_polish_format: 
            export_df["amount"] = export_df["amount"].apply(lambda x: str(f"{x:.2f}").replace('.', ','))
        
        with pd.ExcelWriter(excel_buf, engine='openpyxl') as writer:
            export_df.to_excel(writer, index=False, sheet_name='Register')
            vend_sum.to_excel(writer, index=True, sheet_name='Vendors')
            cat_sum.to_excel(writer, index=True, sheet_name='Categories')
        
        zf.writestr(f"Raport_{period_text.replace(' ', '_')}.xlsx", excel_buf.getvalue())
        for _, row in st.session_state['wszystkie_dokumenty'].iterrows():
            f_id = row['id']
            if f_id in st.session_state['file_storage']:
                f_data = st.session_state['file_storage'][f_id]
                ext = f_data['name'].split('.')[-1]
                # Nazwa pliku z kategorią dla lepszego porządku
                safe_name = f"{row['date']}_{row['vendor']}_{row['category']}_{row['amount']}.{ext}".replace(" ", "_")
                zf.writestr(f"Documents/{safe_name}", f_data['data'])

    st.download_button(t["download_btn"], zip_buffer.getvalue(), f"Paczka_Ksiegowa_{period_text}.zip", "application/zip")
else:
    st.info(t["empty_msg"])