"""
seo_utils.py — wspólne funkcje dla narzędzi SEO.

Wrzuć ten plik OBOK swoich skryptów Streamlit i importuj z niego.
Dzięki temu nie powielasz logowania, scrapera ani embeddingów w każdym pliku.

W requirements.txt dorzuć dodatkowo:
    trafilatura

Reszta zależności (streamlit, openai, bcrypt, requests, beautifulsoup4,
numpy, pandas, scikit-learn, plotly) i tak już masz.
"""

import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin, urlparse

import bcrypt
import numpy as np
import requests
import streamlit as st
from bs4 import BeautifulSoup
from openai import OpenAI

USER_DATA_PATH = "users.json"
EMBED_MODEL = "text-embedding-3-large"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0 Safari/537.36"
}

# =========================================================
# AUTH  (jedno miejsce zamiast trzech kopii)
# =========================================================
def _check_password(hashed, pwd):
    return bcrypt.checkpw(pwd.encode("utf-8"), hashed.encode("utf-8"))


def _load_users():
    try:
        with open(USER_DATA_PATH, "r") as f:
            return json.load(f).get("users", {})
    except FileNotFoundError:
        st.error(f"Nie znaleziono pliku {USER_DATA_PATH}.")
        return {}
    except Exception as e:
        st.error(f"Błąd odczytu użytkowników: {e}")
        return {}


def require_login(app_name="SEO Tool"):
    """Wywołaj na samej górze strony. Jeśli niezalogowany → ekran logowania i stop."""
    if st.session_state.get("logged_in"):
        st.sidebar.title(f"👤 {st.session_state.get('username', '')}")
        if st.sidebar.button("Wyloguj"):
            st.session_state.pop("logged_in", None)
            st.session_state.pop("username", None)
            st.rerun()
        return

    st.title(f"🔐 Logowanie — {app_name}")
    u = st.text_input("Nazwa użytkownika")
    p = st.text_input("Hasło", type="password")
    if st.button("Zaloguj"):
        users = _load_users()
        if u in users and _check_password(users[u], p):
            st.session_state["logged_in"] = True
            st.session_state["username"] = u
            st.rerun()
        else:
            st.error("Nieprawidłowa nazwa użytkownika lub hasło.")
    st.stop()


# =========================================================
# OPENAI
# =========================================================
def get_client():
    key = None
    try:
        key = st.secrets["OPENAI_API_KEY"]
    except Exception:
        key = st.sidebar.text_input("Klucz OpenAI API", type="password")
    if not key:
        st.info("Podaj klucz OpenAI API (secrets lub panel boczny).")
        st.stop()
    return OpenAI(api_key=key)


def chat_json(client, model, system, user, temperature=0.2):
    """
    Wymusza poprawny JSON (response_format) i jest odporny na modele
    reasoning-owe, które potrafią odrzucać parametr temperature.
    """
    base = dict(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        response_format={"type": "json_object"},
    )
    try:
        resp = client.chat.completions.create(temperature=temperature, **base)
    except Exception:
        resp = client.chat.completions.create(**base)  # model bez temperature
    return resp.choices[0].message.content


# =========================================================
# SCRAPING  (trafilatura + fallback BS4, treść GŁÓWNA bez boilerplate)
# =========================================================
_BOILER = re.compile(
    r"(nav|menu|footer|header|cookie|consent|sidebar|breadcrumb|comment|"
    r"popup|modal|share|social|widget|related|recommend|newsletter)",
    re.I,
)


def _fetch_html(url, timeout=12):
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout)
        if r.status_code != 200:
            return None
        r.encoding = r.apparent_encoding or r.encoding
        return r.text
    except Exception:
        return None


def _bs4_main(html, max_chars):
    soup = BeautifulSoup(html, "html.parser")
    # twarde tagi techniczne / nawigacyjne
    for tag in soup(["script", "style", "noscript", "svg", "iframe",
                     "nav", "footer", "header", "aside", "form"]):
        tag.decompose()
    # boilerplate po class / id (div-y menu, cookie, sidebar itd.)
    for el in soup.find_all(
        lambda t: t.has_attr("class")
        and _BOILER.search(" ".join(t.get("class")))
    ):
        el.decompose()
    for el in soup.find_all(id=_BOILER):
        el.decompose()

    main = (soup.find("article") or soup.find("main")
            or soup.find(attrs={"role": "main"}) or soup.body or soup)
    text = " ".join(main.get_text(separator=" ").split())
    return text[:max_chars] if len(text) >= 100 else None


def norm_url(u):
    """Normalizacja do porównań: bez schematu, bez www, bez '/' na końcu, bez kotwicy."""
    try:
        p = urlparse(u.strip())
        netloc = (p.netloc or "").lower()
        if netloc.startswith("www."):
            netloc = netloc[4:]
        path = (p.path or "").rstrip("/") or "/"
        q = f"?{p.query}" if p.query else ""
        return f"{netloc}{path}{q}"
    except Exception:
        return u.strip().lower()


def _text_from_html(html, url, max_chars):
    try:
        import trafilatura
        txt = trafilatura.extract(
            html, url=url,
            include_comments=False, include_tables=True,
            favor_precision=True, output_format="txt",
        )
        if txt and len(txt.strip()) >= 120:
            return " ".join(txt.split())[:max_chars]
    except Exception:
        pass
    return _bs4_main(html, max_chars)


def _links_from_html(html, base_url):
    """Linki wychodzące z TREŚCI GŁÓWNEJ (nie z menu/stopki) → {norm_url: anchor_text}."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["nav", "footer", "header", "aside"]):
        tag.decompose()
    main = (soup.find("article") or soup.find("main")
            or soup.find(attrs={"role": "main"}) or soup.body or soup)
    out = {}
    for a in main.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        try:
            absu = urljoin(base_url, href)
        except Exception:
            continue
        out[norm_url(absu)] = a.get_text(strip=True)
    return out


def _extract_main_content_raw(url, max_chars=20000):
    """Czysta funkcja (bez st.*), bezpieczna do odpalania w wątkach."""
    html = _fetch_html(url)
    if not html:
        return None
    return _text_from_html(html, url, max_chars)


def _extract_source_raw(url, max_chars=20000):
    """Dla źródeł: treść główna + linki wychodzące (do wykrywania istniejących linków)."""
    html = _fetch_html(url)
    if not html:
        return None
    return {"text": _text_from_html(html, url, max_chars),
            "links": _links_from_html(html, url)}


def _title_h1_raw(url):
    html = _fetch_html(url)
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    t = soup.title.get_text(strip=True) if soup.title else ""
    h = soup.find("h1")
    h = h.get_text(strip=True) if h else ""
    return f"{t} {h}".strip()


def _parallel_map(fn, items, max_workers=8, progress=None):
    out = {}
    if not items:
        return out
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs = {ex.submit(fn, it): it for it in items}
        done = 0
        for fut in as_completed(futs):  # pętla w wątku głównym → progress() bezpieczny
            it = futs[fut]
            try:
                out[it] = fut.result()
            except Exception:
                out[it] = None
            done += 1
            if progress:
                progress(done / len(items))
    return out


def scrape_texts(urls, progress=None, max_chars=20000):
    """Treść główna dla listy URL-i. Cache w session_state, scraping równoległy."""
    cache = st.session_state.setdefault("_scrape_cache", {})
    todo = [u for u in urls if u not in cache]
    if todo:
        cache.update(
            _parallel_map(lambda u: _extract_main_content_raw(u, max_chars),
                          todo, progress=progress)
        )
    return [(u, cache.get(u)) for u in urls]


def scrape_topics(urls, progress=None):
    """Title + H1 (lekkie 'o czym jest strona') dla listy URL-i."""
    cache = st.session_state.setdefault("_topic_cache", {})
    todo = [u for u in urls if u not in cache]
    if todo:
        cache.update(_parallel_map(_title_h1_raw, todo, progress=progress))
    return {u: cache.get(u, "") for u in urls}


def scrape_sources(urls, progress=None, max_chars=20000):
    """Dla źródeł: {url: {'text': ..., 'links': {norm_url: anchor}}}. Cache + równolegle."""
    cache = st.session_state.setdefault("_source_cache", {})
    todo = [u for u in urls if u not in cache]
    if todo:
        cache.update(
            _parallel_map(lambda u: _extract_source_raw(u, max_chars),
                          todo, progress=progress)
        )
    return {u: cache.get(u) for u in urls}


# =========================================================
# EMBEDDINGI  (batch + dedup + cache → dużo taniej i szybciej)
# =========================================================
def embed_texts(client, texts, model=EMBED_MODEL, progress=None):
    cache = st.session_state.setdefault("_emb_cache", {})
    norm = [t if isinstance(t, str) and t.strip() else " " for t in texts]
    todo = list({t for t in norm if t not in cache})
    B = 100
    for i in range(0, len(todo), B):
        chunk = todo[i:i + B]
        resp = client.embeddings.create(input=chunk, model=model)
        for t, d in zip(chunk, resp.data):
            cache[t] = np.array(d.embedding, dtype=np.float32)
        if progress:
            progress(min((i + B) / max(len(todo), 1), 1.0))
    return np.array([cache[t] for t in norm])
