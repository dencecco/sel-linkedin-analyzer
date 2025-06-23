"""
X / Social CSV Analyzer (minimal)
================================
Streamlit app to inspect **X (Twitter)** CSV exports for a main brand plus
optional competitor file.  Tabs: Overview · Top‑10 · (Compare) · Raw.
Views column is optional; engagement rate is computed only if present.
"""

import re, streamlit as st, pandas as pd, altair as alt

st.set_page_config(page_title="🐦 X CSV Analyzer", layout="wide")
st.title("🐦 X (Twitter) CSV Analyzer – minimal edition")

# ── Uploads ──────────────────────────────────────────────────────────
main_file = st.sidebar.file_uploader("Upload MAIN brand CSV", type="csv", key="main")
if main_file is None:
    st.info("⬅️ Upload your main brand CSV to start")
    st.stop()
comp_file = st.sidebar.file_uploader("Upload COMPETITOR CSV (opt.)", type="csv", key="comp")

# robust CSV reader (handles comma / semicolon / tab)
import pandas.errors as pde

def safe_read(file):
    try:
        return pd.read_csv(file, low_memory=False)
    except pde.ParserError:
        file.seek(0)
        try:
            return pd.read_csv(file, sep=";", low_memory=False)
        except pde.ParserError:
            file.seek(0)
            return pd.read_csv(file, sep=None, engine="python", on_bad_lines="skip")

df_main = safe_read(main_file)
df_comp = safe_read(comp_file) if comp_file else pd.DataFrame()

# enrich
(df_comp) if not df_comp.empty else pd.DataFrame()

MAIN = df_main[map_cols["author"]].mode()[0]
df_main["brand"] = MAIN
if not df_comp.empty:
    df_comp["brand"] = df_comp[map_cols["author"]]

# ── Tabs ───────────────────────────────────────────────────────────
TABS = ["Overview", "Top 10"]
if not df_comp.empty:
    TABS.insert(1, "Compare")
TABS.append("Raw")
pages = st.tabs(["🐦 " + t for t in TABS])
idx = {n: i for i, n in enumerate(TABS)}

# Overview
with pages[idx["Overview"]]:
    st.subheader(f"Overview – {MAIN}")
    cols = st.columns(5 if map_cols["views"] else 4)
    cols[0].metric("Avg Likes", f"{df_main[map_cols['likes']].mean():.1f}")
    cols[1].metric("Avg Replies", f"{df_main[map_cols['replies']].mean():.1f}")
    cols[2].metric("Avg Reposts", f"{df_main[map_cols['reposts']].mean():.1f}")
    if map_cols["views"]:
        cols[3].metric("Avg Views", f"{df_main[map_cols['views']].mean():.1f}")
        cols[4].metric("Avg Eng.%", f"{df_main['eng_rate_%'].mean():.2f}%")
    else:
        cols[3].metric("Avg Interactions", f"{df_main['total_interactions'].mean():.1f}")

# Top‑10
with pages[idx["Top 10"]]:
    st.subheader("Top 10 Tweets – " + MAIN)
    t10 = df_main.sort_values("total_interactions", ascending=False).head(10)
    cols_show = [map_cols["content"], "date_time", map_cols["likes"], map_cols["replies"], map_cols["reposts"], "total_interactions"]
    if map_cols["views"]:
        cols_show += [map_cols["views"], "eng_rate_%"]
    st.dataframe(t10[cols_show])

# Compare
if "Compare" in TABS:
    with pages[idx["Compare"]]:
        st.subheader("Compare brands")
        combined = pd.concat([df_main, df_comp])
        agg = combined.groupby("brand").agg(tweets=(map_cols["likes"], "count"), avg_interactions=("total_interactions", "mean")).reset_index()
        st.dataframe(agg)

# Raw
with pages[idx["Raw"]]:
    st.subheader("Raw & download")
    st.dataframe(df_main)
    st.download_button("Download enriched CSV", df_main.to_csv(index=False).encode(), "enriched_x.csv")
    if not df_comp.empty:
        st.download_button("Download competitor CSV", df_comp.to_csv(index=False).encode(), "competitor_x.csv")

# End

