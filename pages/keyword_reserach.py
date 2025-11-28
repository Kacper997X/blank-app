import streamlit as st
import requests
import json

st.set_page_config(page_title="Senuto Final Check", layout="wide")
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
        except Exception as e:
            st.error(f"Błąd: {e}")

# --- TEST B: Raporty Analityczne (Z Twojego cURL) ---
with col2:
    st.header("Test B: GetKeywords (Advanced)")
    st.markdown("`POST .../keywords_analysis/reports/keywords/getKeywords`")
    st.info("To jest ten endpoint z Twojej dokumentacji cURL.")
    
    if st.button("Uruchom Test B"):
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
            else:
                st.error("Nie działa 🔴")
                st.text(r.text)
        except Exception as e:
            st.error(f"Błąd: {e}")
