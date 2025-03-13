import streamlit as st

# Sprawdź, czy użytkownik jest zalogowany
if 'logged_in' not in st.session_state or not st.session_state['logged_in']:
    st.warning("Musisz się zalogować, aby uzyskać dostęp do tej strony.")
    st.stop()

# Główna zawartość podstrony
st.title("Podstrona 1")
st.write("To jest zawartość podstrony 1 dostępna tylko dla zalogowanych użytkowników.")