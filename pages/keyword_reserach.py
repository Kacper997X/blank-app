import streamlit as st
import pandas as pd
import openai
import requests
import json

# --- KONFIGURACJA PODSTRONY ---
st.set_page_config(page_title="Keyword Research (Senuto)", layout="wide")

st.title("🔍 Senuto AI Keyword Researcher")

# --- POBIERANIE KLUCZY (Z Secrets lub Inputu) ---
# Zalecane: Trzymaj klucze w pliku .streamlit/secrets.toml
# Wtedy pobierasz je tak: st.secrets["SENUTO_KEY"]
# Tutaj dla ułatwienia dajemy pole input, jeśli secrets nie istnieją.

if "OPENAI_API_KEY" in st.secrets:
    openai_key = st.secrets["OPENAI_API_KEY"]
else:
    openai_key = st.sidebar.text_input("Klucz OpenAI", type="password")

if "SENUTO_API_KEY" in st.secrets:
    senuto_key = st.secrets["SENUTO_API_KEY"]
else:
    senuto_key = st.sidebar.text_input("Klucz Senuto", type="password")

# --- FUNKCJA 1: GENEROWANIE SEEDÓW (AI) ---
def generate_seeds(main_keyword, context, api_key):
    if not api_key: return [main_keyword]
    
    client = openai.Client(api_key=api_key)
    prompt = f"""
    Jesteś ekspertem SEO.
    Słowo główne: {main_keyword}
    Kontekst: {context}
    
    Wypisz 5-8 precyzyjnych fraz kluczowych (tzw. seed keywords), które wpiszemy do narzędzia Senuto, aby znaleźć najlepsze słowa kluczowe pasujące do tego kontekstu.
    Zwróć wynik jako listę oddzieloną przecinkami, np.: rower damski, rower miejski, holenderka
    """
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}]
        )
        text = response.choices[0].message.content
        return [x.strip() for x in text.split(',')]
    except Exception as e:
        st.error(f"Błąd OpenAI: {e}")
        return [main_keyword]

# --- FUNKCJA 2: POBIERANIE Z SENUTO ---
def fetch_from_senuto(seeds, api_key):
    results = []
    # Endpoint do bazy słów kluczowych (Sprawdź w dokumentacji czy endpoint jest aktualny dla Twojego planu)
    # Zazwyczaj jest to POST na /api/keywords/explorer/related
    url = "https://api.senuto.com/api/keywords/explorer/related"
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    progress_bar = st.progress(0)
    
    for i, seed in enumerate(seeds):
        # Parametry zapytania Senuto
        payload = {
            "query": seed,
            "country_id": 1, # 1 = Polska
            "limit": 50      # Limit per seed (oszczędzanie punktów)
        }
        
        try:
            response = requests.post(url, headers=headers, json=payload)
            
            if response.status_code == 200:
                data = response.json()
                # Parsowanie odpowiedzi (zależy od struktury JSON Senuto)
                if data.get('success'):
                    keywords = data.get('data', [])
                    for k in keywords:
                        results.append({
                            "Keyword": k.get('keyword'),
                            "Search Volume": k.get('avg_monthly_searches'),
                            "CPC": k.get('cpc'),
                            "Source Seed": seed
                        })
            else:
                st.warning(f"Senuto zwróciło błąd dla '{seed}': {response.status_code}")
                # st.write(response.text) # Odkomentuj do debugowania
                
        except Exception as e:
            st.error(f"Błąd połączenia z Senuto: {e}")
        
        progress_bar.progress((i + 1) / len(seeds))
        
    return pd.DataFrame(results)

# --- INTERFEJS UŻYTKOWNIKA ---

col1, col2 = st.columns(2)
with col1:
    main_kw = st.text_input("Główne słowo kluczowe", "CRM dla małej firmy")
with col2:
    desc = st.text_area("Opis klienta / Cel", "Software house sprzedający prosty CRM, nie chcemy fraz darmowych ani Excela.")

if st.button("🚀 Rozpocznij Research"):
    if not senuto_key:
        st.error("Brakuje klucza Senuto API!")
    else:
        # 1. AI generuje pomysły
        with st.spinner("AI analizuje kontekst i tworzy zapytania..."):
            seeds = generate_seeds(main_kw, desc, openai_key)
        
        st.success("Wygenerowane zapytania (Seeds):")
        st.write(", ".join(seeds))
        
        # 2. Senuto pobiera dane
        with st.spinner("Pobieram dane z Senuto..."):
            df = fetch_from_senuto(seeds, senuto_key)
            
        if not df.empty:
            st.subheader(f"Znaleziono {len(df)} słów kluczowych")
            
            # Usuwanie duplikatów (bo różne seedy mogą zwrócić to samo)
            df = df.drop_duplicates(subset=['Keyword'])
            
            # Wyświetlanie tabeli
            st.dataframe(df, use_container_width=True)
            
            # Zapis do CSV
            csv = df.to_csv(index=False).encode('utf-8')
            st.download_button("Pobierz CSV", csv, "keyword_research.csv", "text/csv")
            
            # Zapis do session state (żeby dane nie zniknęły przy klikaniu w tabeli)
            st.session_state['senuto_results'] = df
        else:
            st.warning("Nie znaleziono słów kluczowych lub wystąpił błąd API.")
