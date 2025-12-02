import streamlit as st
import json
import bcrypt
import pandas as pd
import time
from openai import OpenAI
import re
from docx import Document

# ==========================================
# KONFIGURACJA I STAŁE
# ==========================================
st.set_page_config(page_title="SEO Macerator & Semantic Tool", layout="wide")

USER_DATA_PATH = 'users.json'
AVAILABLE_MODELS = ["gpt-4o-mini", "gpt-5-mini", "gpt-5-nano"]

# --- DOMYŚLNY SZABLON HTML (Można go edytować w aplikacji) ---
DEFAULT_HTML_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Podsumowanie tygodnia</title>
</head>
<body style="margin: 0; padding: 0; font-family: Arial, sans-serif; background-color: #f3f3f3;">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" align="center">
        <tr>
            <td align="center">
                <table role="presentation" width="600" cellspacing="0" cellpadding="0" border="0" style="background-color: #ffffff; border: 1px solid #ddd;">
                    <!-- Logo firmy -->
                    <tr>
                        <td style="background-color: #000000; padding: 20px; text-align: center;">
                            <img src="https://www.performics.com/pl/wp-content/uploads/2015/10/performics-logo248x43.png" alt="Logo Firmy" width="150" style="display: block; margin: 0 auto;">
                        </td>
                    </tr>

                    <!-- Nagłówek -->
                    <tr>
                        <td style="background-color: #000000; color: white; text-align: center; padding: 20px; font-size: 22px; font-weight: bold;">
                            📢 Podsumowanie tygodnia – [DATA]
                        </td>
                    </tr>

                    <!-- Breaking News -->
                    <tr>
                        <td style="padding: 20px; background-color: #fafafa; color: #000000;">
                            <b style="color: #33D76F;">📢 Breaking News:</b><br><br>
                            <ul style="padding-left: 20px;">
                                <!-- TU WSTAW NEWSY BREAKING -->
                            </ul>
                        </td>
                    </tr>

                    <!-- Informacje ogólne -->
                    <tr>
                        <td style="padding: 20px; background-color: #fafafa; color: #000000;">
                            <b style="color: #33D76F;">📌 Informacje ogólne:</b><br><br>
                            <ul style="padding-left: 20px;">
                                <!-- TU WSTAW INFO OGÓLNE -->
                            </ul>
                        </td>
                    </tr>

                    <!-- Produkty, usługi -->
                    <tr>
                        <td style="padding: 20px; color: #000000;">
                            <b style="color: #33D76F;">🛠 Produkty, usługi:</b><br><br>
                            <ul style="padding-left: 20px;">
                                <!-- TU WSTAW PRODUKTY -->
                            </ul>
                        </td>
                    </tr>

                    <!-- Projekty na aktualnych Klientach -->
                    <tr>
                        <td style="padding: 20px; background-color: #fafafa; color: #000000;">
                            <b style="color: #33D76F;">📊 Projekty na aktualnych Klientach:</b><br><br>
                            <ul style="padding-left: 20px;">
                                <!-- TU WSTAW PROJEKTY -->
                            </ul>
                        </td>
                    </tr>

                    <!-- Przetargi/prospekty -->
                    <tr>
                        <td style="padding: 20px; color: #000000;">
                            <b style="color: #33D76F;">📢 Przetargi/prospekty:</b><br><br>
                            <ul style="padding-left: 20px;">
                                <!-- TU WSTAW PRZETARGI -->
                            </ul>
                        </td>
                    </tr>

                    <!-- Stopka -->
                    <tr>
                        <td style="background-color: #000000; color: white; text-align: center; padding: 15px; font-size: 14px;">
                            &copy; Performics | Wszystkie prawa zastrzeżone
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>"""

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
# FUNKCJE DLA ZAKŁADKI 3 (INTELIGENTNY MERGE)
# ==========================================

def get_full_text_from_docx(docx_file):
    """Wyciąga cały tekst z pliku Word jako jeden długi string, zachowując linki."""
    doc = Document(docx_file)
    full_text = []
    rels = doc.part.rels
    
    for para in doc.paragraphs:
        if not para.text.strip(): continue
        p_text = ""
        # Próba wyciągnięcia tekstu z linkami
        for child in para._element:
            if child.tag.endswith('r') and child.text:
                p_text += child.text
            elif child.tag.endswith('hyperlink'):
                try:
                    rId = child.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id')
                    if rId in rels:
                        url = rels[rId].target_ref
                        link_text = "".join([node.text for node in child.iter() if node.tag.endswith('t')])
                        if link_text and url: p_text += f" [{link_text}]({url}) "
                        else: p_text += link_text
                except: pass
        if not p_text: p_text = para.text
        full_text.append(p_text)
        
    return "\n".join(full_text)

def generate_smart_html(html_template, content_text, date_str, client, model="gpt-4o"):
    """
    Wysyła szablon HTML i treść Worda do AI z poleceniem ich połączenia.
    """
    system_prompt = """Jesteś ekspertem HTML i redaktorem newslettera.
Twoim zadaniem jest wypełnienie dostarczonego szablonu HTML treścią z pliku tekstowego.

ZASADY:
1. Przeanalizuj 'Treść Newslettera' i zidentyfikuj sekcje (Breaking News, Informacje Ogólne, Projekty, Przetargi).
2. Wstaw odpowiednie fragmenty tekstu w odpowiednie miejsca w 'Szablonie HTML' (np. w miejsce komentarzy <!-- TU WSTAW... -->).
3. Podmień [DATA] w nagłówku na podaną datę.
4. FORMATOWANIE TREŚCI (BARDZO WAŻNE):
   - Każdy news wstaw jako element `<li>...</li>`.
   - Zachowaj istniejącą strukturę `<ul>` z szablonu.
   - POGRUB (używając tagu `<b>`) wszystkie: Imiona i nazwiska, Marki (np. Media Markt), Firmy, Narzędzia, Kluczowe daty.
   - Linki w formacie `[tekst](url)` zamień na `<a href="url" style="color: #33D76F; font-weight: bold; text-decoration: none;">tekst</a>`.
5. Zwróć TYLKO kompletny kod HTML. Nie usuwaj stylów CSS.
"""

    user_message = f"""
--- DATA WYDANIA: {date_str} ---

--- SZABLON HTML: ---
{html_template}

--- TREŚĆ Z WORDA: ---
{content_text}
"""

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            temperature=0.1
        )
        content = response.choices[0].message.content.strip()
        # Usunięcie znaczników markdown
        content = content.replace("```html", "").replace("```", "").strip()
        return content
    except Exception as e:
        return f"<h3>Wystąpił błąd AI:</h3><p>{e}</p>"




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
    
    st.title("🛠️ SEO Narzędzia")
    
    # --- Zakładki ---
    tab1 = st.tabs(["📝 1. SEO Macerator"])

    # ==========================================
    # ZAKŁADKA 1: GENERATOR (NIENARUSZONA)
    # ==========================================
    with tab1:
        st.header("Uniwersalny SEO Macerator")
            
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
    # ZAKŁADKA 3: INTELIGENTNY NEWSLETTER (SMART MERGE)
    # ==========================================
    if False:
        st.header("Generator Newslettera (Metoda: Wzór + Treść)")
        st.markdown("To narzędzie działa jak ChatGPT: Dajesz mu wzór HTML, dajesz treść z Worda, a AI łączy to w całość, zachowując style.")

        col_left, col_right = st.columns([1, 1])

        with col_left:
            st.subheader("1. Konfiguracja")
            
            # Edycja Wzoru HTML
            with st.expander("A. Edytuj Wzór HTML (Szablon)", expanded=False):
                html_template_input = st.text_area(
                    "Kod HTML z miejscami na treść:", 
                    value=DEFAULT_HTML_TEMPLATE, 
                    height=300,
                    key="html_template_area"
                )

            # Wgrywanie treści
            st.markdown("**B. Treść (Word)**")
            uploaded_doc = st.file_uploader("Wgraj plik .docx z treścią", type="docx", key="smart_doc_uploader")
            
            # Opcja ręczna
            manual_content = st.text_area("LUB wklej treść ręcznie tutaj:", height=150, placeholder="Wklej treść maila/dokumentu tutaj...")
            
            date_str = st.text_input("Data wydania (np. 29 Listopada)", "29 Listopada")

            generate_btn = st.button("✨ GENERUJ NEWSLETTER (AI)", type="primary")

        with col_right:
            st.subheader("2. Wynik")
            
            if generate_btn:
                # 1. Pobranie treści
                content_to_process = ""
                if uploaded_doc:
                    try:
                        content_to_process = get_full_text_from_docx(uploaded_doc)
                        st.success("Pobrano treść z pliku Word.")
                    except Exception as e:
                        st.error(f"Błąd odczytu pliku: {e}")
                elif manual_content.strip():
                    content_to_process = manual_content
                
                if not content_to_process:
                    st.warning("Musisz wgrać plik Word lub wkleić treść!")
                else:
                    # 2. Generowanie przez AI
                    try:
                        api_key = st.secrets["OPENAI_API_KEY"]
                        client = OpenAI(api_key=api_key)
                        
                        with st.spinner("AI łączy treść z szablonem i formatuje... To potrwa kilka sekund."):
                            # Używamy gpt-4o dla najlepszej jakości rozumienia kontekstu
                            final_html = generate_smart_html(html_template_input, content_to_process, date_str, client, model="gpt-4o")
                            
                        # 3. Wyświetlenie wyniku
                        st.session_state['generated_html'] = final_html
                        
                    except Exception as e:
                        st.error(f"Błąd API: {e}")

            # Wyświetlanie wyniku z sesji (żeby nie znikał)
            if 'generated_html' in st.session_state:
                final_html = st.session_state['generated_html']
                
                tab_preview, tab_code = st.tabs(["👁️ Podgląd", "💻 Kod HTML"])
                
                with tab_preview:
                    st.components.v1.html(final_html, height=800, scrolling=True)
                
                with tab_code:
                    st.code(final_html, language='html')
                
                file_name = f"newsletter_{date_str.replace(' ', '_')}.html"
                st.download_button("📥 POBIERZ GOTOWY HTML", final_html, file_name, "text/html")

if __name__ == "__main__":
    main()
