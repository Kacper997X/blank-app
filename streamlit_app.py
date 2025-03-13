import streamlit as st
import json
import bcrypt

# Ukryj sidebar, jeśli użytkownik nie jest zalogowany
if not st.session_state.get('logged_in'):
    st.set_page_config(initial_sidebar_state="collapsed")

# Ścieżka do pliku z danymi użytkowników
USER_DATA_PATH = 'users.json'

# Funkcja do weryfikacji hasła
def check_password(hashed_password, user_password):
    return bcrypt.checkpw(user_password.encode('utf-8'), hashed_password.encode('utf-8'))

# Funkcja do hashowania hasła
def hash_password(password):
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

# Funkcja do wczytania danych użytkowników
def load_users():
    try:
        with open(USER_DATA_PATH, 'r') as file:
            users = json.load(file)
        return users['users']
    except FileNotFoundError:
        return {}

# Funkcja do zapisywania danych użytkowników
def save_users(users):
    with open(USER_DATA_PATH, 'w') as file:
        json.dump({"users": users}, file, indent=4)

# Funkcja do logowania
def login(users):
    st.title("Logowanie")
    username = st.text_input("Nazwa użytkownika")
    password = st.text_input("Hasło", type="password")

    if st.button("Zaloguj"):
        if username in users and check_password(users[username], password):
            st.session_state['logged_in'] = True
            st.session_state['username'] = username
            st.success("Zalogowano pomyślnie!")
            st.experimental_set_query_params(logged_in=True)  # Dodaj parametr do URL
            st.rerun()  # Przeładuj aplikację
        else:
            st.error("Nieprawidłowa nazwa użytkownika lub hasło")

# Funkcja do wylogowania
def logout():
    st.session_state['logged_in'] = False
    st.session_state['username'] = None
    st.success("Wylogowano pomyślnie!")
    st.experimental_set_query_params(logged_in=False)  # Usuń parametr z URL
    st.rerun()  # Przeładuj aplikację

# Funkcja do tworzenia kafelków
def create_tile(icon, title, description, link):
    st.markdown(
        f"""
        <a href="{link}" style="text-decoration: none; color: inherit;">
            <div style="
                padding: 20px;
                border: 1px solid #e0e0e0;
                border-radius: 10px;
                text-align: center;
                background-color: #f9f9f9;
                box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1);
                transition: transform 0.2s;
                margin: 10px;
            ">
                <div style="font-size: 30px;">{icon}</div>
                <h3>{title}</h3>
                <p>{description}</p>
            </div>
        </a>
        """,
        unsafe_allow_html=True,
    )

# Główna funkcja aplikacji
def main():
    # Inicjalizacja stanu sesji
    if 'logged_in' not in st.session_state:
        st.session_state['logged_in'] = False
    if 'username' not in st.session_state:
        st.session_state['username'] = None

    # Wczytanie danych użytkowników
    users = load_users()

    # Logowanie
    if not st.session_state['logged_in']:
        login(users)
        st.stop()  # Zatrzymaj aplikację, jeśli użytkownik nie jest zalogowany
    else:
        st.title(f"Witaj, {st.session_state['username']}!")
        if st.button("Wyloguj"):
            logout()

        # Główna zawartość aplikacji
        st.title("Witaj w Twojej Aplikacji!")
        st.write("Wybierz moduł, aby rozpocząć:")

        # Tworzenie siatki kafelków (2 w rzędzie)
        col1, col2 = st.columns(2)
        with col1:
            create_tile("📊", "ALT Generator", "Generuj opisy ALT dla obrazów.", "/ALT_Generator")
            create_tile("🌐", "Domen Kategoryzator", "Kategoryzuj domeny.", "/Domen_Kategoryzator")
            create_tile("🔑", "Słów Kluczowych Kategoryzator", "Kategoryzuj słowa kluczowe.", "/Slowa_Kluczowe_Kategoryzator")
        with col2:
            create_tile("🔗", "URL Kategoryzator", "Kategoryzuj adresy URL.", "/URL_Kategoryzator")
            create_tile("🎨", "Odbrandawiacz", "Usuwaj branding z treści.", "/Odbrandawiacz")
            create_tile("🤖", "Henkins", "Automatyzuj zadania z Henkinsem.", "/Henkins")

if __name__ == "__main__":
    main()
