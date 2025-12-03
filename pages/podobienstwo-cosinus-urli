import streamlit as st
import requests
import json
import bcrypt
import logging
import pandas as pd
import numpy as np
import seaborn as sns
import matplotlib.pyplot as plt
from bs4 import BeautifulSoup
from openai import OpenAI
from sklearn.metrics.pairwise import cosine_similarity
import time
import os

# --- KONFIGURACJA LOGOWANIA (Z Twojego działającego skryptu) ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# 1. KONFIGURACJA STRONY
st.set_page_config(
    page_title="SEO Matrix Analyzer", 
    page_icon="🕵️",
    layout="wide"
)

# ==========================================
# KONFIGURACJA UWIERZYTELNIANIA (Z Twojego działającego skryptu)
# ==========================================
USER_DATA_PATH = 'users.json'

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
    st.title("🔐 Logowanie do SEO Matrix")
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
    # Czyścimy dane Matrixa przy wylogowaniu
    keys_to_remove = ['analysis_done', 'matrix', 'valid_urls_data']
    for key in keys_to_remove:
        if key in st.session_state:
            del st.session_state[key]
    st.rerun()

# ==========================================
# LOGIKA LOGOWANIA (GŁÓWNY PRZEPŁYW)
# ==========================================

if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False

users = load_users()

if not st.session_state['logged_in']:
    login(users)
    st.stop()

# --- PASEK BOCZNY (SIDEBAR) ---
st.sidebar.title(f"👤 {st.session_state['username']}")
if st.sidebar.button("Wyloguj"):
    logout()

st.sidebar.markdown("---")
st.sidebar.header("⚙️ Konfiguracja Matrixa")

# Klucz API
api_key = st.sidebar.text_input("OpenAI API Key", type="password")
if not api_key:
    try:
        api_key = st.secrets["OPENAI_API_KEY"]
    except:
        api_key = os.environ.get("OPENAI_API_KEY")

# Suwak
threshold = st.sidebar.slider("Próg podobieństwa", 0.0, 1.0, 0.5, 0.05)


# ==========================================
# FUNKCJE MATRIXA (BACKEND)
# ==========================================

@st.cache_data(show_spinner=False)
def extract_clean_text(url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code != 200: return None
        soup = BeautifulSoup(response.content, 'html.parser')
        for element in soup(["script", "style", "nav", "footer", "header", "form"]):
            element.decompose()
        text = ' '.join(soup.get_text(separator=' ').split())
        return text[:20000] if len(text) > 100 else None
    except Exception as e:
        logger.error(f"Błąd url {url}: {e}")
        return None

def get_embedding(text, client):
    text = text.replace("\n", " ")
    return client.embeddings.create(input=[text], model="text-embedding-3-large").data[0].embedding

def perform_analysis(url_list_raw, api_key_val):
    client = OpenAI(api_key=api_key_val)
    urls = [line.strip() for line in url_list_raw.split('\n') if line.strip()]
    
    if not urls: return None

    progress_bar = st.progress(0)
    data_list = []
    embeddings = []
    
    for i, url in enumerate(urls):
        text = extract_clean_text(url)
        if text:
            try:
                emb = get_embedding(text, client)
                embeddings.append(emb)
                data_list.append({'url': url, 'short_name': url.split('/')[-1][:25]})
            except Exception as e:
                st.warning(f"Błąd API: {e}")
        progress_bar.progress((i + 1) / len(urls))
        time.sleep(0.05)

    if len(embeddings) < 2:
        st.error("Za mało danych.")
        return None

    matrix = cosine_similarity(embeddings)
    return {"matrix": matrix, "data": data_list}

# ==========================================
# APLIKACJA WŁAŚCIWA (MATRIX)
# ==========================================

st.title("🕵️ Masowa Analiza Podobieństwa (Matrix)")
st.markdown("To jest moduł analizy kanibalizacji (uruchomiony na silniku Senuto Checkera).")

url_input = st.text_area(
    "Lista URLi (jeden pod drugim):", 
    height=200, 
    placeholder="https://site.pl/a\nhttps://site.pl/b"
)

if st.button("🚀 Uruchom Analizę", type="primary"):
    if not url_input.strip():
        st.warning("Pusta lista URLi.")
    elif not api_key:
        st.error("Brak klucza API OpenAI (ustaw w Sidebarze).")
    else:
        with st.spinner("Przetwarzanie..."):
            result = perform_analysis(url_input, api_key)
            if result:
                st.session_state['analysis_done'] = True
                st.session_state['matrix'] = result['matrix']
                st.session_state['valid_urls_data'] = result['data']

# --- WYNIKI ---
if st.session_state.get('analysis_done'):
    matrix = st.session_state['matrix']
    data = st.session_state['valid_urls_data']
    labels = [d['short_name'] for d in data]
    urls = [d['url'] for d in data]

    st.divider()
    
    # 1. Heatmapa
    st.subheader("1. Mapa Ciepła")
    fig, ax = plt.subplots(figsize=(10, 8))
    sns.heatmap(matrix, xticklabels=labels, yticklabels=labels, cmap="Greens", annot=True, fmt=".2f")
    st.pyplot(fig)

    # 2. Tabela
    st.subheader(f"2. Pary > {threshold}")
    pairs = []
    for i in range(len(matrix)):
        for j in range(i+1, len(matrix)):
            if matrix[i][j] >= threshold:
                pairs.append([urls[i], urls[j], matrix[i][j]])
    
    if pairs:
        df = pd.DataFrame(pairs, columns=["A", "B", "Score"]).sort_values("Score", ascending=False)
        st.dataframe(df.style.background_gradient(cmap="Greens"))
    else:
        st.info("Brak duplikatów.")
