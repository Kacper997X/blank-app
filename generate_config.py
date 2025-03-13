import streamlit_authenticator as stauth
import yaml

# 📌 Hasła do zahashowania
passwords = ["haslo123", "test123"]

# 📌 Haszujemy każde hasło osobno
hashed_passwords = [stauth.Hasher().hash(p) for p in passwords]

# 📌 Definiujemy użytkowników
users_data = {
    "credentials": {
        "usernames": {
            "admin": {
                "email": "admin@example.com",
                "name": "Administrator",
                "password": hashed_passwords[0],  # Używamy zahaszowanego hasła
            },
            "user1": {
                "email": "user1@example.com",
                "name": "Użytkownik 1",
                "password": hashed_passwords[1],  # Używamy zahaszowanego hasła
            },
        }
    }
}

# 📌 Zapisujemy dane do pliku `config.yaml`
with open("config.yaml", "w") as file:
    yaml.dump(users_data, file, default_flow_style=False)

print("✅ Plik config.yaml został wygenerowany!")
