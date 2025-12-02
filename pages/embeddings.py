import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
from openai import OpenAI

# 1. KONFIGURACJA STRONY
st.set_page_config(page_title="SEO URL Analyzer (Pipeline Ready)", page_icon="🔗")

# 2. INICJALIZACJA KLIENTA OPENAI
try:
    api_key = st.secrets["OPENAI_API_KEY"]
    client = OpenAI(api_key=api_key)
except Exception as e:
    st.error("⚠️ Brak klucza API w secrets! Upewnij się, że dodałeś OPENAI_API_KEY w ustawieniach Streamlit.")
    client = None

# --- FUNKCJE POMOCNICZE ---

def get_seo_metadata(url):
    """Pobiera Title i Meta Description z podanego URL."""
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Pobieranie Title
        title_tag = soup.find('title')
        title = title_tag.get_text().strip() if title_tag else ""
        
        # Pobieranie Meta Description
        meta_desc_tag = soup.find('meta', attrs={'name': 'description'})
        if not meta_desc_tag:
            meta_desc_tag = soup.find('meta', attrs={'name': 'Description'})
            
        description = meta_desc_tag['content'].strip() if meta_desc_tag and 'content' in meta_desc_tag.attrs else ""
        
        return title, description
    except Exception as e:
        return None, None 

def generate_target_keyword_advanced(url, title, description, user_instructions, client):
    """
    Generuje frazę kluczową na podstawie typu strony i instrukcji użytkownika.
    """
    if not title and not description:
        return "Błąd danych"
        
    prompt = f"""
    Jesteś Ekspertem SEO. Twoim zadaniem jest wygenerowanie JEDNEJ głównej frazy kluczowej (Main Keyword) dla podanego URL.

    DANE:
    URL: {url}
    Title: {title}
    Description: {description}
    
    INSTRUKCJE SPECJALNE: "{user_instructions}"

    LOGIKA:
    1. Zidentyfikuj typ strony (Home, Produkt, Kategoria, Blog).
    2. Dla Produktu -> Nazwa modelu.
    3. Dla Kategorii -> Nazwa kategorii.
    4. Dla Bloga -> Temat wpisu.
    5. Home -> Brand.
    
    OUTPUT:
    Tylko fraza. Żadnych zbędnych znaków.
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
    except Exception as e:
        return f"Błąd AI"

# --- UI STREAMLIT ---

st.header("🔗 Generator Fraz")
st.markdown("""
To narzędzie crawluje podane adresy, wyciąga ich Meta Title i Meta Description, oraz wyznacza główne słowo kluczowe.
To narzędzie przygotowuje plik gotowy do analizy embeddingowej. 
Format wyjściowy: **fraza; meta title; meta description; url**.
""")

col1, col2 = st.columns([2, 1])

with col1:
    urls_input = st.text_area(
        "1. Wklej adresy URL (każdy w nowej linii):",
        height=200,
        placeholder="https://sklep.pl/buty-meskie\nhttps://sklep.pl/buty-meskie/nike-air-max"
    )

with col2:
    st.info("💡 Pipeline")
    st.markdown("Wygenerowany plik CSV możesz od razu wgrać do narzędzia **Analiza Embeddingowa** jako plik wejściowy.")

user_prefs = st.text_input(
    "2. (Opcjonalne) Twoje instrukcje dla AI:",
    placeholder="Np. Ignoruj nazwy marek w kategoriach"
)

if st.button("🚀 Generuj plik wsadowy", type="primary"):
    
    if not client:
        st.error("Brak klucza API.")
        st.stop()

    url_list = [url.strip() for url in urls_input.split('\n') if url.strip()]
    
    if not url_list:
        st.warning("Podaj URLe.")
    else:
        results = []
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        total_urls = len(url_list)
        
        for i, url in enumerate(url_list):
            status_text.text(f"Analiza ({i+1}/{total_urls}): {url}")
            
            # 1. Scraping
            title, desc = get_seo_metadata(url)
            
            # 2. AI
            if title is not None:
                keyword = generate_target_keyword_advanced(url, title, desc, user_prefs, client)
            else:
                title = "Błąd"
                desc = "Błąd"
                keyword = "Błąd"
            
            # --- ZAPIS W FORMACIE DOCELOWYM ---
            # Tutaj tworzymy strukturę pod kolejne narzędzie
            results.append({
                "fraza": keyword,
                "meta title": title,
                "meta description": desc,
                "url": url
            })
            
            progress_bar.progress((i + 1) / total_urls)
            
        progress_bar.empty()
        status_text.success("✅ Gotowe!")
        
        # Tworzenie DataFrame
        df_results = pd.DataFrame(results)
        
        # Upewnienie się co do kolejności kolumn
        cols_order = ["fraza", "meta title", "meta description", "url"]
        df_results = df_results[cols_order]
        
        st.dataframe(df_results, use_container_width=True)
        
        # Pobieranie CSV (średnik jako separator!)
        csv_data = df_results.to_csv(sep=';', index=False).encode('utf-8')
        
        st.download_button(
            label="📥 Pobierz Plik Wsadowy (CSV)",
            data=csv_data,
            file_name="dane_do_embeddingow.csv",
            mime="text/csv"
        )
