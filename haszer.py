import bcrypt

# Funkcja do hashowania hasła
def hash_password(password):
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

# Przykład użycia
if __name__ == "__main__":
    password = "secret"  # Tutaj wpisz hasło, które chcesz zahaszować
    hashed_password = hash_password(password)
    print(f"Zahaszowane hasło: {hashed_password}")