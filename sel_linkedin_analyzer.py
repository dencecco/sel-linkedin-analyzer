"""
LinkedIn / Multi‑Social CSV Analyzer
===================================
Streamlit app to explore LinkedIn‑style CSV exports, now with **competitor comparison**.
Last updated: 2025‑06‑24 — fixed styling error in Compare tab.
"""

import streamlit as st
import pandas as pd
import altair as alt
from datetime import timedelta

st.set_page_config(page_title="Universal Social Analyzer", layout="wide")
st.title("📊 Universal Social CSV Analyzer – with Competitor Benchmark")

# ---------------------------------------------------------------------
# 1. Uploads
# ---------------------------------------------------------------------
main_file = st.sidebar.file_uploader("Upload MAIN brand CSV", type="csv", key="main")
if main_file is None:
    st.info("⬅️ Upload your main brand CSV to start.")
    st.stop()

comp_file = st.sidebar.file_uploader("Upload competitor CSV (optional)", type="csv", key="comp")

df_main = pd.read_csv(main_file)
df_comp = pd.read_csv(comp_file) if comp_file else pd.DataFrame()

# ---------------------------------------------------------------------
# 2. Column mapping
# ---------------------------------------------------------------------
ALIASES = {
    "likes": ["likecount", "likes", "favorite_count", "reactioncount"],
    "comments": ["commentcount", "comments", "reply_count"],
    "reposts": ["repostcount", "shares", "retweet_count"],
    "content": ["postcontent", "text", "message", "caption"],
    "url": ["posturl", "url", "link"],
    "timestamp": ["posttimestamp", "created_at", "createdtime", "created_time", "timestamp", "date"],
    "author": ["author", "pagename", "company", "account"]
}

def auto(cols, key):
    for alias in ALIASES[key]:
        for c in cols:
            if c.lower() == alias:
                return c
    return None

cols_main = df_main.columns.tolist()
map_cols = {k: auto(cols_main, k) for k in ALIASES}

st.sidebar.header("Map columns (MAIN CSV)")
for k, label in zip(
    ["likes", "comments", "reposts", "content", "url", "timestamp", "author"],
    ["Likes", "Comments", "Reposts", "Content", "URL (opt.)", "Timestamp (opt.)", "Author"]):
    options = [None] + cols_main
    default = options.index(map_cols[k]) if map_cols[k] else 0
    map_cols[k] = st.sidebar.selectbox(label, options, index=default, key=k)

required = [map_cols[x] for x in ("likes", "comments", "reposts", "author")]
if None in required:
    st.error("Map at least likes, comments, reposts and author.")
    st.stop()

# ---------------------------------------------------------------------
# 3. Helper to clean dataframes
# ---------------------------------------------------------------------

def clean(df):
    df = df.copy()
    for col in (map_cols["likes"], map_cols["comments"], map_cols["reposts"]):
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)
    df["total"] = df[[map_cols["likes"], map_cols["comments"], map_cols["reposts"]]].sum(axis=1)

    if map_cols["timestamp"] and map_cols["timestamp"] in df.columns:
        ts = map_cols["timestamp"]
        df[ts] = pd.to_datetime(df[ts], errors="coerce")
        df["date_time"] = df[ts].dt.strftime("%Y-%m-%d %H:%M")
    else:
        df["date_time"] = "NA"

    df["google_topic"] = df[map_cols["content"]].astype(str).str.contains("google", case=False, na=False)
    return df

df_main = clean(df_main)
df_comp = clean(df_comp) if not df_comp.empty else pd.DataFrame()

MAIN_BRAND = df_main[map_cols["author"]].mode()[0]

df_main["brand"] = MAIN_BRAND
if not df_comp.empty:
    df_comp["brand"] = df_comp[map_cols["author"]]

# ---------------------------------------------------------------------
# 4. Tabs
# ---------------------------------------------------------------------
TAB_TITLES = ["Overview", "Top 10", "Google Insight"]
if not df_comp.empty:
    TAB_TITLES.insert(1, "Compare")
TAB_TITLES.append("Raw")

over_idx = 0
cmp_idx = 1 if "Compare" in TAB_TITLES else None
top_idx = cmp_idx + 1 if cmp_idx is not None else 1
ggl_idx = top_idx + 1
raw_idx = len(TAB_TITLES) - 1

containers = st.tabs([f"📊 {t}" for t in TAB_TITLES])

# -------- Overview --------
with containers[over_idx]:
    st.subheader("Overview – " + MAIN_BRAND)
    st.metric("Avg Likes", f"{df_main[map_cols['likes']].mean():.1f}")
    st.metric("Avg Comments", f"{df_main[map_cols['comments']].mean():.1f}")
    st.metric("Avg Reposts", f"{df_main[map_cols['reposts']].mean():.1f}")
    st.metric("Avg Interactions", f"{df_main['total'].mean():.1f}")

# -------- Compare --------
if cmp_idx is not None:
    with containers[cmp_idx]:
        st.subheader("Compare brands")
        combined = pd.concat([df_main, df_comp], ignore_index=True)

        agg = combined.groupby("brand").agg(
            posts = (map_cols["likes"], "count"),
            avg_likes = (map_cols["likes"], "mean"),
            avg_comments = (map_cols["comments"], "mean"),
            avg_reposts = (map_cols["reposts"], "mean"),
            avg_total = ("total", "mean")
        ).reset_index()

        # posts per week
        if map_cols["timestamp"] and map_cols["timestamp"] in combined.columns:
            span = (combined[map_cols["timestamp"]].max() - combined[map_cols["timestamp"]].min()) / timedelta(weeks=1)
            span = max(span, 1)
            agg["posts_per_week"] = agg["posts"] / span

        # highlight main
        def hl(row):
            return ["background-color:#dfe6fd" if row["brand"] == MAIN_BRAND else "" for _ in row]

        fmt = {col: "{:.1f}" for col in agg.columns if col != "brand"}
        styled = agg.style.apply(hl, axis=1).format(fmt)
        st.dataframe(styled, use_container_width=True)

# -------- Top 10 --------
with containers[top_idx]:
    st.subheader("Top 10 posts – " + MAIN_BRAND)
    top10 = df_main.sort_values("total", ascending=False).head(10)
    show_cols = [map_cols["content"], "date_time", map_cols["likes"], map_cols["comments"], map_cols["reposts"], "total", "google_topic"]
    st.dataframe(top10[show_cols])

# -------- Google Insight --------
with containers[ggl_idx]:
    st.subheader("Google topic insight – " + MAIN_BRAND)
    high = df_main[df_main["total"] >= 10]
    g_high = high[high["google_topic"]]
    st.metric("High performers about Google (>=10)", len(g_high))

# -------- Raw --------
with containers[raw_idx]:
    st.dataframe(df_main)
    st.download_button("Download main CSV", df_main.to_csv(index=False).encode(), "main_enriched.csv", key="d1")
    if not df_comp.empty:
        st.download_button("Download competitor CSV", df_comp.to_csv(index=False).encode(), "comp_enriched.csv", key="d2")
