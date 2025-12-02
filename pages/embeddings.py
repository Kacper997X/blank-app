import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
from openai import OpenAI

# 1. KONFIGURACJA STRONY (Musi być na samym początku)
st.set_page_config(page_title="SEO URL Analyzer", page_icon="🔍")

# 2. INICJALIZACJA KLIENTA OPENAI
# To naprawia błąd "NameError: name 'client' is not defined"
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
        # Udajemy przeglądarkę, żeby serwery nas nie blokowały
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Pobieranie Title
        title_tag = soup.find('title')
        title = title_tag.get_text().strip() if title_tag else ""
        
        # Pobieranie Meta Description
        # Szukamy zarówno 'description' jak i 'Description' (wielkość liter ma znaczenie w kodzie, choć nie w HTML)
        meta_desc_tag = soup.find('meta', attrs={'name': 'description'})
        if not meta_desc_tag:
            meta_desc_tag = soup.find('meta', attrs={'name': 'Description'})
            
        description = meta_desc_tag['content'].strip() if meta_desc_tag and 'content' in meta_desc_tag.attrs else ""
        
        return title, description
    except Exception as e:
        # W razie błędu zwracamy None, żeby potem oznaczyć status jako Błąd
        return None, None 

def generate_target_keyword(title, description, client):
    """Używa AI do zgadnięcia frazy kluczowej na podstawie meta tagów."""
    
    # Jeśli scraping się nie udał, nie pytamy AI
    if not title and not description:
        return "Błąd pobierania danych"
        
    prompt = f"""
    Jesteś ekspertem SEO. Przeanalizuj poniższe dane ze strony internetowej:
    
    Meta Title: {title}
    Meta Description: {description}
    
    Zadanie: Zidentyfikuj JEDNĄ główną frazę kluczową (Main Keyword), pod którą ta strona jest najprawdopodobniej optymalizowana.
    Wypisz tylko tę frazę, bez cudzysłowów i zbędnych komentarzy.
    """
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini", # Model mini jest idealny do tego zadania (tani i szybki)
            messages=[
                {"role": "system", "content": "You are a helpful SEO assistant."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.0
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"Błąd AI: {str(e)}"

# --- UI (INTERFEJS UŻYTKOWNIKA) ---

st.header("🔍 Generator Frazy z URLi")
st.markdown("""
To narzędzie wchodzi na podane strony, pobiera ich **Meta Title** i **Description**, 
a następnie prosi AI o wskazanie, na jaką **frazę kluczową** strona jest pozycjonowana.
""")

# Pole tekstowe na URLe
urls_input = st.text_area(
    "Wklej adresy URL (każdy w nowej linii):",
    height=150,
    placeholder="https://przyklad.pl/podstrona1\nhttps://przyklad.pl/podstrona2"
)

if st.button("🚀 Analizuj URLe i generuj frazy", type="primary"):
    
    # Walidacja klienta OpenAI przed startem
    if not client:
        st.error("Nie można uruchomić analizy bez poprawnego klucza API.")
        st.stop()

    # Przygotowanie listy URLi (usuwanie pustych linii)
    url_list = [url.strip() for url in urls_input.split('\n') if url.strip()]
    
    if not url_list:
        st.warning("Musisz podać przynajmniej jeden adres URL.")
    else:
        results = []
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        total_urls = len(url_list)
        
        # --- GŁÓWNA PĘTLA ---
        for i, url in enumerate(url_list):
            # Wyświetlanie aktualnie przetwarzanego linku
            status_text.text(f"⏳ Przetwarzanie ({i+1}/{total_urls}): {url}")
            
            # Krok 1: Scraping (Pobieranie danych ze strony)
            title, desc = get_seo_metadata(url)
            
            # Krok 2: AI (Analiza danych)
            if title is not None:
                suggested_keyword = generate_target_keyword(title, desc, client)
                status = "Sukces"
            else:
                title = "Błąd pobierania"
                desc = "-"
                suggested_keyword = "-"
                status = "Błąd HTTP/404"
            
            # Zapisanie wyniku do listy
            results.append({
                "URL": url,
                "Meta Title": title,
                "Meta Description": desc,
                "AI Proponowana Fraza": suggested_keyword,
                "Status": status
            })
            
            # Aktualizacja paska postępu
            progress_bar.progress((i + 1) / total_urls)
            
        # --- KONIEC PĘTLI ---
        progress_bar.empty()
        status_text.success("✅ Zakończono analizę wszystkich linków!")
        
        # Wyświetlenie wyników w tabeli
        df_results = pd.DataFrame(results)
        st.dataframe(df_results, use_container_width=True)
        
        # Przycisk pobierania CSV
        csv_data = df_results.to_csv(sep=';', index=False).encode('utf-8')
        st.download_button(
            label="📥 Pobierz wyniki (CSV Excel)",
            data=csv_data,
            file_name="analiza_seo_urls.csv",
            mime="text/csv"
        )
