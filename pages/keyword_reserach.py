import streamlit as st
import requests
import json
import bcrypt
import logging

# --- KONFIGURACJA LOGOWANIA ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# 1. KONFIGURACJA STRONY
st.set_page_config(page_title="Senuto Final Check", layout="wide")

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
    st.title("🔐 Logowanie do Panelu Testowego")
    username = st.text_input("Nazwa użytkownika")
    password = st.text_input("Hasło", type="password")
    
    if st.button("Zaloguj"):
        if username in users and check_password(users[username], password):
            st.session_state['logged_in'] = True
            st.session_state['username'] = username
            st.success("Zalogowano pomyślnie!")
            logger.info(f"Użytkownik {username} zalogował się do modułu Senuto.")
            st.rerun()
        else:
            st.error("Nieprawidłowa nazwa użytkownika lub hasło")
            logger.warning(f"Nieudana próba logowania jako: {username}")

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

# ==========================================
# APLIKACJA WŁAŚCIWA (Widoczna po zalogowaniu)
# ==========================================

st.title("🎯 Ostateczny Test Endpointów")

# --- INPUT TOKENA ---
api_token = st.text_input("Wklej tutaj swój Bearer Token:", type="password")

if not api_token:
    st.warning("Potrzebujesz tokena, żeby ruszyć dalej.")
    st.stop()

headers = {
    "Authorization": f"Bearer {api_token}",
    "Content-Type": "application/json"
}

st.divider()

col1, col2 = st.columns(2)

# --- TEST A: Prosty Explorer (Działa w starszych wersjach API) ---
with col1:
    st.header("Test A: Prosty Explorer")
    st.markdown("`POST /api/keywords/explorer/related`")
    
    if st.button("Uruchom Test A"):
        logger.info("Uruchomiono Test A")
        url = "https://api.senuto.com/api/keywords/explorer/related"
        payload = {"query": "crm", "country_id": 1, "limit": 5}
        
        try:
            r = requests.post(url, headers=headers, json=payload)
            st.write(f"Status: **{r.status_code}**")
            if r.status_code == 200:
                st.success("DZIAŁA! 🟢")
                st.json(r.json())
            else:
                st.error("Nie działa 🔴")
                st.text(r.text)
                logger.error(f"Błąd Test A: {r.status_code} - {r.text}")
        except Exception as e:
            st.error(f"Błąd: {e}")
            logger.error(f"Wyjątek w Test A: {e}")

# --- TEST B: Raporty Analityczne (Z Twojego cURL) ---
with col2:
    st.header("Test B: GetKeywords (Advanced)")
    st.markdown("`POST .../keywords_analysis/reports/keywords/getKeywords`")
    st.info("To jest ten endpoint z Twojej dokumentacji cURL.")
    
    if st.button("Uruchom Test B"):
        logger.info("Uruchomiono Test B")
        url = "https://api.senuto.com/api/keywords_analysis/reports/keywords/getKeywords"
        
        # Payload dokładnie taki jak w Twoim cURL
        payload = {
            "parameters": [
                {
                    "data_fetch_mode": "keyword",
                    "value": ["crm"]
                }
            ],
            "country_id": 1,
            "match_mode": "wide",
            "filtering": [
                {
                    "filters": []
                }
            ]
        }
        
        try:
            r = requests.post(url, headers=headers, json=payload)
            st.write(f"Status: **{r.status_code}**")
            
            if r.status_code == 200:
                st.success("DZIAŁA! 🟢")
                st.write("Oto struktura odpowiedzi (skopiuj ją, jeśli działa!):")
                st.json(r.json())
            elif r.status_code == 403:
                st.warning("403 Forbidden - Token działa, ale nie masz wykupionego tego modułu w planie.")
                logger.warning("Test B: 403 Forbidden")
            else:
                st.error("Nie działa 🔴")
                st.text(r.text)
                logger.error(f"Błąd Test B: {r.status_code} - {r.text}")
        except Exception as e:
            st.error(f"Błąd: {e}")
            logger.error(f"Wyjątek w Test B: {e}")
