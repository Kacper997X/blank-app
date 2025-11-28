import streamlit as st
import json
import bcrypt
import pandas as pd
import numpy as np
import time
from openai import OpenAI
import re
from docx import Document
from docx.opc.constants import RELATIONSHIP_TYPE as RT

# ==========================================
# KONFIGURACJA I STAŁE
# ==========================================
st.set_page_config(page_title="SEO Macerator & Semantic Tool", layout="wide")

USER_DATA_PATH = 'users.json'
AVAILABLE_MODELS = ["gpt-4o-mini", "gpt-5-mini", "gpt-5-nano"]

# --- SZABLON HTML NEWSLETTERA ---
HTML_HEADER = """<!DOCTYPE html>
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
                            📢 Podsumowanie tygodnia – {date_str}
                        </td>
                    </tr>
"""

HTML_FOOTER = """
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
</html>
"""

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
# FUNKCJE LOGICZNE - TAB 3 (GENERATOR NEWSLETTERA)
# ==========================================

def clean_text_with_links(text):
    """
    Prosta funkcja, która zamienia:
    1. **tekst** na <b>tekst</b>
    2. Linki w formacie [tekst](url) na <a href="url" ...>tekst</a> (jeśli ktoś tak wpisze)
    3. Automatycznie podlinkowuje "http..." jeśli nie jest w tagu.
    """
    # Obsługa boldowania w stylu Markdown (**tekst**)
    text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text)
    
    # Obsługa linków w stylu Markdown [Tekst](url) - opcjonalnie, dla wygody
    text = re.sub(r'\[(.*?)\]\((.*?)\)', r'<a href="\2" style="color: #33D76F; font-weight: bold;">\1</a>', text)
    
    return text

def generate_newsletter_html(date_str, data):
    """Generuje pełny HTML na podstawie Twojego wzoru."""
    
    # --- 1. SEKCJE HTML (Zdefiniowane na podstawie wzoru) ---
    HEADER = f"""<!DOCTYPE html>
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
                            📢 Podsumowanie tygodnia{f' – {date_str}' if date_str else ''}
                        </td>
                    </tr>"""

    FOOTER = """
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

    # Funkcja generująca pojedynczą sekcję
    def make_section(title, icon, content_list, bg_color="#fafafa"):
        if not content_list:
            return ""
        
        items_html = ""
        for item in content_list:
            # Czyścimy i formatujemy tekst (boldy, linki)
            formatted_item = clean_text_with_links(item)
            items_html += f'<li style="margin-bottom: 10px;">{formatted_item}</li>\n'
            
        return f"""
                    <tr>
                        <td style="padding: 20px; background-color: {bg_color}; color: #000000;">
                            <b style="color: #33D76F;">{icon} {title}:</b><br><br>
                            <ul style="padding-left: 20px;">
                                {items_html}
                            </ul>
                        </td>
                    </tr>"""

    # --- 2. SKŁADANIE CAŁOŚCI ---
    body = ""
    # Breaking News (Tło #fafafa)
    body += make_section("Breaking News", "📢", data.get("breaking", []), bg_color="#fafafa")
    # Info ogólne (Tło #fafafa - wg wzoru, choć można zmienić na #ffffff dla kontrastu)
    body += make_section("Informacje ogólne", "📌", data.get("general", []), bg_color="#fafafa")
    # Produkty (Tło #ffffff - tu zmieniam dla kontrastu lub zgodnie z życzeniem)
    body += make_section("Produkty, usługi", "🛠", data.get("products", []), bg_color="#ffffff")
    # Klienci (Tło #fafafa)
    body += make_section("Projekty na aktualnych Klientach", "📊", data.get("clients", []), bg_color="#fafafa")
    # Przetargi (Tło #ffffff)
    body += make_section("Przetargi/prospekty", "📢", data.get("tenders", []), bg_color="#ffffff")

    return HEADER + body + FOOTER

def parse_docx(file):
    """
    Prosty parser, który czyta plik linia po linii i szuka nagłówków.
    """
    doc = Document(file)
    parsed_data = {
        "breaking": [],
        "general": [],
        "products": [],
        "clients": [],
        "tenders": []
    }
    
    current_section = None
    
    for para in doc.paragraphs:
        text = para.text.strip()
        if not text:
            continue
            
        text_lower = text.lower()
        
        # Wykrywanie sekcji (słowa kluczowe)
        if "breaking news" in text_lower:
            current_section = "breaking"
            continue
        elif "informacje ogólne" in text_lower:
            current_section = "general"
            continue
        elif "produkty" in text_lower and "usługi" in text_lower:
            current_section = "products"
            continue
        elif "projekty" in text_lower or "aktualnych klientach" in text_lower:
            current_section = "clients"
            continue
        elif "przetargi" in text_lower or "prospekty" in text_lower:
            current_section = "tenders"
            continue
            
        # Dodawanie treści
        if current_section:
            # Tutaj można by dodać logikę wyciągania linków z XML docx, 
            # ale najbezpieczniej pozwolić użytkownikowi edytować tekst w UI
            parsed_data[current_section].append(text)
            
    return parsed_data

# ==========================================
# FUNKCJE NEWSLETTERA (WORD + AI)
# ==========================================
def get_docx_text_with_links(doc):
    """Wyciąga tekst z Worda zachowując linki w formacie Markdown [text](url)."""
    full_text_list = []
    rels = doc.part.rels
    for paragraph in doc.paragraphs:
        if not paragraph.text.strip(): continue
        p_text = ""
        for child in paragraph._element:
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
        full_text_list.append(p_text)
    return full_text_list

def parse_docx_advanced(file):
    """
    Ulepszony parser: lepiej wykrywa sekcje i usuwa nagłówki z treści.
    """
    doc = Document(file)
    raw_lines = get_docx_text_with_links(doc)
    
    parsed_data = {
        "breaking": [],
        "general": [],
        "products": [],
        "clients": [],
        "tenders": []
    }
    
    current_section = None
    
    for line in raw_lines:
        text = line.strip()
        if not text:
            continue
            
        text_lower = text.lower()
        
        # Wykrywanie sekcji - słowa kluczowe
        # Używamy 'continue', żeby NIE dodawać linii nagłówka do treści sekcji
        if "breaking news" in text_lower:
            current_section = "breaking"
            continue
        elif "informacje ogólne" in text_lower:
            current_section = "general"
            continue
        elif "produkty" in text_lower and "usługi" in text_lower:
            current_section = "products"
            continue
        elif "projekty" in text_lower or "aktualnych klientach" in text_lower:
            current_section = "clients"
            continue
        elif "przetargi" in text_lower or "prospekty" in text_lower:
            current_section = "tenders"
            continue
        elif "stopka" in text_lower: # Zabezpieczenie przed wczytaniem stopki
            current_section = None
            continue
            
        # Dodawanie treści tylko jeśli jesteśmy w sekcji
        if current_section:
            parsed_data[current_section].append(text)
            
    return parsed_data

def ai_format_text(text_list, client, model="gpt-4o-mini"):
    """
    Ulepszony prompt: Lepiej radzi sobie z listami i pogrubieniami.
    """
    if not text_list:
        return ""
        
    input_text = "\n".join(text_list)
    
    system_prompt = """Jesteś redaktorem newslettera firmowego Performics. 
Twoim zadaniem jest sformatowanie surowego tekstu na listę HTML.

INSTRUKCJA:
1. Podziel tekst na logiczne punkty. Zazwyczaj jeden akapit lub myślnik w tekście źródłowym to jeden punkt listy <li>.
2. Zwróć wynik JAKO CZYSTY KOD HTML, składający się WYŁĄCZNIE z tagów <li>treść</li>. Nie dodawaj <ul> ani <html>.
3. Styl każdego punktu musi być taki: <li style="margin-bottom: 10px;">...</li>
4. ZACHOWAJ LINKI: Jeśli w tekście jest link Markdown [tekst](url), zamień go na: <a href="url" style="color: #33D76F; font-weight: bold; text-decoration: none;">tekst</a>.
5. FORMATOWANIE (BARDZO WAŻNE):
   - Wyszukaj i POGRUB (używając <b>...</b>) wszystkie:
     * Imiona i nazwiska pracowników (np. Jan Kowalski)
     * Nazwy marek i klientów (np. Media Markt, Samsung, Google)
     * Nazwy narzędzi (np. Yotta, FlowAI, Trade Desk)
     * Kluczowe daty (np. Black Friday, rok 2026, 4 grudnia)
     * Nazwy działów (np. SEO, SEM)
   
6. Nie dodawaj nagłówków sekcji (np. "Informacje ogólne:") do treści punktów.
7. Nie zmieniaj sensu zdań, popraw jedynie ewidentne błędy interpunkcyjne.
"""

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Oto surowy tekst sekcji do sformatowania:\n\n{input_text}"}
            ],
            temperature=0.1 # Niska temperatura, żeby AI nie wymyślało treści
        )
        # Czyszczenie odpowiedzi z markdownowych znaczników kodu, jeśli AI je doda
        content = response.choices[0].message.content.strip()
        content = content.replace("```html", "").replace("```", "").strip()
        content = content.replace("<ul>", "").replace("</ul>", "")
        return content
        
    except Exception as e:
        return f"<!-- Błąd AI: {e} -->\n" + "\n".join([f'<li style="margin-bottom: 10px;">{t}</li>' for t in text_list])

def create_section_html_raw(title, icon, html_content, bg_color="#ffffff"):
    if not html_content: return ""
    return f"""
        <tr><td style="padding: 20px; background-color: {bg_color}; color: #000000;">
        <b style="color: #33D76F;">{icon} {title}:</b><br><br>
        <ul style="padding-left: 20px;">{html_content}</ul></td></tr>"""

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
    tab1, tab2, tab3 = st.tabs(["📝 1. SEO Macerator", "🧠 2. Analiza Semantyczna", "📧 3. Generator Newslettera"])

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
    # ZAKŁADKA 2: ANALIZA SEMANTYCZNA (ZMODYFIKOWANA)
    # ==========================================
    with tab2:
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

# ==========================================
    # ZAKŁADKA 3: GENERATOR Z AI
    # ==========================================
    with tab3:
        st.header("Generator Newslettera HTML z AI")
        st.markdown("""
        **Instrukcja:**
        1. Wgraj plik Word (zachowamy linki).
        2. Kliknij **Wczytaj tekst**.
        3. Kliknij **Auto-Formatowanie AI**, aby GPT sformatowało listę i pogrubiło marki/nazwiska.
        """)

        # 1. Inicjalizacja stanu (żeby dane nie znikały przy klikaniu przycisków)
        if 'news_data' not in st.session_state:
            st.session_state['news_data'] = {
                "breaking": "",
                "general": "",
                "products": "",
                "clients": "",
                "tenders": ""
            }

        col_input, col_preview = st.columns([1, 1])

        with col_input:
            st.subheader("1. Treść i Edycja")
            uploaded_doc = st.file_uploader("Wgraj plik .docx", type="docx", key="news_doc")
            date_str = st.text_input("Data newslettera (np. 29 Listopada)", "29 Listopada")

            # --- KROK 1: Wczytanie z Worda ---
            if uploaded_doc and st.button("📂 1. Wczytaj tekst z pliku"):
                try:
                    parsed = parse_docx_advanced(uploaded_doc)
                    # Zapisujemy surowy tekst do stanu, łącząc linie znakiem nowej linii
                    for key in parsed:
                        st.session_state['news_data'][key] = "\n".join(parsed[key])
                    st.success("Tekst wczytany! Teraz możesz użyć AI do formatowania.")
                except Exception as e:
                    st.error(f"Błąd odczytu pliku: {e}")

            st.markdown("---")

            # --- KROK 2: AI Formatowanie ---
            if st.button("✨ 2. Auto-Formatowanie AI (Boldy & Linki)"):
                # Sprawdzamy czy jest jakikolwiek tekst do przerobienia
                if not any(st.session_state['news_data'].values()):
                    st.warning("Najpierw wczytaj plik Word lub wpisz tekst ręcznie!")
                else:
                    try:
                        api_key = st.secrets["OPENAI_API_KEY"]
                        client = OpenAI(api_key=api_key)

                        with st.status("AI pracuje nad tekstem...", expanded=True):
                            # Mapowanie kluczy na nazwy wyświetlane (dla estetyki paska postępu)
                            sections_map = {
                                'breaking': "Breaking News",
                                'general': "Informacje ogólne",
                                'products': "Produkty",
                                'clients': "Klienci",
                                'tenders': "Przetargi"
                            }

                            for key, name in sections_map.items():
                                content = st.session_state['news_data'][key]
                                if content.strip(): # Tylko jeśli sekcja nie jest pusta
                                    st.write(f"Formatowanie sekcji: {name}...")
                                    # Dzielimy na linie, żeby wysłać jako listę do funkcji
                                    formatted_html = ai_format_text(content.split('\n'), client)
                                    st.session_state['news_data'][key] = formatted_html
                            
                        st.success("Gotowe! AI sformatowało tekst, dodało <b> i poprawiło linki.")
                    
                    except Exception as e:
                        st.error(f"Błąd API OpenAI: {e}")
                        st.info("Sprawdź czy masz poprawny klucz API w pliku secrets.")

            st.markdown("### Edycja (HTML)")
            st.caption("Możesz tutaj ręcznie poprawić to, co wygenerowało AI.")

            # Pola tekstowe edytują bezpośrednio stan sesji (value=st.session_state...)
            st.session_state['news_data']['breaking'] = st.text_area("Breaking News", value=st.session_state['news_data']['breaking'], height=150)
            st.session_state['news_data']['general'] = st.text_area("Informacje ogólne", value=st.session_state['news_data']['general'], height=150)
            st.session_state['news_data']['products'] = st.text_area("Produkty, usługi", value=st.session_state['news_data']['products'], height=150)
            st.session_state['news_data']['clients'] = st.text_area("Projekty na klientach", value=st.session_state['news_data']['clients'], height=200)
            st.session_state['news_data']['tenders'] = st.text_area("Przetargi/prospekty", value=st.session_state['news_data']['tenders'], height=150)

        with col_preview:
            st.subheader("2. Podgląd HTML")

            # Składanie finalnego HTML z kawałków
            full_html = HTML_HEADER.format(date_str=date_str)
            # Używamy create_section_html_raw, bo tekst jest już HTML-em z tagami <li> i <b>
            full_html += create_section_html_raw("Breaking News", "📢", st.session_state['news_data']['breaking'], "#fafafa")
            full_html += create_section_html_raw("Informacje ogólne", "📌", st.session_state['news_data']['general'], "#fafafa")
            full_html += create_section_html_raw("Produkty, usługi", "🛠", st.session_state['news_data']['products'], "#ffffff")
            full_html += create_section_html_raw("Projekty na aktualnych Klientach", "📊", st.session_state['news_data']['clients'], "#fafafa")
            full_html += create_section_html_raw("Przetargi/prospekty", "📢", st.session_state['news_data']['tenders'], "#ffffff")
            full_html += HTML_FOOTER

            # Zakładki podglądu
            subtab_preview, subtab_code = st.tabs(["👁️ Render", "💻 Kod źródłowy"])

            with subtab_preview:
                st.components.v1.html(full_html, height=800, scrolling=True)

            with subtab_code:
                st.code(full_html, language='html')

            # Przycisk pobierania
            file_name_clean = f"newsletter_{date_str.replace(' ', '_')}.html"
            st.download_button(
                label="📥 POBIERZ GOTOWY PLIK HTML",
                data=full_html,
                file_name=file_name_clean,
                mime="text/html"
            )

if __name__ == "__main__":
    main()
