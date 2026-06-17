"""
site_focus.py — Audyt spójności tematycznej (Site Focus & Site Radius)

Zmiany względem wersji poprzedniej:
- analizuje PEŁNĄ treść główną strony (trafilatura), a nie tylko Title+H1+Desc
  → centroid i radius są dużo bardziej wiarygodne;
- scraping równoległy + cache, batchowane embeddingi z cache (taniej i szybciej);
- wyniki trzymane w session_state (pobranie CSV nie kasuje raportu).

Uruchom:  streamlit run site_focus.py
"""

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st
from sklearn.metrics.pairwise import cosine_similarity

from seo_utils import require_login, get_client, scrape_texts, embed_texts

st.set_page_config(page_title="Site Focus & Radius", page_icon="🎯", layout="wide")
require_login("Site Focus")
client = get_client()

st.title("🎯 Audyt spójności tematycznej — Site Focus & Radius")
st.markdown("""
Bada architekturę informacji semantycznie: wyznacza **centroid** (środek tematyczny
domeny) z **pełnej treści** stron i liczy **Site Radius** każdej strony — odległość od
tego środka (`1 − cosinus`).

* 🟢 **CORE** (radius < 0.25) — rdzeń tematyczny
* 🟡 **SUPPORT** (0.25–0.55) — treść wspierająca
* 🔴 **OFF-TOPIC** (> 0.55) — do weryfikacji / potencjalny szum
""")

urls_raw = st.text_area(
    "URL-e domeny (jeden pod drugim):",
    height=240,
    placeholder="https://domena.pl/\nhttps://domena.pl/oferta\nhttps://domena.pl/blog/wpis",
    key="sf_urls",
)

if st.button("🚀 Oblicz Topical Authority", type="primary"):
    urls = [u.strip() for u in urls_raw.splitlines() if u.strip()]
    if len(urls) < 3:
        st.warning("Podaj przynajmniej 3 adresy URL, aby wyznaczyć sensowny środek tematyczny.")
        st.stop()

    pb = st.progress(0.0, text="Pobieranie treści...")
    pairs = scrape_texts(urls, progress=lambda p: pb.progress(p, text="Pobieranie treści głównej..."))
    valid = [(u, t) for u, t in pairs if t]

    if len(valid) < 3:
        pb.empty()
        st.error(f"Pobrano poprawnie tylko {len(valid)} stron (min. 3). Sprawdź URL-e.")
        st.stop()

    urls_v = [u for u, _ in valid]
    texts = [t for _, t in valid]

    pb.progress(0.0, text="Liczenie embeddingów...")
    mat = embed_texts(client, texts, progress=lambda p: pb.progress(p, text="Liczenie embeddingów..."))
    pb.empty()

    centroid = mat.mean(axis=0, keepdims=True)
    radii = 1.0 - cosine_similarity(mat, centroid).flatten()

    df = pd.DataFrame({"url": urls_v, "SiteRadius": radii})

    def status(r):
        if r < 0.25:
            return "🟢 CORE"
        if r < 0.55:
            return "🟡 SUPPORT"
        return "🔴 OFF-TOPIC"

    df["Status"] = df["SiteRadius"].apply(status)
    df = df.sort_values("SiteRadius").reset_index(drop=True)

    avg = float(df["SiteRadius"].mean())
    st.session_state["sf_result"] = {
        "df": df,
        "avg": avg,
        "focus": 1.0 / (1.0 + avg),
        "n_ok": len(valid),
        "n_in": len(urls),
    }

# ---------------- RENDER (poza blokiem przycisku → przeżywa rerun) ----------------
if "sf_result" in st.session_state:
    r = st.session_state["sf_result"]
    df = r["df"]

    st.success(f"✅ Analiza zakończona ({r['n_ok']}/{r['n_in']} stron pobranych poprawnie).")

    m1, m2, m3 = st.columns(3)
    m1.metric("Liczba stron", r["n_ok"])
    m2.metric("Domain Focus", f"{r['focus']:.4f}", help="Heurystyka względna: im bliżej 1.0, tym bardziej domena jest 'zbita' tematycznie. Porównuj między audytami, nie jako wartość bezwzględną.")
    m3.metric("Średni Radius", f"{r['avg']:.4f}", help="Niżej = lepsze skupienie")

    st.divider()
    st.subheader("Mapa spójności")

    plot_df = df.copy()
    plot_df["Y"] = np.random.normal(0, 0.05, len(plot_df))
    plot_df["Label"] = plot_df["url"].apply(lambda x: x[:55] + "…" if len(x) > 55 else x)

    fig = px.scatter(
        plot_df, x="SiteRadius", y="Y", text="Label", color="SiteRadius",
        hover_data=["url"], color_continuous_scale="RdYlGn_r",
        labels={"SiteRadius": "Odległość od centrum (0 = idealnie)"},
        height=560,
    )
    fig.update_yaxes(visible=False, showticklabels=False)
    fig.update_traces(textposition="top center")
    fig.add_vline(x=r["avg"], line_dash="dash", annotation_text="średnia")
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("Szczegóły")
    st.dataframe(
        df[["Status", "SiteRadius", "url"]],
        use_container_width=True,
        column_config={
            "SiteRadius": st.column_config.NumberColumn(format="%.4f"),
            "url": st.column_config.LinkColumn(),
        },
    )
    st.download_button(
        "📥 Pobierz raport (CSV)",
        df.to_csv(sep=";", index=False).encode("utf-8"),
        "raport_topical_authority.csv",
        "text/csv",
    )
