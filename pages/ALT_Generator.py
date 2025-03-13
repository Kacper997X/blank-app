
import streamlit as st

# Sprawdź, czy użytkownik jest zalogowany
if 'logged_in' not in st.session_state or not st.session_state['logged_in']:
    st.warning("Musisz się zalogować, aby uzyskać dostęp do tej strony.")
    st.stop()

import pandas as pd
from openai import OpenAI
import concurrent.futures
import requests
from dotenv import load_dotenv

# Inicjalizacja klienta OpenAI
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

# Funkcja do generowania opisu zdjęcia (Krok 1)
def generate_image_description(image_url):
    try:
        # Sprawdź, czy obraz jest dostępny
        response = requests.get(image_url, timeout=10)
        response.raise_for_status()  # Sprawdź, czy odpowiedź jest poprawna

        # Prześlij obraz do OpenAI API
        response = client.chat.completions.create(
            model="gpt-4o-mini",  # Użyj modelu GPT-4o mini
            messages=[
                {"role": "system", "content": 
                  "Utilize advanced image processing and visual content analysis techniques to accurately identify and describe elements in the image. "
                  "Focus on details such as key objects, colors, actions, emotions, and other significant aspects that are crucial for a comprehensive understanding of the image content."
                 },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Please analyze and describe the following image:"},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": image_url,
                            },
                        },
                    ],
                },
            ],
            temperature =0.7,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        st.warning(f"Błąd podczas generowania opisu dla {image_url}: {e}")
        return None

# Funkcja do generowania atrybutu ALT (Krok 2)
def generate_alt_text(image_description, keyword=None, title=None, brand_context=None):
    try:
        if not image_description:
            return None

        system_prompt = (
            "As an SEO and accessibility specialist, your mission is to enrich the web experience for all users by creating alt attributes for images. "
            "These attributes should not only be optimized for search engines but also cater to the accessibility needs of people with disabilities. "
            "Your aim is to naturally incorporate the provided keyword into the alt text, ensuring it aligns perfectly with the context and serves accessibility purposes.\n\n"
            "Examples of ALT attributes:\n"
            "### 1. Context: A woman working on her laptop at a coffee shop.\n"
            "- **Keyword Phrase**: 'work remotely coffee shop'\n"
            "- **Prompt**: 'Create an ALT attribute that naturally includes the phrase 'work remotely coffee shop', ensuring it's descriptive, accessible, and SEO-friendly.'\n"
            "- **Correct ALT**: 'A woman working remotely in a bustling coffee shop, blending work with the pleasure of coffee.'\n\n"
            "### 2. Context: Fresh vegetables and fruits on a kitchen counter.\n"
            "- **Keyword Phrase**: 'eat healthy food'\n"
            "- **Prompt**: 'Generate an ALT attribute that seamlessly integrates 'eat healthy food' into a descriptive and engaging sentence that benefits both SEO and accessibility.'\n"
            "- **Correct ALT**: 'A colorful selection of fresh fruits and vegetables on a kitchen counter promoting healthy eating habits.'\n\n"
            "### 3. Context: A man hiking in the mountains.\n"
            "- **Keyword Phrase**: 'hike mountain adventure'\n"
            "- **Prompt**: 'Create an ALT attribute that naturally weaves in 'hike mountain adventure', making it informative for SEO while being useful for users with accessibility needs.'\n"
            "- **Correct ALT**: 'An adventurous man hiking a scenic mountain trail, indulging in the thrill of a mountain adventure.'\n\n"
            "### 4. Context: Kids playing in a playground.\n"
            "- **Keyword Phrase**: 'play outdoor games'\n"
            "- **Prompt**: 'Develop an ALT attribute that effectively incorporates 'play outdoor games', focusing on making it sound natural and ensuring it aids both SEO and accessibility.'\n"
            "- **Correct ALT**: 'Joyful children playing on a sunny playground, showcasing the joys of outdoor games.'\n\n"
            "### 5. Context: A compact and modern city car.\n"
            "- **Keyword Phrase**: 'drive city car'\n"
            "- **Prompt**: 'Compose an ALT attribute that includes 'drive city car' in a way that feels organic and serves the dual purpose of enhancing SEO and accessibility.'\n"
            "- **Correct ALT**: 'Sleek and modern city car parked on an urban street, perfect for those wishing to effortlessly navigate the city.'\n\n"
            "Please also consider the brand-specific context, and examples of alt attributes for that brand, if provided: {brand_context} {example_alts}\n\n"
            "ALT Attribute should be written in Polish Language."
        )
        user_prompt = (
            f"Using the image description obtained, your task is to create an ALT attribute that:\n\n"
            f"1. Accurately and vividly conveys the content and essence of the image, focusing on key details that elucidate its connection to the page content.\n"
            f"2. Integrates the provided keyword (if available) into the description in a way that feels integral to the narrative, avoiding any impression that it's been awkwardly inserted.\n"
            f"3. Meets the WCAG accessibility standards by ensuring the text is clear, concise, and meaningful for users utilizing screen readers, thereby avoiding vague or non-specific language.\n"
            f"4. Is succinct, aiming to keep the description under 125 characters to ensure it is brief yet effective for those using screen readers.\n"
            f"5. Avoids starting with unnecessary introductions like 'image of' or 'picture of,' as assistive technologies already identify the content as an image.\n"
            f"6. Is thoughtfully tailored based on the provided image description, and incorporates the keyword (if available), resulting in an ALT text that enriches understanding of the image's role and importance within the page context.\n\n"
            f"Image description: {image_description}\n"
            f"Keyword: {keyword}\n"
            f"Title or context: {title}\n\n"
            f"Please provide only the text of the ALT attribute."
        )

        response = client.chat.completions.create(
            model="gpt-4o-mini",  # Użyj modelu GPT-4o mini
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            max_tokens=125,
            temperature =0.5
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        st.warning(f"Błąd podczas generowania ALT dla opisu: {image_description}. Błąd: {e}")
        return None

# Funkcja do przetwarzania pojedynczego wiersza
def process_row(row, brand_context):
    image_url = row['url']
    keyword = row.get('keyword', None)
    title = row.get('title', None)

    # Krok 1: Generowanie opisu zdjęcia
    image_description = generate_image_description(image_url)
    if image_description:
        # Krok 2: Generowanie atrybutu ALT
        alt_text = generate_alt_text(image_description, keyword, title, brand_context)
        return image_description, alt_text
    else:
        return "Błąd: Nie udało się wygenerować opisu.", "Błąd: Nie udało się wygenerować ALT."

# Interfejs Streamlit
st.title("Generator atrybutów ALT dla obrazów")

# Przycisk do pobrania wzoru pliku CSV
def get_csv_template():
    # Przygotowanie przykładowych danych
    data = {
        'url': ['https://example.com/image1.jpg', 'https://example.com/image2.png'],
        'keyword': ['zdrowa żywność', 'kawa w kawiarni'],
        'title': ['Owoce i warzywa', 'Relaks przy kawie']
    }
    df = pd.DataFrame(data)
    return df

st.download_button(
    label="Pobierz wzór pliku CSV",
    data=get_csv_template().to_csv(index=False).encode('utf-8'),
    file_name="wzor_pliku.csv",
    mime="text/csv"
)

# Pole do przesłania pliku CSV
uploaded_file = st.file_uploader("Prześlij plik CSV z kolumnami: url, keyword, title", type=["csv"])

# Pole do wprowadzenia kontekstu marki (brand context)
brand_context = st.text_area("Podaj kontekst marki (opcjonalne):", placeholder="np. Marka XYZ specjalizuje się w ekologicznych produktach.")

# Pole do wprowadzenia przykładowych atrybutów ALT (opcjonalne)
example_alts = st.text_area("Podaj przykładowe atrybuty ALT (opcjonalne):", placeholder="np. Ekologiczne warzywa i owoce na drewnianym stole.")

# Przycisk do uruchomienia procesu
if st.button("Generuj ALT"):
    if uploaded_file is not None:
        # Wczytanie pliku CSV
        df = pd.read_csv(uploaded_file, encoding='ISO-8859-2')

        # Sprawdzenie, czy plik zawiera wymagane kolumny
        if 'url' not in df.columns:
            st.error("Plik CSV musi zawierać kolumnę 'url'.")
        else:
            # Dodanie nowych kolumn do DataFrame
            df['opis_zdjecia'] = ""
            df['atrybut_alt'] = ""

            # Przetwarzanie każdego wiersza równolegle
            with concurrent.futures.ThreadPoolExecutor() as executor:
                # Przechowuj wyniki w liście, aby zachować kolejność
                results = list(executor.map(lambda row: process_row(row, brand_context), df.to_dict('records')))

            # Przypisz wyniki do odpowiednich wierszy
            for index, (image_description, alt_text) in enumerate(results):
                df.at[index, 'opis_zdjecia'] = image_description
                df.at[index, 'atrybut_alt'] = alt_text

            # Wyświetlenie wyników
            st.success("Generowanie zakończone!")
            st.write(df)

            # Przycisk do pobrania wyników jako CSV
            csv = df.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="Pobierz wyniki jako CSV",
                data=csv,
                file_name='wyniki_alt.csv',
                mime='text/csv',
            )
    else:
        st.error("Proszę przesłać plik CSV.")