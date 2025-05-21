import streamlit as st
import json
import bcrypt
import pandas as pd
import time
from openai import OpenAI
import concurrent.futures

USER_DATA_PATH = 'users.json'
AVAILABLE_MODELS = ["gpt-4.1-mini"]

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
    st.title("Logowanie")
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

def get_csv_template():
    df = pd.DataFrame({'input': ['przykładowa fraza', 'https://example.com']})
    return df

def process_row(row_dict, system_prompt, user_prompt, model, client):
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt.format(**row_dict)},
            ],
            temperature=0.7,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"Błąd: {e}"

def escape_braces(s):
    """Zamienia { na {{ i } na }} w stringu, by uniknąć KeyError przy .format()"""
    return str(s).replace('{', '{{').replace('}', '}}')

def process_rows_in_batches(df, batch_size, system_prompt, user_prompt, model, client):
    import json
    import time
    results = []
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
                batch_result = json.loads(content)
                # batch_result powinien być dict: {fraza: kategoria}
                for keyword in keywords:
                    results.append(batch_result.get(keyword, "BRAK ODPOWIEDZI"))
            except json.JSONDecodeError:
                # Odpowiedź nie jest poprawnym JSON-em
                for _ in keywords:
                    results.append(f"Błąd: Niepoprawny JSON: {content}")
        except Exception as e:
            for _ in keywords:
                results.append(f"Błąd: {e}")
        time.sleep(1)  # By nie przekroczyć limitów API
    return results

def main():
    if 'logged_in' not in st.session_state:
        st.session_state['logged_in'] = False
    if 'username' not in st.session_state:
        st.session_state['username'] = None

    users = load_users()

    if not st.session_state['logged_in']:
        login(users)
        st.stop()
    else:
        st.title(f"SEO Macerator")
        if st.button("Wyloguj"):
            logout()

        st.subheader("1. Pobierz wzór pliku CSV")
        st.download_button(
            label="Pobierz wzór pliku CSV",
            data=get_csv_template().to_csv(index=False).encode('utf-8'),
            file_name="wzor.csv",
            mime="text/csv"
        )

 # --- PRZYKŁADOWE PROMPTY JAKO PRZYCISKI ---
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

        # Wyświetl przyciski
        for i, example in enumerate(prompt_examples):
            if st.button(example["title"]):
                st.session_state['system_prompt'] = example["system"]
                st.session_state['user_prompt'] = example["user"]

        st.subheader("2. Wgraj plik CSV")
        uploaded_file = st.file_uploader("Prześlij plik CSV (musi zawierać kolumnę 'input')", type=["csv"])

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
            placeholder="Wpisz prompt systemowy..."
        )
        user_prompt = st.text_area(
            "Prompt użytkownika (np. 'Stwórz opis dla: {input}')",
            value=st.session_state.get('user_prompt', ''),
            placeholder="Wpisz prompt użytkownika...",
        )
        model = st.selectbox("Wybierz model AI", AVAILABLE_MODELS)
        batch_size = st.number_input(
    "Ile wierszy przetwarzać jednocześnie?",
    min_value=1,
    max_value=50,
    value=5,
    help="Im większa liczba, tym szybciej przetworzysz plik, ale dokładność odpowiedzi AI może być niższa (model może popełniać więcej błędów na dużych batchach)."
)

        if st.button("Uruchom przetwarzanie") and df is not None:
            if not system_prompt or not user_prompt:
                st.error("Uzupełnij oba prompty.")
            else:
                st.info("Przetwarzanie... To może chwilę potrwać.")
                client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
                results = process_rows_in_batches(df, batch_size, system_prompt, user_prompt, model, client)
                df['wynik'] = results
                st.success("Gotowe! Oto wyniki:")
                st.write(df)
                st.download_button(
                    label="Pobierz wyniki jako CSV",
                    data=df.to_csv(index=False, encoding="utf-8-sig").encode('utf-8-sig'),
                    file_name="wyniki.csv",
                    mime="text/csv"
                )

if __name__ == "__main__":
    main()
