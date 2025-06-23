"""
X / Multi‑Social CSV Analyzer
============================
Streamlit app to analyse **X (Twitter)** CSV exports for a MAIN brand and
optionally a competitor file, mirroring the LinkedIn tool structure.
Tabs: Overview · Compare · Top‑10 · Google Insight · Raw.

Columns auto‑detected (case‑insensitive):
    • likes    → like_count, likes, favorite_count
    • replies  → reply_count, comments
    • reposts  → repost_count, retweet_count, shares
    • views    → view_count, view count, viewcount, impression_count, impressions
    • content  → text, tweet, message
    • url      → url, tweet_url
    • timestamp→ created_at, date, timestamp
    • author   → author, username, account
"""

import streamlit as st
import pandas as pd
import altair as alt
from datetime import timedelta

st.set_page_config(page_title="X Social Analyzer", layout="wide")
st.title("🐦 X (Twitter) CSV Analyzer – with Competitor Benchmark")

# ───────────────────────── Uploads ─────────────────────────
main_file = st.sidebar.file_uploader("Upload MAIN brand CSV", type="csv", key="main")
if main_file is None:
    st.info("⬅️ Upload your main brand CSV to start.")
    st.stop()
comp_file = st.sidebar.file_uploader("Upload competitor CSV (optional)", type="csv", key="comp")

df_main = pd.read_csv(main_file)
df_comp = pd.read_csv(comp_file) if comp_file else pd.DataFrame()

# ───────────────────────── Column mapping ─────────────────────────
ALIASES = {
    "likes"   : ["like_count", "likes", "favorite_count"],
    "comments": ["reply_count", "comments"],
    "reposts" : ["repost_count", "retweet_count", "shares"],
    "views"   : ["view_count", "view count", "viewcount", "impression_count", "impressions"],
    "content" : ["text", "tweet", "message"],
    "url"     : ["url", "tweet_url"],
    "timestamp": ["created_at", "date", "timestamp"],
    "author"  : ["author", "username", "account"],
}

def _norm(s: str) -> str:
    """Normalize header: lowercase, strip spaces, keep alnum only."""
    import re
    return re.sub(r"[^a-z0-9]", "", s.lower())

def auto(cols, key):
    norm_cols = [_norm(c) for c in cols]
    for alias in ALIASES[key]:
        norm_alias = _norm(alias)
        if norm_alias in norm_cols:
            return cols[norm_cols.index(norm_alias)]
        # also accept alias as substring of column
        for i, nc in enumerate(norm_cols):
            if norm_alias in nc or nc in norm_alias:
                return cols[i]
    return None

cols_main = df_main.columns.tolist()
map_cols = {k: auto(cols_main, k) for k in ALIASES}

st.sidebar.header("Map columns (MAIN CSV)")
for k, label in zip(
    ["likes", "comments", "reposts", "views", "content", "url", "timestamp", "author"],
    ["Likes", "Replies", "Reposts", "Views", "Content", "URL (opt.)", "Timestamp (opt.)", "Author"]):
    opts = [None] + cols_main
    idx = opts.index(map_cols[k]) if map_cols[k] else 0
    map_cols[k] = st.sidebar.selectbox(label, opts, index=idx, key=k)

# mandatory columns now exclude "views" (optional)
if None in [map_cols[c] for c in ("likes", "comments", "reposts", "author")]:
    st.error("Please map at least likes, replies, reposts and author columns.")
    st.stop()

if map_cols["views"] is None:
    st.warning("Views column not mapped – engagement rate will be skipped.")

# ───────────────────────── Enrich helper ─────────────────────────

def enrich(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for col in (map_cols["likes"], map_cols["comments"], map_cols["reposts"], map_cols["views"]):
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)

    df["total_interactions"] = df[[map_cols["likes"], map_cols["comments"], map_cols["reposts"]]].sum(axis=1)
    df["eng_rate_%"] = (df["total_interactions"] / df[map_cols["views"]]) * 100

    if map_cols["timestamp"] and map_cols["timestamp"] in df.columns:
        ts = map_cols["timestamp"]
        df[ts] = pd.to_datetime(df[ts], errors="coerce")
        df["date_time"] = df[ts].dt.strftime("%Y-%m-%d %H:%M")
    else:
        df["date_time"] = "NA"

    df["google_topic"] = df[map_cols["content"]].astype(str).str.contains("google", case=False, na=False)
    return df

df_main = enrich(df_main)
df_comp = enrich(df_comp) if not df_comp.empty else pd.DataFrame()

MAIN_BRAND = df_main[map_cols["author"]].mode()[0]
df_main["brand"] = MAIN_BRAND
if not df_comp.empty:
    df_comp["brand"] = df_comp[map_cols["author"]]

# ───────────────────────── Tabs setup ─────────────────────────
TABS = ["Overview", "Top 10", "Google Insight"]
if not df_comp.empty:
    TABS.insert(1, "Compare")
TABS.append("Raw")

pages = st.tabs(["🐦 " + t for t in TABS])
idx = {n: i for i, n in enumerate(TABS)}

# ───────── Overview ─────────
with pages[idx["Overview"]]:
    st.subheader(f"Overview – {MAIN_BRAND}")
    a, b, c, d, e = st.columns(5)
    a.metric("Avg Likes", f"{df_main[map_cols['likes']].mean():.1f}")
    b.metric("Avg Replies", f"{df_main[map_cols['comments']].mean():.1f}")
    c.metric("Avg Reposts", f"{df_main[map_cols['reposts']].mean():.1f}")
    d.metric("Avg Views", f"{df_main[map_cols['views']].mean():.1f}")
    e.metric("Avg Eng.%", f"{df_main['eng_rate_%'].mean():.2f}%")

    st.altair_chart(
        alt.Chart(df_main).mark_circle(size=60, opacity=0.6).encode(
            x="total_interactions", y=map_cols["views"], color="google_topic:N",
            tooltip=[map_cols["content"], "total_interactions", map_cols["views"]],
        ).interactive(), use_container_width=True
    )

# ───────── Compare ─────────
if "Compare" in TABS:
    with pages[idx["Compare"]]:
        st.subheader("Compare brands")
        combo = pd.concat([df_main, df_comp])
        agg = combo.groupby("brand").agg(
            posts=(map_cols["likes"], "count"),
            avg_views=(map_cols["views"], "mean"),
            avg_eng=("eng_rate_%", "mean"),
            avg_total=("total_interactions", "mean"),
        ).reset_index()
        st.dataframe(agg, use_container_width=True)

# ───────── Top‑10 ─────────
with pages[idx["Top 10"]]:
    st.subheader("Top 10 tweets – " + MAIN_BRAND)
    top10 = df_main.sort_values("total_interactions", ascending=False).head(10).copy()
    top10["Tweet"] = top10[map_cols["content"]].astype(str).str.slice(0, 80)
    st.table(top10[["Tweet", "date_time", map_cols["likes"], map_cols["comments"], map_cols["reposts"], map_cols["views"], "eng_rate_%"]])

# ───────── Google Insight ─────────
with pages[idx["Google Insight"]]:
    st.subheader("Google topic insight")
    hi = df_main[df_main["total_interactions"] >= 10]
    lo = df_main[df_main["total_interactions"] < 10]

    st.metric("High tweets about Google", int(hi[hi["google_topic"]].shape[0]))
    st.metric("High tweets non‑Google", int(hi[~hi["google_topic"]].shape[0]))

# ───────── Raw ─────────
with pages[idx["Raw"]]:
    st.subheader("Raw data & downloads")
    st.dataframe(df_main, use_container_width=True)

    st.download_button(
        label="Download main enriched CSV",
        data=df_main.to_csv(index=False).encode(),
        file_name="main_enriched_x.csv",
        key="dl_main",
    )

    if not df_comp.empty:
        st.download_button(
            label="Download competitor enriched CSV",
            data=df_comp.to_csv(index=False).encode(),
            file_name="comp_enriched_x.csv",
            key="dl_comp",
        )

# End of file
