"""
internal_linking.py — Planer linkowania wewnętrznego (v2)

PIPELINE (Opcja A — wszystko na OpenAI, bez dodatkowej infry):
  1. COSINUS (bi-encoder) — zbiera kandydatów na każde źródło (szeroka sieć).
     To NIE jest cięcie — tylko zebranie puli do oceny.
  2. RERANK + ANCHOR (jeden strzał na źródło) — model ocenia trafność każdego
     kandydata 0-100 ("relevance") ORAZ proponuje anchory. Reranking USTAWIA
     KOLEJNOŚĆ (od najbardziej do najmniej zbliżonych), niczego nie odrzuca.
  3. Tabela posortowana wg trafności, z oznaczeniem linków JUŻ obecnych w tekście.

TRYBY WEJŚCIA:
  • Dwie pule:  ŹRÓDŁA (gdzie szukamy miejsc na link) → CELE (gdzie linkujemy).
  • Jedna pula: każdy z każdym (dowolna strona może linkować do dowolnej innej).

TRYBY EDYCJI:
  • bez edycji — anchor tylko z fraz dosłownie obecnych w tekście (walidacja w kodzie).
  • z edycją  — dozwolone drobne zmiany zdań (typ "nowy").

Gdybyś kiedyś chciał prawdziwy cross-encoder (Jina API / self-host bge-reranker-v2-m3),
podmieniasz tylko krok scorujący — reszta pipeline zostaje bez zmian.

Uruchom:  streamlit run internal_linking.py
"""

import json
import re

import numpy as np
import pandas as pd
import streamlit as st
from sklearn.metrics.pairwise import cosine_similarity

from seo_utils import (require_login, get_client, scrape_sources,
                       scrape_topics, embed_texts, chat_json, norm_url)

st.set_page_config(page_title="Internal Linking Planner", page_icon="🔗", layout="wide")
require_login("Internal Linking")
client = get_client()

MODELS = ["gpt-4o-mini", "gpt-4o", "gpt-5-mini"]
MAX_SRC_CHARS = 14000  # ile tekstu źródłowego wysyłamy do modelu (kontrola tokenów)

st.title("🔗 Planer linkowania wewnętrznego")
st.markdown(
    "Szuka miejsc na linki wewnętrzne. Cosinus zbiera kandydatów, model układa ich "
    "**w kolejności trafności** (nic nie wycina) i proponuje anchory. Linki już obecne "
    "w tekście są wykrywane i oznaczane."
)

# ---------- WEJŚCIE ----------
input_mode = st.radio(
    "Tryb wejścia:",
    ["Dwie pule (źródła → cele)", "Jedna pula (każdy z każdym)"],
    horizontal=True,
)

if input_mode.startswith("Dwie"):
    c_src, c_tgt = st.columns(2)
    with c_src:
        src_raw = st.text_area(
            "ŹRÓDŁA — URL-e (tekst, w którym szukamy miejsc na link):",
            height=220,
            placeholder="https://domena.pl/blog/artykul-1\nhttps://domena.pl/blog/artykul-2",
            key="il_src",
        )
    with c_tgt:
        tgt_raw = st.text_area(
            "CELE — `URL` albo `URL ; fraza docelowa`:",
            height=220,
            placeholder="https://domena.pl/oferta ; skup nieruchomości\nhttps://domena.pl/kredyt ; kalkulator kredytu hipotecznego",
            key="il_tgt",
        )
    pool_raw = ""
else:
    pool_raw = st.text_area(
        "PULA — wszystkie URL-e (`URL` albo `URL ; fraza`). Każdy może linkować do każdego:",
        height=240,
        placeholder="https://domena.pl/a\nhttps://domena.pl/b ; fraza b\nhttps://domena.pl/c",
        key="il_pool",
    )
    src_raw = tgt_raw = ""

st.caption("Frazę docelową po średniku warto podać — definiuje, o czym jest strona docelowa. "
           "Bez niej narzędzie pobierze Title+H1 strony.")

mode = st.radio(
    "Tryb edycji tekstu:",
    ["Nie mogę edytować tekstu (tylko frazy już obecne)",
     "Mogę edytować tekst (dozwolone drobne zmiany)"],
)
edit_allowed = mode.startswith("Mogę")

c1, c2, c3 = st.columns(3)
top_k = c1.slider("Kandydatów na źródło (cosinus zbiera)", 1, 25, 8)
min_sim = c2.slider("Min. podobieństwo cosinus (sito wstępne)", 0.0, 0.6, 0.15, 0.05)
model = c3.selectbox("Model (rerank + anchory)", MODELS)

run = st.button("🚀 Analizuj możliwości linkowania", type="primary")


# ---------- PROMPTY ----------
SYSTEM_BASE = """Jesteś ekspertem SEO od linkowania wewnętrznego (internal linking) dla polskich serwisów.
Dostajesz JEDEN tekst źródłowy oraz listę stron docelowych (każda opisana frazą/tematem).
Dla KAŻDEJ strony docelowej zrób dwie rzeczy:

A) RERANKING — oceń "relevance" 0-100: jak bardzo sensowny i merytorycznie uzasadniony jest link
   z tego tekstu do tej strony (temat + kontekst tekstu). Oceń KAŻDĄ stronę — to służy do ułożenia
   kolejności, niczego nie odrzucamy.
B) ANCHORY — zaproponuj konkretne anchory wg zasad trybu poniżej.

ZASADY ANCHORÓW:
- Link uzasadniony merytorycznie; anchor pasuje do strony docelowej ORAZ do kontekstu zdania.
- Anchor 1-5 słów, naturalny, bez exact-match spamu.
- Maksymalnie 2 propozycje na jedną stronę docelową; brak dobrej propozycji → pusta lista (ale "relevance" i tak oceń).
- "kontekst" = zdanie/fragment z tekstu, którego dotyczy anchor.
- Jeśli przy stronie docelowej jest adnotacja [JUŻ PODLINKOWANE], link z tego tekstu już istnieje:
  obniż relevance i NIE proponuj duplikatu (chyba że sensowny jest dodatkowy link w innym miejscu).
"""

MODE1 = """
TRYB: NIE MOŻNA EDYTOWAĆ TEKSTU.
- Wolno użyć WYŁĄCZNIE fragmentów występujących DOSŁOWNIE w tekście źródłowym.
- "anchor" musi być dokładnym ciągiem skopiowanym 1:1 z tekstu (z zachowaniem odmiany).
- Jeśli brak naturalnego, dosłownego dopasowania — pusta lista propozycji (relevance oceń mimo to).
- "typ" zawsze = "istniejacy", "propozycja_zmiany" zawsze = null.
"""

MODE2 = """
TRYB: MOŻNA EDYTOWAĆ TEKST.
- Najpierw szukaj anchorów obecnych dosłownie (typ = "istniejacy", propozycja_zmiany = null).
- Jeśli brak dobrego dopasowania, zaproponuj DROBNĄ zmianę (typ = "nowy"): przeredagowanie zdania
  lub dołożenie jednego krótkiego, naturalnego zdania mieszczącego link.
- Dla typu "nowy" w "propozycja_zmiany" podaj pełną nową/zmienioną treść zdania, anchor w **gwiazdkach**.
- Zmiany minimalne, nie psują stylu ani sensu.
"""

SCHEMA = """
FORMAT ODPOWIEDZI — wyłącznie poprawny JSON:
{
  "wyniki": [
    {
      "target_id": <numer w nawiasie []>,
      "relevance": <0-100>,
      "propozycje": [
        {"typ":"istniejacy|nowy","anchor":"...","kontekst":"...","propozycja_zmiany":null,"trafnosc":0-100,"uzasadnienie":"..."}
      ]
    }
  ]
}
"""


def _norm(s):
    return re.sub(r"\s+", " ", str(s).lower()).strip()


def parse_targets(raw):
    out = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        if ";" in line:
            u, f = line.split(";", 1)
            out.append((u.strip(), f.strip()))
        else:
            out.append((line, ""))
    return out


if run:
    # --- 1. zbuduj pule wg trybu ---
    if input_mode.startswith("Dwie"):
        src_urls = [u.strip() for u in src_raw.splitlines() if u.strip()]
        targets = parse_targets(tgt_raw)
    else:
        targets = parse_targets(pool_raw)
        src_urls = [u for u, _ in targets]

    if not src_urls or not targets:
        st.warning("Podaj dane wejściowe (źródła i cele albo wspólną pulę).")
        st.stop()

    # --- 2. scraping źródeł (tekst + linki) i tematów celów ---
    pb = st.progress(0.0, text="Pobieranie treści źródłowych...")
    src_map = scrape_sources(src_urls, progress=lambda p: pb.progress(p, text="Pobieranie treści źródłowych..."))

    tgt_urls = [u for u, _ in targets]
    missing = [u for u, f in targets if not f]
    pb.progress(0.0, text="Pobieranie tematów stron docelowych...")
    topic_map = scrape_topics(missing, progress=lambda p: pb.progress(p, text="Pobieranie tematów stron docelowych...")) if missing else {}
    tgt_topic = [f if f else (topic_map.get(u, "") or u) for u, f in targets]
    pb.empty()

    s_urls, s_texts, s_links = [], [], []
    for u in src_urls:
        d = src_map.get(u)
        if d and d.get("text"):
            s_urls.append(u)
            s_texts.append(d["text"][:MAX_SRC_CHARS])
            s_links.append(d.get("links") or {})
    if not s_urls:
        st.error("Nie udało się pobrać treści żadnego źródła.")
        st.stop()

    # --- 3. COSINUS: zbierz kandydatów ---
    with st.spinner("Etap 1 — cosinus (zbieranie kandydatów)..."):
        vecs = embed_texts(client, s_texts + tgt_topic)
        s_vecs, t_vecs = vecs[:len(s_texts)], vecs[len(s_texts):]
        sim = cosine_similarity(s_vecs, t_vecs)  # [n_src, n_tgt]

    tgt_norm = [norm_url(u) for u in tgt_urls]
    candidates = {}
    for i in range(len(s_urls)):
        src_n = norm_url(s_urls[i])
        picks = []
        for j in np.argsort(sim[i])[::-1]:
            if tgt_norm[j] == src_n:           # nie linkuj do samego siebie
                continue
            if sim[i][j] < min_sim:
                break
            picks.append((int(j), float(sim[i][j])))
            if len(picks) >= top_k:
                break
        if picks:
            candidates[i] = picks

    n_calls = len(candidates)
    if n_calls == 0:
        st.info("Cosinus nie znalazł par powyżej progu. Obniż 'Min. podobieństwo' lub sprawdź dane.")
        st.stop()
    st.caption(f"Cosinus: {sum(len(v) for v in candidates.values())} par-kandydatów "
               f"→ rerank + anchory: {n_calls} zapytań do modelu ({model}).")

    # --- 4. RERANK + ANCHOR (jeden strzał na źródło) ---
    system = SYSTEM_BASE + (MODE2 if edit_allowed else MODE1) + SCHEMA
    rows = []
    pb2 = st.progress(0.0, text="Rerank + propozycje anchorów...")

    for n, (i, picks) in enumerate(candidates.items()):
        links_i = s_links[i]
        existing = {j: (tgt_norm[j] in links_i) for j, _ in picks}

        block = "\n".join(
            f"[{k}] URL: {tgt_urls[j]} | TEMAT: {tgt_topic[j]}"
            + (" [JUŻ PODLINKOWANE]" if existing[j] else "")
            for k, (j, _) in enumerate(picks)
        )
        user = (f'TEKST ŹRÓDŁOWY (URL: {s_urls[i]}):\n"""\n{s_texts[i]}\n"""\n\n'
                f"STRONY DOCELOWE (używaj target_id = numer w []):\n{block}")

        rerank_map = {}
        try:
            data = json.loads(chat_json(client, model, system, user))
            for w in data.get("wyniki", []):
                try:
                    k = int(w.get("target_id"))
                    j, score = picks[k]
                except (TypeError, ValueError, IndexError):
                    continue
                relevance = w.get("relevance", "")
                rerank_map[j] = relevance
                text_norm = _norm(s_texts[i])

                valid = []
                for prop in (w.get("propozycje") or [])[:2]:
                    typ = prop.get("typ", "istniejacy")
                    anchor = (prop.get("anchor") or "").strip()
                    if not anchor:
                        continue
                    if not edit_allowed and (typ != "istniejacy" or _norm(anchor) not in text_norm):
                        continue
                    valid.append((typ, anchor, prop))

                base = {
                    "zrodlo": s_urls[i], "cel": tgt_urls[j], "fraza_docelowa": tgt_topic[j],
                    "relevance": relevance, "similarity": round(score, 3),
                    "juz_podlinkowane": "TAK" if existing[j] else "",
                    "istniejacy_anchor": links_i.get(tgt_norm[j], "") if existing[j] else "",
                }
                if valid:
                    for typ, anchor, prop in valid:
                        rows.append({**base, "typ": typ, "anchor": anchor,
                                     "trafnosc": prop.get("trafnosc", ""),
                                     "kontekst": (prop.get("kontekst") or "")[:300],
                                     "propozycja_zmiany": prop.get("propozycja_zmiany") or ""})
                else:
                    rows.append({**base, "typ": "", "anchor": "", "trafnosc": "",
                                 "kontekst": "", "propozycja_zmiany": ""})
        except Exception as e:
            for j, score in picks:
                rows.append({"zrodlo": s_urls[i], "cel": tgt_urls[j], "fraza_docelowa": tgt_topic[j],
                             "relevance": "", "similarity": round(score, 3),
                             "juz_podlinkowane": "TAK" if existing[j] else "",
                             "istniejacy_anchor": "", "typ": "BŁĄD", "anchor": "",
                             "trafnosc": "", "kontekst": str(e)[:120], "propozycja_zmiany": ""})
        pb2.progress((n + 1) / n_calls)

    pb2.empty()
    if not rows:
        st.info("Brak wyników.")
        st.stop()

    df = pd.DataFrame(rows)
    df["_rel"] = pd.to_numeric(df["relevance"], errors="coerce").fillna(-1)
    df = df.sort_values(["zrodlo", "_rel"], ascending=[True, False]).drop(columns="_rel").reset_index(drop=True)

    st.session_state["il_df"] = df
    # snapshot istniejących linków (z treści głównej) do podglądu
    ex_rows = []
    for u in s_urls:
        for href, anchor in (src_map.get(u, {}) or {}).get("links", {}).items():
            ex_rows.append({"zrodlo": u, "link": href, "anchor": anchor})
    st.session_state["il_existing"] = pd.DataFrame(ex_rows)


# ---------- RENDER ----------
if "il_df" in st.session_state:
    df = st.session_state["il_df"]
    st.success(f"✅ Gotowe — {len(df)} pozycji (uporządkowane wg trafności).")

    if "anchor" in df:
        vc = df.loc[df["anchor"] != "", "anchor"].str.lower().value_counts()
        spam = vc[vc >= 4]
        if len(spam):
            st.warning("⚠️ Możliwa nadoptymalizacja — anchory powtarzają się ≥4×: "
                       + ", ".join(f"„{a}” ({c})" for a, c in spam.items()))

    cols = ["zrodlo", "cel", "fraza_docelowa", "relevance", "similarity",
            "juz_podlinkowane", "istniejacy_anchor", "typ", "anchor",
            "trafnosc", "kontekst", "propozycja_zmiany"]
    st.dataframe(
        df[cols], use_container_width=True,
        column_config={
            "zrodlo": st.column_config.LinkColumn("Źródło"),
            "cel": st.column_config.LinkColumn("Cel"),
            "relevance": st.column_config.NumberColumn("Rerank"),
            "similarity": st.column_config.NumberColumn("Cosinus", format="%.3f"),
            "juz_podlinkowane": st.column_config.TextColumn("Już linkowane?"),
        },
    )
    st.download_button(
        "📥 Pobierz propozycje (CSV)",
        df[cols].to_csv(sep=";", index=False).encode("utf-8"),
        "linkowanie_wewnetrzne.csv", "text/csv",
    )

    ex = st.session_state.get("il_existing")
    if ex is not None and len(ex):
        with st.expander(f"🔗 Istniejące linki w tekstach źródłowych ({len(ex)})"):
            st.dataframe(ex, use_container_width=True,
                         column_config={"link": st.column_config.TextColumn("Link (znorm.)")})
