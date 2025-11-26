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
AVAILABLE_MODELS = ["gpt-4o-mini", "gpt-5-mini","gpt-5-nano"]

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
    st.title("🔐 Witaj w SEO Maceratorze")
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
                temperature=0.7,
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
                # Ale staramy się, żeby użytkownik widział co poszło nie tak
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
def get_embedding(text, client):
    """Pobiera wektor z OpenAI (text-embedding-3-large)."""
    # Zabezpieczenie przed pustymi polami (NaN)
    if not isinstance(text, str) or not text.strip():
        return np.zeros(3072) # Zwraca wektor zerowy

    text = text.replace("\n", " ")
    try:
        return client.embeddings.create(
            input=[text],
            model="text-embedding-3-large"
        ).data[0].embedding
    except Exception as e:
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
    tab1, tab2 = st.tabs(["📝 1. SEO Macerator", "🧠 2. Podobieństwo cosinusowe"])

    # ==========================================
    # ZAKŁADKA 1: GENERATOR (Twój kod)
    # ==========================================
    with tab1:
        st.header("Macerator")
        
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

        if st.button("🚀 Maceruj!") and df is not None:
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
    # ZAKŁADKA 2: ANALIZA SEMANTYCZNA (Z Twojego Colaba)
    # ==========================================
    with tab2:
        st.header("Analiza Semantyczna (Embeddingi)")
        st.markdown("Narzędzie do porównywania wektorowego słów kluczowych z tytułami i opisami.")
        
        uploaded_sem = st.file_uploader(
            "📂 Wybierz plik CSV z Etapu 1 (separator średnik ';')", 
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
                    # Wczytanie z separatorem średnik (zgodnie z instrukcją colab)
                    df_sem = pd.read_csv(uploaded_sem, sep=';')
                    
                    # Sprawdzenie kolumn
                    required_cols = ['generated_keyword', 'meta title', 'meta description']
                    missing = [col for col in required_cols if col not in df_sem.columns]
                    
                    if missing:
                        st.error(f"❌ BŁĄD: W pliku brakuje kolumn: {missing}")
                        st.info("Upewnij się, że plik ma separator średnik (;)")
                    else:
                        st.success(f"✅ Wczytano plik. Liczba wierszy: {len(df_sem)}")
                        
                        with st.expander("👀 Zobacz podgląd wczytanych danych"):
                            st.dataframe(df_sem.head())

                        if st.button("🚀 Uruchom analizę cosinusową"):
                            
                            progress_text = "Obliczanie embeddingów... to może chwilę potrwać."
                            my_bar = st.progress(0, text=progress_text)
                            
                            scores_title = []
                            scores_desc = []
                            total_rows = len(df_sem)

                            for i, row in df_sem.iterrows():
                                # 1. Pobierz wektory
                                vec_kw = get_embedding(str(row['generated_keyword']), client)
                                vec_title = get_embedding(str(row['meta title']), client)
                                vec_desc = get_embedding(str(row['meta description']), client)

                                # 2. Policz podobieństwo
                                score_t = cosine_similarity(vec_kw, vec_title)
                                score_d = cosine_similarity(vec_kw, vec_desc)

                                scores_title.append(round(score_t, 4))
                                scores_desc.append(round(score_d, 4))
                                
                                # Pasek postępu
                                percent_complete = min((i + 1) / total_rows, 1.0)
                                my_bar.progress(percent_complete, text=f"Przetwarzanie wiersza {i+1} z {total_rows}")

                            df_sem['score_title_match'] = scores_title
                            df_sem['score_desc_match'] = scores_desc

                            # Sortowanie
                            df_sem = df_sem.sort_values(by='score_title_match', ascending=True)
                            
                            my_bar.empty()
                            st.success("🎉 Analiza zakończona!")

                            st.write("### Wyniki (posortowane od najgorszego dopasowania tytułu):")
                            st.dataframe(df_sem[['generated_keyword', 'meta title', 'score_title_match', 'score_desc_match']].head(10))

                            st.download_button(
                                label="📥 Pobierz Raport Finalny (CSV)",
                                data=df_sem.to_csv(sep=';', index=False).encode('utf-8'),
                                file_name=f"RAPORT_FINALNY_{uploaded_sem.name}",
                                mime='text/csv',
                            )

                except Exception as e:
                    st.error(f"Wystąpił błąd podczas przetwarzania pliku: {e}")

if __name__ == "__main__":
    main()
