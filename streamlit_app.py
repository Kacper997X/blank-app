import streamlit as st
import json
import bcrypt
import pandas as pd
import numpy as np
import time
from openai import OpenAI

# ==========================================
# KONFIGURACJA I STAŁE
# ==========================================
st.set_page_config(page_title="SEO Macerator & Semantic Tool", layout="wide")

USER_DATA_PATH = 'users.json'
AVAILABLE_MODELS = ["gpt-4o-mini", "gpt-5-mini", "gpt-5-nano"]

# ==========================================
# FUNKCJE UWIERZYTELNIANIA
# ==========================================
def check_password(hashed_password, user_password):
    return bcrypt.checkpw(user_password.encode('utf-8'), hashed_password.encode('utf-8'))

def load_users():
    try:
        with open(USER_DATA_PATH, 'r') as file:
            users = json.load(file)
        return users['users']
    except FileNotFoundError:
        return {}

def login(users):
    st.title("🔐 Witaj w SEO MACERATORZE!")
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
# FUNKCJE LOGICZNE - TAB 1 (GENERATOR)
# ==========================================
def get_csv_template():
    df = pd.DataFrame({'input': ['przykładowa fraza', 'https://example.com']})
    return df

def escape_braces(s):
    """Zamienia { na {{ i } na }} w stringu, by uniknąć KeyError przy .format()"""
    return str(s).replace('{', '{{').replace('}', '}}')

def process_rows_in_batches(df, batch_size, system_prompt, user_prompt, model, client):
    results = []
    
    # Tworzymy pasek postępu
    progress_bar = st.progress(0, text="Przetwarzanie...")
    total_rows = len(df)
    
    for i in range(0, len(df), batch_size):
        batch = df.iloc[i:i+batch_size]
        # Escapowanie klamer w każdej frazie!
        keywords = [escape_braces(x) for x in batch['input'].tolist()]
        prompt_filled = user_prompt.format(input="\n".join(keywords))
        
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt_filled},
                ],
            )
            content = response.choices[0].message.content.strip()
            
            # Sprawdź czy odpowiedź nie jest pusta
            if not content:
                for _ in keywords:
                    results.append("Błąd: Pusta odpowiedź AI")
                continue
                
            try:
                # Próba parsowania JSON
                batch_result = json.loads(content)
                # batch_result powinien być dict: {fraza: kategoria}
                if isinstance(batch_result, dict):
                    for keyword in keywords:
                        # Odkręcamy escape braces dla klucza słownika przy wyszukiwaniu
                        raw_key = keyword.replace('{{', '{').replace('}}', '}')
                        val = batch_result.get(raw_key) or batch_result.get(keyword, "BRAK ODPOWIEDZI")
                        results.append(val)
                else:
                    # Jeśli model zwrócił coś innego niż dict (np. listę), fallback
                    results.extend([str(content)] * len(keywords))
                    
            except json.JSONDecodeError:
                # Odpowiedź nie jest poprawnym JSON-em - zapisujemy błąd dla całego batcha
                for _ in keywords:
                    results.append(f"Błąd JSON: {content[:100]}...")
                    
        except Exception as e:
            for _ in keywords:
                results.append(f"Błąd API: {e}")
        
        # Aktualizacja paska postępu
        current_progress = min((i + batch_size) / total_rows, 1.0)
        progress_bar.progress(current_progress, text=f"Przetworzono {min(i + batch_size, total_rows)} z {total_rows} wierszy")
        time.sleep(0.5)  # By nie przekroczyć limitów API
        
    progress_bar.empty()
    return results

# ==========================================
# FUNKCJE LOGICZNE - TAB 2 (EMBEDDINGI)
# ==========================================
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

# ==========================================
# GŁÓWNA APLIKACJA
# ==========================================
def main():
    # Inicjalizacja stanu
    if 'logged_in' not in st.session_state:
        st.session_state['logged_in'] = False
    if 'username' not in st.session_state:
        st.session_state['username'] = None

    users = load_users()

    # Ekran logowania
    if not st.session_state['logged_in']:
        login(users)
        st.stop()
    
    # --- Pasek boczny ---
    st.sidebar.title(f"👤 {st.session_state['username']}")
    if st.sidebar.button("Wyloguj"):
        logout()
    
    st.title("🛠️ SEO Macerator & Semantic Tools")
    
    # --- Zakładki ---
    tab1, tab2 = st.tabs(["📝 1. SEO Macerator", "🧠 2. Analiza Semantyczna"])

    # ==========================================
    # ZAKŁADKA 1: GENERATOR (NIENARUSZONA)
    # ==========================================
    with tab1:
        st.header("Uniwersalny macerator")
            
        col1, col2 = st.columns([1, 1])
        with col1:
             st.subheader("1. Pobierz wzór")
             st.download_button(
                label="Pobierz wzór pliku CSV",
                data=get_csv_template().to_csv(index=False).encode('utf-8'),
                file_name="wzor.csv",
                mime="text/csv"
            )
        
        with col2:
             st.subheader("2. Wgraj plik")
             uploaded_file = st.file_uploader("Prześlij plik CSV (musi zawierać kolumnę 'input')", type=["csv"])

        # --- PRZYKŁADOWE PROMPTY (DOKŁADNIE TWOJE) ---
        st.subheader("Przykładowe prompty")
        prompt_examples = [
            {
                "title": "Przyporządkuj frazę do etapu ścieżki zakupowej",
                "system": """Jesteś ekspertem SEO pracującym dla marki Semilac (semilac.pl) – lidera rynku lakierów hybrydowych, akcesoriów i produktów do stylizacji paznokci. Semilac oferuje lakiery hybrydowe, żele, akcesoria do manicure i pedicure, lampy UV/LED, frezarki, ozdoby do paznokci i zestawy startowe. Klientem Semilac są zarówno osoby początkujące, jak i profesjonalistki, które szukają inspiracji, porad, produktów i miejsc zakupu.

### Twoja rola:
Wcielasz się w doświadczonego specjalistę SEO i analityka fraz kluczowych, który na podstawie listy fraz ma przypisać każdą frazę do odpowiedniego etapu ścieżki zakupowej (customer journey) oraz odrzucić frazy niezwiązane z ofertą Semilac (np. dotyczące makijażu, fryzur, innych branż beauty).

### Co masz zrobić:
Przypisz każdej frazie jeden z trzech etapów ścieżki zakupowej: Awareness, Consideration, Purchase, według podanej definicji.
Jeśli fraza nie dotyczy stylizacji paznokci lub produktów Semilac, oznacz ją jako „NIE DOTYCZY”.

### Definicje etapów ścieżki zakupowej:
# 1. **Awareness (Świadomość):**
Użytkownik szuka inspiracji, trendów, ogólnych porad lub pomysłów na stylizację paznokci. Nie zna jeszcze konkretnych produktów ani marek.
Przykłady fraz:
- modne paznokcie
- inspiracje na paznokcie
- paznokcie świąteczne
- paznokcie na lato
- wzory na paznokcie
- french paznokcie
- paznokcie jesienne kolory
- krok po kroku
- przedłużanie paznokci

# 2. **Consideration (Rozważanie):**
Użytkownik zna już swoje potrzeby: porównuje produkty, szuka konkretnych typów produktów, analizuje cechy, czyta recenzje i porównania.
Przykłady fraz:
- lakiery hybrydowe
- frezarka do paznokci
- żel do paznokci
- zestaw do paznokci
- cleaner do paznokci
- odżywka do paznokci
- lampa do paznokci
- frezy do paznokci
- paznokcie hybrydy
- paznokcie żelowe

# 3. **Purchase (Zakup/Decyzja):**
Użytkownik jest zdecydowany na zakup konkretnego produktu lub szuka miejsca, gdzie może go kupić. Używa fraz transakcyjnych, często z nazwą marki lub dodatkami zakupowymi.
Przykłady fraz:
- sklep z lakierami hybrydowymi
- kupić zestaw do paznokci
- frezarka do paznokci promocja
- lakiery hybrydowe Semilac
- Semilac zestaw startowy
- gdzie kupić żel do paznokci
- lampa do paznokci cena
""",
                "user": """Przypisz frazę "{input}" do odpowiedniego etapu ścieżki zakupowej (Awareness, Consideration, Purchase) lub oznacz jako "NIE DOTYCZY". Jako wynik podaj tylko nazwę etapu lub "NIE DOTYCZY".
            ###  Przykład odpowiedzi:
{{
  "uv nagellack": "Consideration",
  "nagellack stift": "Purchase"
}}"""
            },
            {
                "title": "Kategoryzacja słów kluczowych",
                "system": """
Jesteś ekspertem SEO analizującym frazy kluczowe dla marki Semilac (semilac.pl) – polskiego lidera rynku lakierów hybrydowych, żeli, akcesoriów i produktów do stylizacji paznokci. Oferta Semilac obejmuje lakiery hybrydowe, żele, frezarki, lampy UV/LED, zestawy startowe, akcesoria (np. cążki, pilniki, tipsy), produkty do pielęgnacji paznokci, a także szkolenia z zakresu stylizacji paznokci. Klientami Semilac są zarówno osoby początkujące, jak i profesjonalistki.

### Twoje zadanie:
Przypisz każdą frazę kluczową do jednej z poniższych kategorii produktowych. Jeśli fraza dotyczy problemów zdrowotnych paznokci, pielęgnacji, naprawy, chorób, jest ogólnomedyczna lub nie dotyczy produktów Semilac – przypisz ją do kategorii „inne”. Wybierz tylko jedną, najbardziej odpowiednią kategorię dla każdej frazy.

### Kategorie i definicje (z przykładami):
##Frezarki
Frazy dotyczące frezarek do paznokci, urządzeń frezujących, frezów, pochłaniaczy pyłu.
Przykłady: frezarka do paznokci, frezarki do paznokci, frezy do paznokci, pochłaniacz pyłu
##Inspiracje
Frazy dotyczące wyglądu, stylizacji, kolorów, wzorów, sezonowych trendów paznokci, inspiracji, galerii, np. na święta, lato, jesień, french, ombre, czerwone, czarne, krótkie paznokcie.
Przykłady: paznokcie świąteczne, french paznokcie, czerwone paznokcie, paznokcie wzory galeria, paznokcie na lato, paznokcie jesienne, czarne paznokcie, krótkie paznokcie hybrydowe
##Lakiery hybrydowe
Frazy dotyczące lakierów hybrydowych, manicure hybrydowego, hybryd, lakierów do hybryd, paznokci hybrydowych.
Przykłady: lakiery hybrydowe, paznokcie hybryda, paznokcie hybrydy, lakier hybrydowy, lakiery hybrydy, paznokcie u nóg hybryda.
##Żele UV
Frazy dotyczące żeli do paznokci, żeli UV, akrylożeli, żeli do przedłużania, akrylożelu.
Przykłady: żel do paznokci, żele uv, akrylożel, żel do przedłużania paznokci, akrylożel do paznokci
##Akcesoria
Frazy dotyczące akcesoriów do paznokci, narzędzi, materiałów pomocniczych, produktów do przygotowania i wykończenia stylizacji, np. aceton, tipsy, kuferek, nożyczki, cążki, płytki, top, primer, cleaner, folia transferowa, klej do tipsów.
Przykłady: aceton, tipsy, kuferek na kosmetyki, nożyczki do skórek, płytki do paznokci, top do paznokci, primer bezkwasowy, folia transferowa, klej do tipsów, obcinacz do paznokci, cążki, krem do rąk, odżywki do paznokci,
##Lampy
Frazy dotyczące lamp UV/LED do paznokci, lamp kosmetycznych.
Przykłady: lampa do hybryd, lampa uv do paznokci, lampy led, lampa kosmetyczna
##Zestawy
Frazy dotyczące zestawów produktów, zestawów startowych, prezentowych, zestawów do manicure/hybryd, zestawów lakierów.
Przykłady: zestaw do paznokci, zestaw do manicure, zestaw lakierów hybrydowych, zestawy do robienia paznokci
##Szkolenia
Frazy dotyczące kursów, nauki, instrukcji krok po kroku, szkoleń, tutoriali.
Przykłady: hybryda krok po kroku, hybrydowy krok po kroku, japoński manicure (jeśli w kontekście szkolenia)
##Inne
Frazy dotyczące pielęgnacji, zdrowia, naprawy, chorób, ogólnomedyczne, niepasujące do powyższych kategorii.
Przykłady: uszkodzona macierz paznokcia, zanokcica paznokcia, obgryzanie paznokci, zielona bakteria na paznokciu, macierz paznokcia
""",
                "user": """Przeanalizuj poniższe frazy kluczowe i przypisz każdą do JEDNEJ kategorii produktowej Semilac.

### Lista fraz do analizy (każda fraza w osobnej linii):
{input}

### Format odpowiedzi:
- Zwróć JSON gdzie kluczem jest dokładna fraza, a wartością jedna z kategorii
- Dozwolone kategorie: frezarki, inspiracje, lakiery hybrydowe, żele uv, akcesoria, lampy, zestawy, szkolenia, inne, pozostałe
- Nie dodawaj żadnych komentarzy, tylko czysty JSON

Przykład poprawnej odpowiedzi:
{{
  "frezarka do paznokci": "frezarki",
  "paznokcie świąteczne": "inspiracje",
  "zanokcica paznokcia": "inne"
}}
"""
            },
            {
                "title": "Tłumaczenie słów kluczowych",
                "system": """Jesteś doświadczonym tłumaczem i specjalistą SEO. Twoim zadaniem jest tłumaczenie fraz kluczowych związanych z branżą {kontekst} z języka {z_języka} na język {na_język}. 
Tłumacz frazy tak, by były naturalne, poprawne językowo i zgodne z intencją wyszukiwania użytkowników w danym kraju. Unikaj tłumaczenia dosłownego, jeśli lokalny użytkownik użyłby innej frazy. 
Nie tłumacz nazw własnych i marek. Jeśli fraza jest nieprzetłumaczalna lub nie ma sensu w danym języku, napisz „BRAK ODPOWIEDNIKA”.

Zawsze zwracaj tylko tłumaczenie frazy, bez dodatkowych komentarzy.

Przykład odpowiedzi:
{{
  "frezarka do paznokci": "nail drill",
  "paznokcie świąteczne": "christmas nails",
  "zanokcica paznokcia": "BRAK ODPOWIEDNIKA"
}}""",
                "user": """Przetłumacz poniższe frazy kluczowe z języka {z_języka} na {na_język}. 
Zwróć wynik jako czysty JSON, gdzie kluczem jest oryginalna fraza, a wartością tłumaczenie.

Lista fraz do tłumaczenia (każda w osobnej linii):
{input}
"""
            },
            {
                "title": "Rozpoznawanie brandu i lokalizacji",
                "system": """Jesteś doświadczonym specjalistą SEO działającym na rynku hiszpańskim, w branży lakierów hybrydowych (stylizacje paznokci). Twoim zadaniem jest analiza fraz kluczowych pod kątem obecności nazw brandów (marek) oraz lokalizacji geograficznych.

- Jeśli fraza kluczowa zawiera nazwę jakiejkolwiek marki (brandu) działającej na rynku hiszpańskim (np. znane firmy kosmetyczne, sklepy, sieci handlowe, itp.), oznacz ją jako "brand".
- Jeśli fraza kluczowa zawiera nazwę miasta, regionu, państwa lub innej lokalizacji geograficznej (np. "Madrid", "Barcelona", "España", "Andalucía", "cerca de mí" itp.), oznacz ją jako "localization".
- Jeśli fraza zawiera zarówno brand, jak i lokalizację, oznacz ją jako "brand".
- Jeśli fraza nie zawiera ani brandu, ani lokalizacji, oznacz ją jako "clean".

Zwracaj tylko czysty wynik klasyfikacji dla każdej frazy, bez dodatkowych komentarzy. Wynik podaj w formacie JSON, gdzie kluczem jest fraza, a wartością jedna z kategorii: "brand", "localization", "clean".

Jeśli nie jesteś pewien, czy dana fraza zawiera brand lub lokalizację, podejmij najlepszą możliwą decyzję na podstawie swojej wiedzy o rynku hiszpańskim.""",
                "user": """Przeanalizuj poniższe frazy kluczowe i dla każdej określ, czy zawiera nazwę brandu, lokalizacji, czy żadnej z tych kategorii.

Zwróć wynik jako czysty JSON, gdzie kluczem jest oryginalna fraza, a wartością jedna z kategorii: "brand", "localization", "clean".

Lista fraz do analizy (każda fraza w osobnej linii):
{input}

Przykład odpowiedzi:
{{
  "mercadona esmalte de uñas": "brand",
  "manicura en Barcelona": "localization",
  "uñas decoradas fáciles": "clean",
  "peluquería L'Oréal Madrid": "brand"
}}
"""
            }
        ]
        
        # Wybór przykładów
        cols_prompts = st.columns(len(prompt_examples))
        for i, example in enumerate(prompt_examples):
            with cols_prompts[i]:
                if st.button(example["title"], key=f"prompt_btn_{i}"):
                    st.session_state['system_prompt'] = example["system"]
                    st.session_state['user_prompt'] = example["user"]

        # Wczytanie DataFrame
        df = None
        if uploaded_file is not None:
            df = pd.read_csv(uploaded_file, encoding="utf-8")
            st.write("Nagłówki pliku CSV:", df.columns.tolist())
            if 'input' not in df.columns:
                st.error("Plik CSV musi zawierać kolumnę o nazwie 'input'.")
                df = None

        st.subheader("3. Ustaw prompty i wybierz model")
        system_prompt = st.text_area(
            "Prompt systemowy",
            value=st.session_state.get('system_prompt', ''),
            placeholder="Wpisz prompt systemowy...",
            height=200
        )
        user_prompt = st.text_area(
            "Prompt użytkownika (np. 'Stwórz opis dla: {input}')",
            value=st.session_state.get('user_prompt', ''),
            placeholder="Wpisz prompt użytkownika...",
            height=150
        )
        model = st.selectbox("Wybierz model AI", AVAILABLE_MODELS)
        batch_size = st.number_input(
            "Ile wierszy przetwarzać jednocześnie?",
            min_value=1,
            max_value=50,
            value=5,
            help="Im większa liczba, tym szybciej przetworzysz plik, ale dokładność odpowiedzi AI może być niższa."
        )

        if st.button("🚀 Maceruję!") and df is not None:
            if not system_prompt or not user_prompt:
                st.error("Uzupełnij oba prompty.")
            else:
                try:
                    # Pobieranie klucza z secrets
                    api_key = st.secrets["OPENAI_API_KEY"]
                    client = OpenAI(api_key=api_key)
                    
                    st.info("Przetwarzanie... To może chwilę potrwać.")
                    results = process_rows_in_batches(df, batch_size, system_prompt, user_prompt, model, client)
                    df['wynik'] = results
                    
                    st.success("Gotowe! Oto wyniki:")
                    st.write(df)
                    st.download_button(
                        label="Pobierz wyniki jako CSV",
                        data=df.to_csv(index=False, encoding="utf-8-sig").encode('utf-8-sig'),
                        file_name="wyniki_generator.csv",
                        mime="text/csv"
                    )
                except Exception as e:
                    st.error(f"Wystąpił błąd: {e}")
                    st.warning("Upewnij się, że masz ustawiony klucz OPENAI_API_KEY w secrets.")

    # ==========================================
    # ZAKŁADKA 2: ANALIZA SEMANTYCZNA (ZMODYFIKOWANA)
    # ==========================================
    with tab2:
        st.header("Analiza Semantyczna (Embeddingi)")
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
            key="sem_uploader"
        )

        if uploaded_sem is not None:
            # Używamy klucza z secrets
            try:
                api_key = st.secrets["OPENAI_API_KEY"]
                client = OpenAI(api_key=api_key)
            except:
                st.error("Brak klucza API w secrets!")
                client = None

            if client:
                try:
                    # Wczytanie z separatorem średnik (zgodnie z poprzednim standardem)
                    # Używamy on_bad_lines='skip', żeby nie wywaliło się na błędach formatowania
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
                        # Wybór kolumn do porównania (filtrujemy, żeby nie wybrać tej samej co keyword)
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
                            
                            # Przygotowanie słownika na wyniki {nazwa_kolumny: [lista_wynikow]}
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
                            # Tworzymy nazwy nowych kolumn np. 'score_match_MetaTitle'
                            sort_column = None
                            
                            for col_name, scores in results_dict.items():
                                new_col_name = f"score_match_{col_name}"
                                df_sem[new_col_name] = scores
                                # Zapamiętujemy ostatnią kolumnę wyniku do sortowania
                                sort_column = new_col_name

                            # Sortowanie (rosnąco - najgorsze dopasowania na górze)
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

if __name__ == "__main__":
    main()
