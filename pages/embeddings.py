import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
from openai import OpenAI

# 1. KONFIGURACJA STRONY
st.set_page_config(page_title="SEO URL Analyzer Pro", page_icon="🧠")

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
    Zaawansowana funkcja AI, która analizuje typ strony i stosuje odpowiednią strategię
    doboru słowa kluczowego, uwzględniając preferencje użytkownika.
    """
    
    if not title and not description:
        return "Błąd pobierania danych"
        
    # Budujemy zaawansowany prompt z logiką biznesową
    prompt = f"""
    Jesteś Ekspertem SEO (Senior SEO Strategist). Twoim zadaniem jest reverse-engineering słowa kluczowego (Main Keyword) dla podanego adresu URL.

    DANE WEJŚCIOWE:
    URL: {url}
    Meta Title: {title}
    Meta Description: {description}
    
    DODATKOWE INSTRUKCJE OD UŻYTKOWNIKA (PRIORYTETOWE):
    "{user_instructions}"

    LOGIKA POSTĘPOWANIA (Zastosuj odpowiednią strategię):
    1. Zidentyfikuj typ podstrony na podstawie URL i Title:
       - STRONA GŁÓWNA (Homepage) -> Fraza to nazwa Brandu/Marki.
       - PRODUKT (Product Page) -> Fraza to konkretna Nazwa Produktu (np. "Nike Air Max 90", a nie "Kup buty sportowe").
       - KATEGORIA (Category Page) -> Fraza to Nazwa Kategorii (np. "Buty do biegania", a nie "Najlepsze buty do biegania w sklepie").
       - ARTYKUŁ BLOGOWY (Blog Post) -> Fraza to główny temat wyciągnięty z tytułu (np. "jak wiązać krawat").
    
    2. Zasady edycji:
       - Nie kopiuj 1:1. Użyj swojej wiedzy, aby fraza była naturalna dla wyszukiwarki (to co wpisuje użytkownik w Google).
       - Usuń zbędne słowa typu "Tania oferta", "Sklep online", "Sprawdź teraz", chyba że użytkownik nakazał inaczej.
       - Jeśli instrukcje użytkownika są sprzeczne z powyższą logiką, ZAWSZE słuchaj użytkownika.

    OUTPUT:
    Wypisz TYLKO wynikową frazę kluczową. Żadnych cudzysłowów, żadnych wyjaśnień typu "Moja propozycja to...".
    """
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini", 
            messages=[
                {"role": "system", "content": "You are a helpful SEO assistant focused on search intent extraction."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.0 # Zero dla powtarzalności wyników
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"Błąd AI: {str(e)}"

# --- UI STREAMLIT ---

st.header("🧠 Inteligentny Generator Fraz SEO")
st.markdown("""
To narzędzie crawluje podane adresy, wyciąga ich Meta Title i Meta Description, oraz wyznacza główne słowo kluczowe.
""")

col1, col2 = st.columns([2, 1])

with col1:
    urls_input = st.text_area(
        "1. Wklej adresy URL (każdy w nowej linii):",
        height=200,
        placeholder="https://sklep.pl/buty-meskie\nhttps://sklep.pl/buty-meskie/nike-air-max\nhttps://blog.sklep.pl/jak-dobrac-rozmiar"
    )

with col2:
    st.info("💡 Wskazówka")
    st.markdown("""
    AI automatycznie wykryje:
    * 📦 **Produkt** -> Nazwa modelu
    * 📂 **Kategoria** -> Nazwa kategorii
    * 🏠 **Home** -> Nazwa Brandu
    * 📝 **Blog** -> Temat wpisu
    """)

# Nowe pole na preferencje użytkownika
user_prefs = st.text_input(
    "2. (Opcjonalne) Twoje dodatkowe instrukcje dla AI:",
    placeholder="Np. 'Zawsze dodawaj słowo Opinie do produktów' albo 'Ignoruj nazwy marek w kategoriach'",
    help="To co tu wpiszesz, zostanie doklejone do promptu i będzie miało najwyższy priorytet."
)

if st.button("🚀 Analizuj i generuj frazy", type="primary"):
    
    if not client:
        st.error("Nie można uruchomić analizy bez poprawnego klucza API.")
        st.stop()

    url_list = [url.strip() for url in urls_input.split('\n') if url.strip()]
    
    if not url_list:
        st.warning("Musisz podać przynajmniej jeden adres URL.")
    else:
        results = []
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        total_urls = len(url_list)
        
        for i, url in enumerate(url_list):
            status_text.text(f"⏳ Analiza kontekstowa ({i+1}/{total_urls}): {url}")
            
            # 1. Scraping
            title, desc = get_seo_metadata(url)
            
            # 2. AI z nową logiką i instrukcjami użytkownika
            if title is not None:
                # Przekazujemy teraz url i user_prefs do funkcji
                suggested_keyword = generate_target_keyword_advanced(url, title, desc, user_prefs, client)
                status = "Sukces"
            else:
                title = "Błąd pobierania"
                desc = "-"
                suggested_keyword = "-"
                status = "Błąd HTTP/404"
            
            results.append({
                "URL": url,
                "Meta Title": title,
                "Meta Description": desc,
                "AI Fraza (Strategia + Preferencje)": suggested_keyword,
                "Status": status
            })
            
            progress_bar.progress((i + 1) / total_urls)
            
        progress_bar.empty()
        status_text.success("✅ Gotowe! AI zastosowało logikę typów stron.")
        
        df_results = pd.DataFrame(results)
        st.dataframe(df_results, use_container_width=True)
        
        # Nazwa pliku zawiera informację, jeśli użyto customowych instrukcji
        filename_suffix = "_custom" if user_prefs else ""
        
        csv_data = df_results.to_csv(sep=';', index=False).encode('utf-8')
        st.download_button(
            label="📥 Pobierz Raport (CSV)",
            data=csv_data,
            file_name=f"analiza_seo_smart{filename_suffix}.csv",
            mime="text/csv"
        )
