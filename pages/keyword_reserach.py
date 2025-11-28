import streamlit as st
import pandas as pd
import openai
import requests
import json

# --- ZABEZPIECZENIE STRONY (Musi być na samej górze) ---
if 'logged_in' not in st.session_state or not st.session_state['logged_in']:
    st.warning("⚠️ Musisz się najpierw zalogować na stronie głównej!")
    st.stop() # Zatrzymuje ładowanie reszty kodu
    
# --- Pasek boczny z informacją o użytkowniku ---
with st.sidebar:
    if 'username' in st.session_state and st.session_state['username']:
        st.write(f"Zalogowany jako: **{st.session_state['username']}**")
    
    # Przycisk powrotu do menu głównego (opcjonalnie)
    st.page_link("streamlit_app.py", label="🏠 Wróć do strony głównej")

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
    
    # AKTUALIZACJA 1: Poprawny URL endpointu
    url = "https://api.senuto.com/api/keyword-explorer/related-keywords"
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    progress_bar = st.progress(0)
    
    for i, seed in enumerate(seeds):
        # AKTUALIZACJA 2: Poprawna struktura zapytania i ID kraju (Polska = 42)
        payload = {
            "keyword": seed,    # Czasami 'query', czasami 'keyword' - zależy od wersji, próbujemy 'keyword'
            "country_id": 42,   # 42 to ID Polski w Senuto
            "limit": 50
        }
        
        try:
            response = requests.post(url, headers=headers, json=payload)
            
            if response.status_code == 200:
                data = response.json()
                
                # AKTUALIZACJA 3: Bezpieczniejsze parsowanie (Senuto może zwracać dane różnie)
                if data.get('success', True): # Czasami success jest domyślne
                    # Szukamy listy słów w 'data' lub bezpośrednio
                    keywords_list = data.get('data', [])
                    
                    if not keywords_list and isinstance(data, list):
                        keywords_list = data
                        
                    for k in keywords_list:
                        # Wyciągamy dane, z zabezpieczeniem przed brakującymi kluczami
                        results.append({
                            "Keyword": k.get('keyword', k.get('name')),
                            "Search Volume": k.get('avg_monthly_searches', 0),
                            "CPC": k.get('cpc', 0),
                            "Source Seed": seed
                        })
            else:
                # WAŻNE: Wyświetlamy treść błędu z Senuto, żeby wiedzieć co jest nie tak
                st.error(f"Błąd Senuto dla '{seed}': Kod {response.status_code}")
                with st.expander(f"Szczegóły błędu dla {seed}"):
                    st.write(response.text) # Pokaże nam komunikat od twórców API
                
        except Exception as e:
            st.error(f"Krytyczny błąd połączenia: {e}")
        
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
