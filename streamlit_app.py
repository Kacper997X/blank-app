import streamlit as st
import json
import bcrypt
import pandas as pd
import time
import numpy as np
from openai import OpenAI
import concurrent.futures
import io

# ==========================================
# KONFIGURACJA I STAŁE
# ==========================================
USER_DATA_PATH = 'users.json'
AVAILABLE_MODELS = ["gpt-4o-mini", "gpt-3.5-turbo"] # Zaktualizowałem nazwy modeli na poprawne

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
    st.title("🔐 Logowanie do SEO Macerator")
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
# FUNKCJE: GENERATOR (TAB 1)
# ==========================================
def get_csv_template():
    df = pd.DataFrame({'input': ['przykładowa fraza', 'https://example.com']})
    return df

def escape_braces(s):
    """Zamienia { na {{ i } na }} w stringu, by uniknąć KeyError przy .format()"""
    return str(s).replace('{', '{{').replace('}', '}}')

def process_rows_in_batches(df, batch_size, system_prompt, user_prompt, model, client):
    results = []
    # Pasek postępu dla generatora
    progress_bar = st.progress(0, text="Rozpoczynam generowanie...")
    total_rows = len(df)
    
    for i in range(0, total_rows, batch_size):
        batch = df.iloc[i:i+batch_size]
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
            
            if not content:
                for _ in keywords:
                    results.append("Błąd: Pusta odpowiedź AI")
                continue
            
            try:
                # Próba sparsowania JSON
                batch_result = json.loads(content)
                if isinstance(batch_result, dict):
                     for keyword in keywords:
                        # Odkręcamy escape braces dla klucza słownika, jeśli to konieczne, 
                        # ale tutaj API zazwyczaj zwraca czysty tekst.
                        # Spróbujmy znaleźć dopasowanie
                        key_unescaped = keyword.replace('{{', '{').replace('}}', '}')
                        val = batch_result.get(key_unescaped) or batch_result.get(keyword, "BRAK ODPOWIEDZI")
                        results.append(val)
                else:
                     # Jeśli to nie dict, tylko np. lista, lub string
                     results.extend([str(content)] * len(keywords))

            except json.JSONDecodeError:
                # Fallback jeśli model nie zwrócił JSONa tylko tekst
                for _ in keywords:
                    results.append(f"Błąd JSON/Tekst: {content[:50]}...")
                    
        except Exception as e:
            for _ in keywords:
                results.append(f"Błąd API: {e}")
        
        # Aktualizacja paska
        current_progress = min((i + batch_size) / total_rows, 1.0)
        progress_bar.progress(current_progress, text=f"Przetworzono {min(i + batch_size, total_rows)} z {total_rows}")
        
        time.sleep(0.5) # Lekkie opóźnienie dla rate limits
    
    progress_bar.empty()
    return results

# ==========================================
# FUNKCJE: EMBEDDINGI (TAB 2)
# ==========================================
def get_embedding(text, client):
    """Pobiera wektor z OpenAI (text-embedding-3-large)."""
    if not isinstance(text, str) or not text.strip():
        return np.zeros(3072)
    text = text.replace("\n", " ")
    try:
        return client.embeddings.create(
            input=[text],
            model="text-embedding-3-large"
        ).data[0].embedding
    except Exception as e:
        return np.zeros(3072)

def cosine_similarity(a, b):
    if np.all(a == 0) or np.all(b == 0):
        return 0.0
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))

# ==========================================
# GŁÓWNA APLIKACJA
# ==========================================
def main():
    # Inicjalizacja stanu sesji
    if 'logged_in' not in st.session_state:
        st.session_state['logged_in'] = False
    if 'username' not in st.session_state:
        st.session_state['username'] = None

    # Wczytanie użytkowników
    users = load_users()

    # Ekran logowania
    if not st.session_state['logged_in']:
        login(users)
        st.stop()
    
    # === APLIKACJA PO ZALOGOWANIU ===
    st.sidebar.title(f"Witaj, {st.session_state['username']}!")
    if st.sidebar.button("Wyloguj"):
        logout()

    st.title("🛠️ SEO Macerator")

    # Tworzymy zakładki dla różnych narzędzi
    tab1, tab2 = st.tabs(["📝 1. Generator Treści (GPT)", "🧠 2. Analiza Semantyczna (Embeddingi)"])

    # ---------------------------------------------------------
    # TAB 1: GENERATOR TREŚCI (Twój pierwotny kod)
    # ---------------------------------------------------------
    with tab1:
        st.header("Generator / Klasyfikator Fraz")
        
        col1, col2 = st.columns([1, 2])
        
        with col1:
            st.subheader("Ustawienia")
            st.download_button(
                label="📥 Pobierz wzór CSV",
                data=get_csv_template().to_csv(index=False).encode('utf-8'),
                file_name="wzor_generator.csv",
                mime="text/csv"
            )
            uploaded_file = st.file_uploader("Wgraj plik CSV (kolumna 'input')", type=["csv"], key="uploader_gen")
            model = st.selectbox("Model", AVAILABLE_MODELS, key="model_gen")
            batch_size = st.number_input("Batch size", 1, 50, 5, key="batch_gen")

        with col2:
            st.subheader("Prompty")
            
            # Przykłady promptów (skrócone dla czytelności kodu, można tu wkleić Twoją pełną listę)
            prompt_examples = [
                {"title": "Kategoryzacja (JSON)", "system": "Jesteś ekspertem SEO...", "user": "Sklasyfikuj w formacie JSON: {input}"},
                {"title": "Tłumaczenie", "system": "Jesteś tłumaczem...", "user": "Przetłumacz na JSON: {input}"}
            ]
            
            selected_example = st.selectbox("Wybierz gotowy szablon (opcjonalnie)", ["-- Własny --"] + [p['title'] for p in prompt_examples])
            
            if selected_example != "-- Własny --":
                ex = next(p for p in prompt_examples if p['title'] == selected_example)
                st.session_state['sys_prompt_val'] = ex['system']
                st.session_state['user_prompt_val'] = ex['user']

            system_prompt = st.text_area("System Prompt", value=st.session_state.get('sys_prompt_val', ''), height=150)
            user_prompt = st.text_area("User Prompt", value=st.session_state.get('user_prompt_val', ''), height=100)

        # Uruchomienie generatora
        if st.button("🚀 Uruchom Generator", type="primary"):
            if uploaded_file and system_prompt and user_prompt:
                try:
                    df = pd.read_csv(uploaded_file)
                    if 'input' not in df.columns:
                        st.error("Brak kolumny 'input'!")
                    else:
                        client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
                        results = process_rows_in_batches(df, batch_size, system_prompt, user_prompt, model, client)
                        df['wynik'] = results
                        st.success("Zakończono!")
                        st.dataframe(df.head())
                        st.download_button("Pobierz wyniki", df.to_csv(index=False).encode('utf-8'), "wyniki_generator.csv")
                except Exception as e:
                    st.error(f"Błąd: {e}")
            else:
                st.warning("Wgraj plik i uzupełnij prompty.")

    # ---------------------------------------------------------
    # TAB 2: ANALIZA SEMANTYCZNA (Kod z Etapu 2)
    # ---------------------------------------------------------
    with tab2:
        st.header("Analiza Dopasowania Semantycznego")
        st.info("To narzędzie porównuje wektory frazy kluczowej z tytułem i opisem meta.")

        uploaded_sem = st.file_uploader("Wgraj plik CSV (wymagane: 'generated_keyword', 'meta title', 'meta description')", type=['csv'], key="uploader_sem")

        if uploaded_sem is not None:
            try:
                # Wczytujemy separatorem średnik (tak jak w Twoim skrypcie Etapu 2) lub przecinkiem
                # Spróbujmy najpierw automatycznie wykryć lub założyć średnik, jeśli to export z poprzedniego etapu
                df_sem = pd.read_csv(uploaded_sem, sep=None, engine='python')
                
                required_cols = ['generated_keyword', 'meta title', 'meta description']
                missing = [c for c in required_cols if c not in df_sem.columns]

                if missing:
                    st.error(f"❌ Brakuje kolumn: {missing}. Sprawdź separator (zalecany średnik lub przecinek).")
                else:
                    st.success(f"✅ Wczytano {len(df_sem)} wierszy.")
                    
                    if st.button("🚀 Oblicz dopasowanie (Cosinus)", key="btn_sem"):
                        client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
                        
                        progress_bar = st.progress(0, text="Generowanie embeddingów...")
                        scores_title = []
                        scores_desc = []
                        
                        for i, row in df_sem.iterrows():
                            # 1. Embeddingi
                            vec_kw = get_embedding(str(row['generated_keyword']), client)
                            vec_title = get_embedding(str(row['meta title']), client)
                            vec_desc = get_embedding(str(row['meta description']), client)

                            # 2. Podobieństwo
                            scores_title.append(round(cosine_similarity(vec_kw, vec_title), 4))
                            scores_desc.append(round(cosine_similarity(vec_kw, vec_desc), 4))
                            
                            # Pasek
                            progress_bar.progress((i + 1) / len(df_sem))

                        df_sem['score_title_match'] = scores_title
                        df_sem['score_desc_match'] = scores_desc
                        
                        # Sortowanie
                        df_sem = df_sem.sort_values(by='score_title_match', ascending=True)
                        
                        st.success("Gotowe!")
                        st.write("Najgorsze dopasowania (wymagają uwagi):")
                        st.dataframe(df_sem[['generated_keyword', 'meta title', 'score_title_match']].head(10))
                        
                        st.download_button(
                            "📥 Pobierz Raport Semantyczny",
                            df_sem.to_csv(sep=';', index=False).encode('utf-8'),
                            f"RAPORT_SEMANTYCZNY_{uploaded_sem.name}",
                            "text/csv"
                        )

            except Exception as e:
                st.error(f"Błąd pliku: {e}")

if __name__ == "__main__":
    main()
