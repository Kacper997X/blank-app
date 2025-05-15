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

def process_rows_in_batches(df, batch_size, system_prompt, user_prompt, model, client):
    results = []
    for i in range(0, len(df), batch_size):
        batch = df.iloc[i:i+batch_size]
        with concurrent.futures.ThreadPoolExecutor() as executor:
            batch_results = list(executor.map(
                lambda row: process_row(row, system_prompt, user_prompt, model, client),
                batch.to_dict('records')
            ))
        results.extend(batch_results)
        time.sleep(1)
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
        st.title(f"Witaj, {st.session_state['username']}!")
        if st.button("Wyloguj"):
            logout()

        st.header("SEO Macerator")

        st.subheader("1. Pobierz wzór pliku CSV")
        st.download_button(
            label="Pobierz wzór pliku CSV",
            data=get_csv_template().to_csv(index=False).encode('utf-8'),
            file_name="wzor.csv",
            mime="text/csv"
        )

        st.subheader("2. Wgraj plik CSV")
        uploaded_file = st.file_uploader("Prześlij plik CSV (musi zawierać kolumnę 'input')", type=["csv"])

        df = None
        if uploaded_file is not None:
            df = pd.read_csv(uploaded_file)
            st.write("Nagłówki pliku CSV:", df.columns.tolist())
            if 'input' not in df.columns:
                st.error("Plik CSV musi zawierać kolumnę o nazwie 'input'.")
                df = None

        st.subheader("3. Ustaw prompty i wybierz model")
        st.info("W promptach używaj {input} aby odwołać się do wartości z kolumny 'input'.")
        system_prompt = st.text_area("Prompt systemowy", placeholder="Wpisz prompt systemowy...")
        user_prompt = st.text_area(
            "Prompt użytkownika (np. 'Stwórz opis dla: {input}')",
            placeholder="Wpisz prompt użytkownika..."
        )
        model = st.selectbox("Wybierz model AI", AVAILABLE_MODELS)
        batch_size = st.number_input("Ile wierszy przetwarzać jednocześnie?", min_value=1, max_value=50, value=5)

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
                    data=df.to_csv(index=False).encode('utf-8'),
                    file_name="wyniki.csv",
                    mime="text/csv"
                )

if __name__ == "__main__":
    main()
