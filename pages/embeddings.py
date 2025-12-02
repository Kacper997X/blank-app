import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
from openai import OpenAI

# --- FUNKCJE POMOCNICZE ---

def get_seo_metadata(url):
    """Pobiera Title i Meta Description z podanego URL."""
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        response = requests.get(url, headers=headers, timeout=5)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Pobieranie Title
        title_tag = soup.find('title')
        title = title_tag.get_text().strip() if title_tag else ""
        
        # Pobieranie Meta Description
        meta_desc_tag = soup.find('meta', attrs={'name': 'description'})
        if not meta_desc_tag:
            # Czasem nazwa jest wielką literą 'Description'
            meta_desc_tag = soup.find('meta', attrs={'name': 'Description'})
            
        description = meta_desc_tag['content'].strip() if meta_desc_tag and 'content' in meta_desc_tag.attrs else ""
        
        return title, description
    except Exception as e:
        return None, None # Zwracamy puste wartości w razie błędu

def generate_target_keyword(title, description, client):
    """Używa AI do zgadnięcia frazy kluczowej na podstawie meta tagów."""
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
            model="gpt-4o-mini", # Używamy modelu mini - jest szybki i tani, wystarczy do tego zadania
            messages=[
                {"role": "system", "content": "You are a helpful SEO assistant."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.0
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"Błąd AI: {str(e)}"

# --- UI STREAMLIT ---

st.header("🔍 Generator Frazy z URLi")
st.markdown("Wklej listę adresów URL, a narzędzie pobierze ich meta dane i zaproponuje frazę główną.")

# 1. Pole tekstowe na URLe
urls_input = st.text_area(
    "Wklej adresy URL (każdy w nowej linii):",
    height=150,
    placeholder="https://przyklad.pl/podstrona1\nhttps://przyklad.pl/podstrona2"
)

if st.button("🚀 Analizuj URLe i generuj frazy"):
    # Przygotowanie listy URLi (usuwanie pustych linii)
    url_list = [url.strip() for url in urls_input.split('\n') if url.strip()]
    
    if not url_list:
        st.warning("Musisz podać przynajmniej jeden adres URL.")
    elif not client: # Sprawdzenie czy klient OpenAI jest zainicjalizowany (z poprzednich kroków)
        st.error("Brak połączenia z API OpenAI.")
    else:
        results = []
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        total_urls = len(url_list)
        
        # Główna pętla przetwarzania
        for i, url in enumerate(url_list):
            status_text.text(f"Przetwarzanie ({i+1}/{total_urls}): {url}")
            
            # Krok 1: Scraping
            title, desc = get_seo_metadata(url)
            
            # Krok 2: AI Generation (tylko jeśli udało się pobrać dane)
            if title is not None:
                suggested_keyword = generate_target_keyword(title, desc, client)
                status = "Sukces"
            else:
                title = "Błąd"
                desc = "Błąd"
                suggested_keyword = "-"
                status = "Błąd połączenia"
            
            # Zapisanie wyniku
            results.append({
                "URL": url,
                "Meta Title": title,
                "Meta Description": desc,
                "AI Proponowana Fraza": suggested_keyword,
                "Status": status
            })
            
            # Aktualizacja paska postępu
            progress_bar.progress((i + 1) / total_urls)
            
        progress_bar.empty()
        status_text.success("✅ Zakończono analizę!")
        
        # Wyświetlenie wyników
        df_results = pd.DataFrame(results)
        st.dataframe(df_results)
        
        # Pobieranie CSV
        st.download_button(
            label="📥 Pobierz wyniki (CSV)",
            data=df_results.to_csv(sep=';', index=False).encode('utf-8'),
            file_name="analiza_url_keywords.csv",
            mime="text/csv"
        )
