import streamlit as st
import requests
import json

st.set_page_config(page_title="Senuto Lab v2", layout="wide")
st.title("🧪 Laboratorium API Senuto: Generator Tokena")

# Zakładki: Najpierw zdobywamy token, potem testujemy
tab1, tab2 = st.tabs(["🔑 1. Wygeneruj Prawdziwy Token", "🔬 2. Testuj Endpointy"])

# --- ZAKŁADKA 1: GENEROWANIE TOKENA ---
with tab1:
    st.header("Generowanie Bearer Token")
    st.markdown("""
    Tokeny integracyjne (np. do Data Studio) często nie działają w czystym API. 
    Zgodnie z dokumentacją, musimy wymienić Twój login i hasło na **Bearer Token**.
    """)
    
    col_auth1, col_auth2 = st.columns(2)
    with col_auth1:
        email = st.text_input("Twój Email do Senuto")
    with col_auth2:
        password = st.text_input("Twoje Hasło do Senuto", type="password")
        
    if st.button("🔄 Pobierz Bearer Token"):
        if not email or not password:
            st.error("Podaj email i hasło!")
        else:
            url = "https://api.senuto.com/api/users/token"
            # Zgodnie z dokumentacją Senuto (Form Data lub JSON)
            payload = {
                "email": email,
                "password": password
            }
            
            try:
                with st.spinner("Logowanie do Senuto..."):
                    response = requests.post(url, json=payload)
                
                if response.status_code == 200:
                    data = response.json()
                    if data.get('success'):
                        token = data['data']['token']
                        st.success("✅ SUKCES! Oto Twój Bearer Token:")
                        st.code(token, language="text")
                        st.info("👇 Skopiuj ten token i wklej go w zakładce 'Testuj Endpointy' lub zapisz w secrets!")
                        
                        # Zapisz w sesji dla wygody
                        st.session_state['generated_token'] = token
                    else:
                        st.error("Logowanie nieudane (Success: false)")
                        st.json(data)
                else:
                    st.error(f"Błąd logowania: {response.status_code}")
                    st.text(response.text)
            except Exception as e:
                st.error(f"Błąd połączenia: {e}")

# --- ZAKŁADKA 2: TESTOWANIE ---
with tab2:
    st.header("Testowanie Endpointów")
    
    # Automatycznie wpisz wygenerowany token, jeśli istnieje
    default_token = st.session_state.get('generated_token', st.secrets.get("SENUTO_API_KEY", ""))
    api_token = st.text_input("Bearer Token (Wklej tu ten wygenerowany)", value=default_token, type="password")
    
    st.divider()
    
    st.markdown("### 🎯 Sprawdźmy Keyword Explorer")
    
    col_url, col_method = st.columns([3, 1])
    with col_url:
        # Najbardziej prawdopodobny endpoint wg dokumentacji
        endpoint = st.text_input("Endpoint URL", "https://api.senuto.com/api/keywords/explorer/related")
    with col_method:
        method = st.selectbox("Metoda", ["POST", "GET"])
        
    body_str = st.text_area("Body JSON", value='{\n  "query": "crm",\n  "country_id": 1,\n  "limit": 5\n}', height=150)
    
    if st.button("🚀 Wyślij Zapytanie Testowe"):
        if not api_token:
            st.error("Brak tokena!")
        else:
            headers = {
                "Authorization": f"Bearer {api_token}",
                "Content-Type": "application/json"
            }
            
            try:
                if method == "GET":
                    r = requests.get(endpoint, headers=headers)
                else:
                    json_data = json.loads(body_str)
                    r = requests.post(endpoint, headers=headers, json=json_data)
                
                st.write(f"Status: **{r.status_code}**")
                
                if r.status_code == 200:
                    st.success("Działa!")
                    st.json(r.json())
                else:
                    st.error("Błąd API")
                    st.json(r.json())
            except Exception as e:
                st.error(f"Błąd: {e}")
