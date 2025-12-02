import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
from openai import OpenAI

# 1. KONFIGURACJA STRONY (Musi być na samym początku pliku)
st.set_page_config(
    page_title="SEO Keyword Generator (Pipeline Ready)", 
    page_icon="🏭",
    layout="wide"
)

# 2. INICJALIZACJA KLIENTA OPENAI
try:
    api_key = st.secrets["OPENAI_API_KEY"]
    client = OpenAI(api_key=api_key)
except Exception:
    # Obsługa przypadku braku klucza (pokazujemy błąd dopiero przy próbie użycia)
    client = None

# --- WSPÓLNE FUNKCJE (LOGIKA BIZNESOWA) ---

def get_seo_metadata(url):
    """Pobiera Title i Meta Description ze strony www (Scraping)."""
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Title
        title_tag = soup.find('title')
        title = title_tag.get_text().strip() if title_tag else ""
        
        # Description (szukamy małą lub dużą literą)
        meta_desc_tag = soup.find('meta', attrs={'name': 'description'})
        if not meta_desc_tag:
            meta_desc_tag = soup.find('meta', attrs={'name': 'Description'})
            
        description = meta_desc_tag['content'].strip() if meta_desc_tag and 'content' in meta_desc_tag.attrs else ""
        
        return title, description
    except Exception:
        return None, None

def generate_keyword_ai(url, title, description, user_instructions, client):
    """
    Uniwersalna funkcja AI do generowania frazy.
    Działa tak samo dla danych ze scrapingu i z pliku CSV.
    """
    # Zabezpieczenie danych wejściowych
    if pd.isna(title): title = ""
    if pd.isna(description): description = ""
    if pd.isna(url): url = ""

    # Jeśli brakuje danych, nie pytamy AI
    if not title and not description:
        return "Brak danych"

    prompt = f"""
    Jesteś Ekspertem SEO. Twoim zadaniem jest wygenerowanie JEDNEJ głównej frazy kluczowej (Main Keyword).

    DANE WEJŚCIOWE:
    URL: {url}
    Title: {title}
    Description: {description}
    
    INSTRUKCJE OD UŻYTKOWNIKA: "{user_instructions}"

    LOGIKA TYPÓW STRON (Zastosuj odpowiednią strategię):
    1. PRODUKT (np. /nike-air-max) -> Fraza to konkretna nazwa modelu (np. "Nike Air Max").
    2. KATEGORIA (np. /buty-do-biegania) -> Fraza to nazwa kategorii (np. "Buty do biegania").
    3. BLOG (np. /jak-wybrac-buty) -> Fraza to temat wpisu.
    4. HOME -> Nazwa Brandu.
    
    OUTPUT:
    Wypisz TYLKO wynikową frazę. Bez cudzysłowów.
    """
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a SEO assistant."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.0
        )
        return response.choices[0].message.content.strip()
    except Exception:
        return "Błąd API"

# --- INTERFEJS UŻYTKOWNIKA (GŁÓWNY) ---

st.title("🏭 Generator Fraz SEO (Pipeline)")
st.markdown("Narzędzie generuje pliki wsadowe (CSV) gotowe do analizy embeddingowej.")

# Tworzenie zakładek
tab1, tab2 = st.tabs(["🌍 1. Ze Scrapowaniem (Z URLi)", "📂 2. Z gotowego pliku (CSV)"])

# ==========================================
# ZAKŁADKA 1: SCRAPING + AI
# ==========================================
with tab1:
    st.subheader("Generuj z listy URLi")
    st.info("Wklej linki -> System pobierze Meta Tagi -> AI dobierze frazy.")
    
    c1, c2 = st.columns([2, 1])
    with c1:
        urls_input = st.text_area(
            "Lista adresów URL (jeden pod drugim):",
            height=200,
            placeholder="https://sklep.pl/kategoria\nhttps://sklep.pl/produkt-abc"
        )
    with c2:
        user_prefs_t1 = st.text_area(
            "Instrukcje dla AI (Tab 1):",
            height=200,
            placeholder="Np. 'Dla produktów dodawaj słowo Opinie'.",
            key="prefs_tab1"
        )

    if st.button("🚀 Uruchom Scraping i Analizę", key="btn_tab1"):
        if not client:
            st.error("Brak klucza API w secrets!")
            st.stop()
            
        url_list = [u.strip() for u in urls_input.split('\n') if u.strip()]
        
        if not url_list:
            st.warning("Podaj listę URLi.")
        else:
            results_t1 = []
            progress_bar = st.progress(0)
            status_text = st.empty()
            total = len(url_list)
            
            for i, url in enumerate(url_list):
                status_text.text(f"Pobieranie ({i+1}/{total}): {url}")
                
                # 1. Scraping
                title, desc = get_seo_metadata(url)
                
                # 2. AI
                if title is not None:
                    keyword = generate_keyword_ai(url, title, desc, user_prefs_t1, client)
                else:
                    title, desc, keyword = "Błąd", "Błąd", "Błąd"
                
                results_t1.append({
                    "fraza": keyword,
                    "meta title": title,
                    "meta description": desc,
                    "url": url
                })
                progress_bar.progress((i + 1) / total)
            
            progress_bar.empty()
            status_text.success("✅ Gotowe!")
            
            # Wynik i pobieranie
            df_t1 = pd.DataFrame(results_t1)
            df_t1 = df_t1[["fraza", "meta title", "meta description", "url"]] # Wymuszona kolejność
            
            st.dataframe(df_t1, use_container_width=True)
            st.download_button(
                "📥 Pobierz CSV (Scraping)",
                df_t1.to_csv(sep=';', index=False).encode('utf-8'),
                "wynik_ze_scrapingu.csv",
                "text/csv"
            )

# ==========================================
# ZAKŁADKA 2: Z PLIKU CSV (BEZ SCRAPINGU)
# ==========================================
with tab2:
    st.subheader("Generuj z gotowych danych")
    st.info("Masz plik z Screaming Frog? Wgraj go tutaj. AI dorobi tylko frazy (szybciej, bez blokad).")
    
    uploaded_file = st.file_uploader("Wgraj plik CSV (separator średnik ';')", type=['csv'])
    
    if uploaded_file:
        try:
            df_in = pd.read_csv(uploaded_file, sep=';', on_bad_lines='skip')
            st.success(f"Wczytano {len(df_in)} wierszy.")
            
            st.markdown("#### Mapowanie kolumn")
            cols = df_in.columns.tolist()
            col_c1, col_c2, col_c3 = st.columns(3)
            
            # Inteligentny wybór domyślny
            idx_url = next((i for i, c in enumerate(cols) if 'url' in c.lower()), 0)
            idx_tit = next((i for i, c in enumerate(cols) if 'title' in c.lower()), 0)
            idx_des = next((i for i, c in enumerate(cols) if 'desc' in c.lower()), 0)
            
            with col_c1: sel_url = st.selectbox("Kolumna URL:", cols, index=idx_url)
            with col_c2: sel_tit = st.selectbox("Kolumna Title:", cols, index=idx_tit)
            with col_c3: sel_des = st.selectbox("Kolumna Desc:", cols, index=idx_des)
            
            user_prefs_t2 = st.text_input("Instrukcje dla AI (Tab 2):", placeholder="Opcjonalne instrukcje...", key="prefs_tab2")
            
            if st.button("🚀 Generuj Frazy z pliku", key="btn_tab2"):
                if not client:
                    st.error("Brak klucza API!")
                    st.stop()
                
                results_t2 = []
                prog_bar_t2 = st.progress(0)
                total_rows = len(df_in)
                
                for i, row in df_in.iterrows():
                    # Pobieranie danych z mapowanych kolumn
                    u_val = str(row[sel_url])
                    t_val = str(row[sel_tit])
                    d_val = str(row[sel_des])
                    
                    # Generowanie (ta sama funkcja co w Tab 1)
                    kw = generate_keyword_ai(u_val, t_val, d_val, user_prefs_t2, client)
                    
                    results_t2.append({
                        "fraza": kw,
                        "meta title": t_val,
                        "meta description": d_val,
                        "url": u_val
                    })
                    
                    if i % 5 == 0 or i == total_rows - 1:
                        prog_bar_t2.progress((i + 1) / total_rows)
                
                prog_bar_t2.empty()
                st.success("✅ Przetwarzanie pliku zakończone!")
                
                df_t2 = pd.DataFrame(results_t2)
                df_t2 = df_t2[["fraza", "meta title", "meta description", "url"]] # Wymuszona kolejność
                
                st.dataframe(df_t2, use_container_width=True)
                st.download_button(
                    "📥 Pobierz CSV (Z Pliku)",
                    df_t2.to_csv(sep=';', index=False).encode('utf-8'),
                    "wynik_z_csv.csv",
                    "text/csv"
                )

        except Exception as e:
            st.error(f"Błąd odczytu pliku: {e}")
