import streamlit as st
import requests
import json

st.set_page_config(page_title="Senuto Lab", layout="wide")

st.title("🧪 Laboratorium API Senuto")
st.markdown("""
To narzędzie służy do znalezienia działającego połączenia.
Będziesz potrzebować otwartej dokumentacji Senuto.
""")

# --- 1. KONFIGURACJA KLUCZA ---
with st.sidebar:
    st.header("🔑 Ustawienia")
    # Pobieramy klucz z secrets, jeśli jest
    default_key = st.secrets.get("SENUTO_API_KEY", "")
    api_key = st.text_input("Twój Bearer Token", value=default_key, type="password")
    
    st.info("Token powinien być długim ciągiem znaków.")

# --- 2. TEST POŁĄCZENIA (Autoryzacja) ---
st.subheader("1. Test Autoryzacji")
st.caption("Sprawdźmy, czy Twój klucz API jest poprawny, pytając o dane zalogowanego użytkownika.")

if st.button("🔍 Sprawdź klucz (/api/users/getLoggedUser)"):
    if not api_key:
        st.error("Wpisz klucz API w pasku bocznym!")
    else:
        url = "https://api.senuto.com/api/users/getLoggedUser"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        try:
            response = requests.get(url, headers=headers)
            if response.status_code == 200:
                st.success("✅ SUKCES! Klucz działa.")
                st.json(response.json())
            else:
                st.error(f"❌ BŁĄD: {response.status_code}")
                st.write("Serwer odpowiedział:")
                st.text(response.text)
        except Exception as e:
            st.error(f"Błąd połączenia: {e}")

st.divider()

# --- 3. TEST KEYWORD EXPLORER ---
st.subheader("2. Test Keyword Explorer")
st.markdown("Tutaj wklej endpoint z sekcji **Keyword Explorer** ze swojej dokumentacji.")

col1, col2 = st.columns([3, 1])
with col1:
    # Domyślnie wpisuję najbardziej prawdopodobny adres
    endpoint = st.text_input("Endpoint URL", "https://api.senuto.com/api/keywords/explorer/related")
with col2:
    method = st.selectbox("Metoda", ["POST", "GET"])

# Domyślny JSON dla Keyword Explorer
default_body = """{
    "query": "rowery",
    "country_id": 1,
    "limit": 5
}"""

body = st.text_area("Body (JSON)", value=default_body, height=150)

if st.button("🚀 Wyślij zapytanie testowe"):
    if not api_key:
        st.error("Brak klucza API!")
    else:
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        st.write(f"Wysyłam {method} na: `{endpoint}`")
        
        try:
            if method == "GET":
                response = requests.get(endpoint, headers=headers)
            else:
                # Parsowanie JSON z pola tekstowego
                try:
                    json_data = json.loads(body)
                except:
                    st.error("Błąd w formacie JSON! Sprawdź przecinki i cudzysłowy.")
                    st.stop()
                    
                response = requests.post(endpoint, headers=headers, json=json_data)
            
            # Wynik
            st.write(f"Status: **{response.status_code}**")
            
            if response.status_code == 200:
                st.success("Działa! Oto dane:")
                st.json(response.json())
            elif response.status_code == 404:
                st.error("404 Not Found - Ten endpoint nie istnieje.")
                st.info("Sprawdź w dokumentacji sekcję 'Keyword Explorer'. Adres może być inny.")
            elif response.status_code == 401:
                st.error("401 Unauthorized - Token nie ma dostępu do tego modułu.")
            else:
                st.error("Inny błąd.")
                st.text(response.text)
                
        except Exception as e:
            st.error(f"Krytyczny błąd: {e}")
