import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
from openai import OpenAI
import io
import logging
import json
import bcrypt

# --- KONFIGURACJA LOGOWANIA ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# 1. KONFIGURACJA STRONY (Musi być na samym początku)
st.set_page_config(
    page_title="SEO Embeddingi i Cosinusy", 
    page_icon="🧠",
    layout="wide"
)

# ==========================================
# KONFIGURACJA UWIERZYTELNIANIA (BCRYPT)
# ==========================================
USER_DATA_PATH = 'users.json'  # Ścieżka do pliku z użytkownikami

def check_password(hashed_password, user_password):
    return bcrypt.checkpw(user_password.encode('utf-8'), hashed_password.encode('utf-8'))

def load_users():
    try:
        with open(USER_DATA_PATH, 'r') as file:
            users = json.load(file)
        return users['users']
    except FileNotFoundError:
        st.error(f"Nie znaleziono pliku {USER_DATA_PATH}. Upewnij się, że plik istnieje.")
        return {}
    except Exception as e:
        st.error(f"Błąd odczytu pliku użytkowników: {e}")
        return {}

def login(users):
    st.title("🔐 Logowanie do SEO Maceratora")
    username = st.text_input("Nazwa użytkownika")
    password = st.text_input("Hasło", type="password")
    
    if st.button("Zaloguj"):
        if username in users and check_password(users[username], password):
            st.session_state['logged_in'] = True
            st.session_state['username'] = username
            st.success("Zalogowano pomyślnie!")
            st.rerun()
        else:
            st.error("Nieprawidłowa nazwa użytkownika lub hasło")

def logout():
    st.session_state['logged_in'] = False
    st.session_state['username'] = None
    st.success("Wylogowano pomyślnie!")
    st.rerun()

# ==========================================
# LOGIKA LOGOWANIA (GŁÓWNY PRZEPŁYW)
# ==========================================

# Inicjalizacja stanu sesji
if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False
if 'username' not in st.session_state:
    st.session_state['username'] = None

# Ładowanie użytkowników
users = load_users()

# Jeśli nie zalogowany -> Pokaż ekran logowania i zatrzymaj resztę
if not st.session_state['logged_in']:
    login(users)
    st.stop()

# --- PASEK BOCZNY (SIDEBAR) ---
st.sidebar.title(f"👤 {st.session_state['username']}")
if st.sidebar.button("Wyloguj"):
    logout()

# 2. INICJALIZACJA KLIENTA OPENAI
try:
    api_key = st.secrets["OPENAI_API_KEY"]
    client = OpenAI(api_key=api_key)
except Exception:
    client = None

# --- FUNKCJE POMOCNICZE ---

def get_template_csv():
    """Generuje przykładowy plik CSV do pobrania."""
    data = [
        {
            "url": "https://sklep.pl/buty-biegowe", 
            "meta title": "Najlepsze Buty do Biegania - Sklep X", 
            "meta description": "Sprawdź naszą ofertę butów..."
        },
        {
            "url": "https://sklep.pl/blog/jak-biegac", 
            "meta title": "Jak zacząć biegać? Poradnik", 
            "meta description": "5 porad dla początkujących..."
        }
    ]
    df = pd.DataFrame(data)
    return df.to_csv(sep=';', index=False).encode('utf-8')

def get_seo_metadata(url):
    """Pobiera Title i Meta Description ze strony www (Scraping)."""
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        title_tag = soup.find('title')
        title = title_tag.get_text().strip() if title_tag else ""
        
        meta_desc_tag = soup.find('meta', attrs={'name': 'description'})
        if not meta_desc_tag:
            meta_desc_tag = soup.find('meta', attrs={'name': 'Description'})
            
        description = meta_desc_tag['content'].strip() if meta_desc_tag and 'content' in meta_desc_tag.attrs else ""
        
        return title, description
    except Exception:
        return None, None

def generate_keyword_ai(url, title, description, user_instructions, client):
    """
    Główna funkcja z Twoim nowym PROMPTEM.
    """
    # Zabezpieczenie danych
    if pd.isna(title): title = ""
    if pd.isna(description): description = ""
    if pd.isna(url): url = ""

    if not title and not description:
        return "Brak danych"

    # --- TWÓJ NOWY PROMPT ---
    prompt = f"""
    Jesteś Ekspertem SEO i Specjalistą ds. Semantyki. Twoim zadaniem jest przeanalizowanie danych wejściowych i wyekstrahowanie JEDNEJ, najbardziej trafnej głównej frazy kluczowej (Main Keyword).

    ### DANE WEJŚCIOWE:
    URL: {url}
    Title: {title}
    Description: {description}

    ### DODATKOWE INSTRUKCJE OD UŻYTKOWNIKA:
    "{user_instructions}"

    ### ZASADY ANALIZY (PRIORYTETY):
    1. Określ typ strony na podstawie URL i Title.
    2. Wybierz frazę zgodnie z poniższą logiką:
       - PRODUKT: Skup się na [Nazwa Producenta] + [Model] + [Rodzaj produktu] (np. "Nike Air Max buty do biegania").
       - KATEGORIA: Skup się na ogólnej nazwie asortymentu (np. "Laptopy gamingowe").
       - BLOG/ARTYKUŁ: Skup się na problemie lub pytaniu, które rozwiązuje tekst (np. "Jak wyczyścić buty zamszowe").
       - HOME: Skup się na nazwie Brandu lub głównej usłudze (np. "Agencja SEO Warszawa").
    3. **Hierarchia ważności:** Najważniejsze słowa kluczowe znajdują się zazwyczaj w `Title`, następnie w `URL`, a na końcu w `Description`.

    ### PRZYKŁADY (FEW-SHOT):
    Input: URL: /buty/meskie/nike-air, Title: Nike Air Max - Sklep Online, Desc: Najlepsze buty sportowe...
    Output: Buty męskie Nike Air Max

    Input: URL: /blog/jak-wiazac-krawat, Title: Poradnik eleganta - wiązanie krawata, Desc: Zobacz 5 sposobów...
    Output: jak wiązać krawat

    Input: URL: /kontakt, Title: Skontaktuj się z nami - Firma X, Desc: Adres i telefon...
    Output: Firma X kontakt

    ### FORMAT WYJŚCIOWY:
    - Zwróć WYŁĄCZNIE samą frazę kluczową.
    - Nie używaj cudzysłowów, punktorów ani znaków interpunkcyjnych na końcu.
    - Nie pisz "Oto fraza" ani żadnych wyjaśnień.
    """
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a helpful SEO assistant."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.0
        )
        return response.choices[0].message.content.strip()
    except Exception:
        return "Błąd API"

# --- INTERFEJS UŻYTKOWNIKA ---

st.title("🧠 SEO Keyword Generator Pro")
st.markdown("Narzędzie generuje pliki wsadowe (CSV) gotowe do analizy embeddingowej.")

tab1, tab2 = st.tabs(["🌍 1. Ze Scrapowaniem (Z URLi)", "📂 2. Z gotowego pliku (CSV)"])

# ==========================================
# ZAKŁADKA 1: SCRAPING
# ==========================================
with tab1:
    st.subheader("Generuj z listy URLi")
    
    c1, c2 = st.columns([2, 1])
    with c1:
        urls_input = st.text_area(
            "Lista adresów URL (jeden pod drugim):",
            height=250,
            placeholder="https://sklep.pl/kategoria\nhttps://sklep.pl/produkt-abc"
        )
    with c2:
        st.info("💡 Jak to działa?")
        st.markdown("System wejdzie na każdą stronę, pobierze Meta Title i Description, a potem AI wyznaczy frazę.")
        # Pole na instrukcje użytkownika (było wcześniej, zostaje)
        user_prefs_t1 = st.text_area(
            "Twoje instrukcje dla AI:",
            height=130,
            placeholder="Np. 'Dla produktów dodawaj słowo cena'.",
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
                
                title, desc = get_seo_metadata(url)
                
                if title is not None:
                    # Używamy instrukcji z Tab 1
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
            
            df_t1 = pd.DataFrame(results_t1)
            df_t1 = df_t1[["fraza", "meta title", "meta description", "url"]]
            
            st.dataframe(df_t1, use_container_width=True)
            st.download_button(
                "📥 Pobierz CSV (Wynik)",
                df_t1.to_csv(sep=';', index=False).encode('utf-8'),
                "wynik_scraping.csv",
                "text/csv"
            )

# ==========================================
# ZAKŁADKA 2: Z PLIKU CSV
# ==========================================
with tab2:
    st.subheader("Generuj z gotowych danych")
    
    col_d1, col_d2 = st.columns([1, 3])
    with col_d1:
        # NOWOŚĆ: Przycisk pobierania wzoru
        st.download_button(
            label="📄 Pobierz wzór pliku CSV",
            data=get_template_csv(),
            file_name="wzor_danych.csv",
            mime="text/csv",
            help="Pobierz przykładowy plik, aby zobaczyć wymaganą strukturę."
        )
    with col_d2:
        st.markdown("<- Pobierz wzór, jeśli nie wiesz jak przygotować plik.")

    st.divider()

    uploaded_file = st.file_uploader("Wgraj swój plik CSV (separator średnik ';')", type=['csv'])
    
    if uploaded_file:
        try:
            df_in = pd.read_csv(uploaded_file, sep=';', on_bad_lines='skip')
            st.success(f"Wczytano {len(df_in)} wierszy.")
            
            st.markdown("#### 1. Mapowanie kolumn")
            cols = df_in.columns.tolist()
            col_c1, col_c2, col_c3 = st.columns(3)
            
            # Auto-wykrywanie kolumn
            idx_url = next((i for i, c in enumerate(cols) if 'url' in c.lower()), 0)
            idx_tit = next((i for i, c in enumerate(cols) if 'title' in c.lower()), 0)
            idx_des = next((i for i, c in enumerate(cols) if 'desc' in c.lower()), 0)
            
            with col_c1: sel_url = st.selectbox("Kolumna URL:", cols, index=idx_url)
            with col_c2: sel_tit = st.selectbox("Kolumna Title:", cols, index=idx_tit)
            with col_c3: sel_des = st.selectbox("Kolumna Desc:", cols, index=idx_des)
            
            # NOWOŚĆ: Dodane pole na instrukcje użytkownika w zakładce 2
            st.markdown("#### 2. Dodatkowe instrukcje")
            user_prefs_t2 = st.text_input(
                "Twoje instrukcje dla AI (opcjonalne):", 
                placeholder="Np. Ignoruj nazwy marek w kategoriach.", 
                key="prefs_tab2"
            )
            
            if st.button("🚀 Generuj Frazy z pliku", key="btn_tab2"):
                if not client:
                    st.error("Brak klucza API!")
                    st.stop()
                
                results_t2 = []
                prog_bar_t2 = st.progress(0)
                total_rows = len(df_in)
                
                for i, row in df_in.iterrows():
                    u_val = str(row[sel_url])
                    t_val = str(row[sel_tit])
                    d_val = str(row[sel_des])
                    
                    # Używamy instrukcji z Tab 2
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
                st.success("✅ Zakończono!")
                
                df_t2 = pd.DataFrame(results_t2)
                df_t2 = df_t2[["fraza", "meta title", "meta description", "url"]]
                
                st.dataframe(df_t2, use_container_width=True)
                st.download_button(
                    "📥 Pobierz CSV (Wynik)",
                    df_t2.to_csv(sep=';', index=False).encode('utf-8'),
                    "wynik_z_csv.csv",
                    "text/csv"
                )

        except Exception as e:
            st.error(f"Błąd odczytu pliku: {e}")
