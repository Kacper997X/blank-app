import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
from openai import OpenAI
import io
import logging
import json
import bcrypt
import numpy as np
import seaborn as sns
import matplotlib.pyplot as plt

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
def get_semantic_template_v2():
    """Generuje wzór pliku dla narzędzia semantycznego"""
    return pd.DataFrame({
        'Keyword': ['buty do biegania', 'krem nawilżający'],
        'Input1 (np. Title)': ['Najlepsze obuwie sportowe Nike', 'Krem do twarzy na dzień'],
        'Input2 (np. Desc)': ['Sprawdź naszą ofertę butów do biegania w terenie.', 'Lekka formuła nawilżająca skórę.']
    })

def get_embedding(text, client):
    """Pobiera wektor z OpenAI (text-embedding-3-large)."""
    # Zabezpieczenie przed pustymi polami (NaN) lub brakiem tekstu
    if not isinstance(text, str) or not text.strip():
        return np.zeros(3072) # Zwraca wektor zerowy

    text = text.replace("\n", " ")
    try:
        return client.embeddings.create(
            input=[text],
            model="text-embedding-3-large"
        ).data[0].embedding
    except Exception as e:
        # W razie błędu zwracamy wektor zerowy, żeby nie wywalić całego procesu
        return np.zeros(3072)

def cosine_similarity(a, b):
    """Oblicza podobieństwo (0 do 1)."""
    if np.all(a == 0) or np.all(b == 0):
        return 0.0
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))

def extract_clean_text(url):
    """Scraper wycinający menu i stopki (Anti-Boilerplate)."""
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code != 200: return None
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Usuwamy techniczne
        for element in soup(["script", "style", "nav", "footer", "header", "aside", "form", "iframe", "noscript", "svg"]):
            element.decompose()

        text = soup.get_text(separator='\n')
        lines = text.split('\n')
        clean_lines = []
        
        for line in lines:
            line = line.strip()
            if len(line) < 30: continue
            garbage_words = ["wszelkie prawa", "copyright", "polityka prywatności", "pliki cookies", "zobacz więcej", "czytaj dalej"]
            if any(word in line.lower() for word in garbage_words): continue
            clean_lines.append(line)
        
        final_text = ' '.join(clean_lines)
        if len(final_text) < 100: return soup.get_text(separator=' ')[:5000]
        return final_text[:20000]
    except Exception:
        return None


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

st.title("🧠 SEO Embeddingi i Cosinusy")
st.markdown("Narzędzie generuje pliki wsadowe (CSV) gotowe do analizy embeddingowej.")

tab1, tab2, tab3, tab4 = st.tabs([
    "🌍 1. Generowanie keyword (Z URLi)", 
    "📂 2. Generowanie keyword (Z CSV)",
    "🧠 3. Analiza Embeddingowa",
    "🕸️ 4. Site Focus & Site Radius"
])
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


    # --- DODANA SEKCJA Z INSTRUKCJĄ DLA UŻYTKOWNIKA ---
    st.info("""
    **ℹ️ Instrukcja przygotowania pliku:**
    1. Plik musi być formatu **CSV**.
    2. Separator kolumn to **średnik (;)**.
    3. Plik powinien zawierać kolumny z danymi: **URL, Title, Description** (nazwy kolumn mogą być inne, dopasujesz je poniżej).
    """)
    # --------------------------------------------------
    
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
            
            # NOWOŚĆ: Dodane pole na instrukcje użytkownika w zakładce 2 (zamienione na text_area)
            st.markdown("#### 2. Dodatkowe instrukcje")
            user_prefs_t2 = st.text_area(
                "Twoje instrukcje dla AI (opcjonalne):", 
                height=130,
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



# ==========================================
# ZAKŁADKA 3: ANALIZA SEMANTYCZNA (PRZENIESIONA)
# ==========================================
with tab3:
    st.header("Analiza Semantyczna (Embeddingi i Cosinusy)")
    st.markdown("Porównaj wektorowo **Słowo Kluczowe** z dowolnymi innymi kolumnami (np. Tytułem, Opisem).")

    with st.expander("ℹ️ Jak interpretować wyniki? (Ściąga)", expanded=False):
        st.markdown("""
        **Similarity Score** to liczba od **0 do 1**, określająca podobieństwo znaczeniowe (semantyczne), a nie tylko obecność słów.
        
        * 🟢 **0.80 - 1.00**: **Bardzo mocne dopasowanie.** Fraza i tekst znaczą niemal to samo. Idealne dla tytułów SEO.
        * 🟡 **0.65 - 0.79**: **Dobre dopasowanie.** Temat jest zgodny, ale użyto nieco innego słownictwa. Wystarczające dla opisów (meta description).
        * 🟠 **0.50 - 0.64**: **Średnie dopasowanie.** Kontekst jest podobny, ale relacja jest luźna. Warto doprecyzować treść.
        * 🔴 **Poniżej 0.50**: **Słabe dopasowanie.** Algorytm uznaje, że teksty dotyczą różnych rzeczy. Ryzyko, że Google nie powiąże frazy z treścią.
        
        💡 **Wskazówka:** Nie dąż do wyniku 1.0 za wszelką cenę (to bywa nienaturalne). W SEO zazwyczaj celujemy w przedział **0.75 - 0.90**.
        """)
    
    # Sekcja pobierania szablonu
    st.subheader("1. Pobierz wzór")
    st.download_button(
        label="📥 Pobierz przykładowy CSV (Keyword + 2 kolumny)",
        data=get_semantic_template_v2().to_csv(sep=';', index=False).encode('utf-8'),
        file_name="wzor_semantyczny.csv",
        mime="text/csv"
    )
    
    st.subheader("2. Wgraj plik i wybierz kolumny")
    uploaded_sem = st.file_uploader(
        "📂 Wybierz plik CSV (separator średnik ';')", 
        type=['csv'], 
        key="sem_uploader_tab3" # Zmieniłem key, żeby nie było konfliktu
    )

    if uploaded_sem is not None:
        # Sprawdzamy klienta (w tym pliku jest on już zainicjalizowany wcześniej)
        if client:
            try:
                # Wczytanie z separatorem średnik
                df_sem = pd.read_csv(uploaded_sem, sep=';', on_bad_lines='skip')
                
                st.success(f"✅ Wczytano plik. Liczba wierszy: {len(df_sem)}")
                
                # --- DYNAMICZNY WYBÓR KOLUMN ---
                all_columns = df_sem.columns.tolist()
                
                col1_sem, col2_sem = st.columns(2)
                
                with col1_sem:
                    # Wybór kolumny "Głównej" (Słowo kluczowe)
                    keyword_col = st.selectbox(
                        "Wybierz kolumnę ze SŁOWEM KLUCZOWYM:", 
                        options=all_columns,
                        index=0
                    )
                
                with col2_sem:
                    # Wybór kolumn do porównania
                    remaining_cols = [c for c in all_columns if c != keyword_col]
                    compare_cols = st.multiselect(
                        "Wybierz kolumny do PORÓWNANIA (max 2):",
                        options=remaining_cols,
                        default=remaining_cols[:2] if len(remaining_cols) >= 2 else remaining_cols
                    )

                # Podgląd danych
                with st.expander("👀 Zobacz podgląd danych"):
                    st.dataframe(df_sem[[keyword_col] + compare_cols].head())

                if st.button("🚀 Uruchom analizę cosinusową"):
                    if not compare_cols:
                        st.warning("Musisz wybrać przynajmniej jedną kolumnę do porównania!")
                    else:
                        progress_text = "Obliczanie embeddingów..."
                        my_bar = st.progress(0, text=progress_text)
                        
                        total_rows = len(df_sem)
                        
                        # Przygotowanie słownika na wyniki
                        results_dict = {col: [] for col in compare_cols}

                        for i, row in df_sem.iterrows():
                            # 1. Embedding słowa kluczowego
                            vec_kw = get_embedding(str(row[keyword_col]), client)

                            # 2. Pętla po kolumnach do porównania
                            for col_name in compare_cols:
                                vec_target = get_embedding(str(row[col_name]), client)
                                score = cosine_similarity(vec_kw, vec_target)
                                results_dict[col_name].append(round(score, 4))
                            
                            # Pasek postępu
                            percent_complete = min((i + 1) / total_rows, 1.0)
                            my_bar.progress(percent_complete, text=f"Przetwarzanie wiersza {i+1} z {total_rows}")

                        # Dodanie wyników do DataFrame
                        sort_column = None
                        
                        for col_name, scores in results_dict.items():
                            new_col_name = f"score_match_{col_name}"
                            df_sem[new_col_name] = scores
                            sort_column = new_col_name

                        # Sortowanie
                        if sort_column:
                            df_sem = df_sem.sort_values(by=sort_column, ascending=True)
                        
                        my_bar.empty()
                        st.success("🎉 Analiza zakończona!")

                        st.write("### Wyniki (posortowane wg dopasowania ostatniej kolumny):")
                        st.dataframe(df_sem.head(10))

                        st.download_button(
                            label="📥 Pobierz Raport Finalny (CSV)",
                            data=df_sem.to_csv(sep=';', index=False).encode('utf-8'),
                            file_name=f"RAPORT_FINALNY_{uploaded_sem.name}",
                            mime='text/csv',
                        )

            except Exception as e:
                st.error(f"Wystąpił błąd podczas przetwarzania pliku: {e}")
                st.info("Spróbuj sprawdzić czy plik jest poprawnym CSV rozdzielonym średnikami.")
        else:
            st.error("Brak klucza API w secrets!")

# ==========================================
# ZAKŁADKA 4: MATRIX KANIBALIZACJI (DODANA)
# ==========================================
with tab4:
    st.header("🕸️ Matrix Kanibalizacji (Każdy z Każdym)")
    st.markdown("""
    Narzędzie pobiera treść z listy URLi, tworzy wektory i porównuje każdą stronę z każdą inną.
    Służy do wykrywania **Duplicate Content** oraz **Kanibalizacji Słów Kluczowych**.
    """)

    col_in, col_opt = st.columns([2, 1])
    
    with col_in:
        urls_matrix_input = st.text_area(
            "Wklej listę URLi do sprawdzenia (jeden pod drugim):", 
            height=250,
            placeholder="https://domena.pl/artykul-1\nhttps://domena.pl/artykul-2",
            key="matrix_input"
        )
    
    with col_opt:
        st.info("⚙️ Ustawienia")
        threshold = st.slider("Pokaż pary o podobieństwie powyżej:", 0.0, 1.0, 0.60, 0.05)
        st.caption("0.0 = Pokaż wszystko (Pełny raport)\n0.8 = Tylko silne duplikaty")

    if st.button("🚀 Generuj Matrix Podobieństwa", key="btn_matrix"):
        if not client:
            st.error("Brak klucza API!")
            st.stop()
            
        # Przygotowanie listy URLi
        url_list = [u.strip() for u in urls_matrix_input.split('\n') if u.strip()]
        
        if len(url_list) < 2:
            st.warning("Podaj co najmniej 2 adresy URL, aby móc je porównać.")
        else:
            # Kontener na wyniki
            embeddings_list = []
            valid_urls = []
            short_names = [] # Do wykresu
            
            # UI Elementy
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            # --- 1. SCRAPING I EMBEDDINGI ---
            for i, url in enumerate(url_list):
                status_text.text(f"Pobieranie i analiza ({i+1}/{len(url_list)}): {url}")
                
                # Używamy nowej funkcji extract_clean_text
                text_content = extract_clean_text(url)
                
                if text_content and len(text_content) > 100:
                    # Generowanie embeddingu (używamy istniejącej funkcji get_embedding)
                    emb = get_embedding(text_content, client)
                    
                    embeddings_list.append(emb)
                    valid_urls.append(url)
                    
                    # Skracanie nazwy do wykresu (np. domena.pl/slug -> .../slug)
                    short_name = url.rstrip('/').split('/')[-1][:15] + "..."
                    short_names.append(short_name)
                else:
                    st.warning(f"Pominięto (brak treści/błąd): {url}")
                
                progress_bar.progress((i + 1) / len(url_list))
            
            progress_bar.empty()
            status_text.success("✅ Dane pobrane. Generuję macierz...")

            if len(embeddings_list) > 1:
                # --- 2. OBLICZENIA MACIERZOWE ---
                # Używamy sklearn dla szybkości (zakładam, że jest zainstalowany, bo był w imports w Colabie)
                from sklearn.metrics.pairwise import cosine_similarity as sklearn_cosine
                
                matrix = sklearn_cosine(embeddings_list)
                
                # --- 3. HEATMAPA (WYKRES) ---
                st.subheader("Mapa Cieplna Podobieństwa")
                fig, ax = plt.subplots(figsize=(10, 8))
                sns.heatmap(matrix, xticklabels=short_names, yticklabels=short_names, cmap="Greens", annot=True, fmt=".2f", ax=ax)
                st.pyplot(fig)
                
                # --- 4. TABELA WYNIKÓW ---
                st.subheader(f"Lista Par (Podobieństwo >= {threshold})")
                pairs = []
                all_pairs = [] # Do CSV chcemy wszystko
                
                # Przechodzimy przez górny trójkąt macierzy
                for i in range(len(matrix)):
                    for j in range(i + 1, len(matrix)):
                        score = matrix[i][j]
                        
                        # Zapisz do pełnej listy
                        all_pairs.append({
                            "URL A": valid_urls[i],
                            "URL B": valid_urls[j],
                            "Podobieństwo": round(score, 4)
                        })

                        # Zapisz do listy wyświetlanej (jeśli spełnia warunek suwaka)
                        if score >= threshold:
                            pairs.append({
                                "URL A": valid_urls[i],
                                "URL B": valid_urls[j],
                                "Podobieństwo": round(score, 4)
                            })
                
                # Wyświetlanie w aplikacji (tylko przefiltrowane)
                if pairs:
                    df_display = pd.DataFrame(pairs).sort_values(by="Podobieństwo", ascending=False)
                    st.dataframe(df_display, use_container_width=True)
                else:
                    st.info(f"Brak par o podobieństwie powyżej {threshold}. Zmień ustawienie suwaka.")

                # --- 5. POBIERANIE PEŁNEGO RAPORTU ---
                if all_pairs:
                    df_full = pd.DataFrame(all_pairs).sort_values(by="Podobieństwo", ascending=False)
                    csv_data = df_full.to_csv(sep=';', index=False).encode('utf-8')
                    
                    st.download_button(
                        label="📥 Pobierz Pełny Raport Matrix (CSV)",
                        data=csv_data,
                        file_name="matrix_kanibalizacji_full.csv",
                        mime="text/csv"
                    )
            else:
                st.error("Nie udało się pobrać wystarczającej liczby danych do porównania.")
