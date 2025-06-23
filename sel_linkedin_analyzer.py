"""
LinkedIn / Multi‑Social CSV Analyzer
===================================
Streamlit app to analyse LinkedIn‑style CSV exports for a **main brand** and
optionally a **competitor file**. Tabs: Overview · Compare · Top‑10 · Google
Insight · Raw.
Last update: 2025‑06‑24 – fixed Google Insight block and syntax errors.
"""

import streamlit as st
import pandas as pd
import altair as alt
from datetime import timedelta

st.set_page_config(page_title="Universal Social Analyzer", layout="wide")
st.title("📊 Universal Social CSV Analyzer – with Competitor Benchmark")

# ───────────────────────────────────── Uploads ──────────────────────────────────────
main_file = st.sidebar.file_uploader("Upload MAIN brand CSV", type="csv", key="main")
if main_file is None:
    st.info("⬅️ Upload your main brand CSV to start.")
    st.stop()

comp_file = st.sidebar.file_uploader("Upload competitor CSV (optional)", type="csv", key="comp")

df_main = pd.read_csv(main_file)
df_comp = pd.read_csv(comp_file) if comp_file else pd.DataFrame()

# ─────────────────────────────────── Column mapping ──────────────────────────────────
ALIASES = {
    "likes": ["likecount", "likes", "favorite_count", "reactioncount"],
    "comments": ["commentcount", "comments", "reply_count"],
    "reposts": ["repostcount", "shares", "retweet_count"],
    "content": ["postcontent", "text", "message", "caption"],
    "url": ["posturl", "url", "link"],
    "timestamp": ["posttimestamp", "created_at", "createdtime", "created_time", "timestamp", "date"],
    "author": ["author", "pagename", "company", "account"],
}

def auto(col_list, key):
    lower = [c.lower() for c in col_list]
    for alias in ALIASES[key]:
        if alias in lower:
            return col_list[lower.index(alias)]
    return None

cols_main = df_main.columns.tolist()
map_cols = {k: auto(cols_main, k) for k in ALIASES}

st.sidebar.header("Map columns (MAIN CSV)")
for k, label in zip(
    ["likes", "comments", "reposts", "content", "url", "timestamp", "author"],
    ["Likes", "Comments", "Reposts", "Content", "URL (opt.)", "Timestamp (opt.)", "Author"]):
    opts = [None] + cols_main
    idx_default = opts.index(map_cols[k]) if map_cols[k] else 0
    map_cols[k] = st.sidebar.selectbox(label, opts, index=idx_default, key=k)

if None in [map_cols[c] for c in ("likes", "comments", "reposts", "author")]:
    st.error("Please map at least likes, comments, reposts and author.")
    st.stop()

# ────────────────────────────── Helper: enrich dataframe ─────────────────────────────

def enrich(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    # numeric clean
    for col in (map_cols["likes"], map_cols["comments"], map_cols["reposts"]):
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)
    df["total_interactions"] = df[[map_cols["likes"], map_cols["comments"], map_cols["reposts"]]].sum(axis=1)

    # timestamp
    if map_cols["timestamp"] and map_cols["timestamp"] in df.columns:
        ts = map_cols["timestamp"]
        df[ts] = pd.to_datetime(df[ts], errors="coerce")
        df["date_time"] = df[ts].dt.strftime("%Y-%m-%d %H:%M")
    else:
        df["date_time"] = "NA"

    # topic flag
    df["google_topic"] = df[map_cols["content"]].astype(str).str.contains("google", case=False, na=False)
    return df

df_main = enrich(df_main)
df_comp = enrich(df_comp) if not df_comp.empty else pd.DataFrame()

MAIN_BRAND = df_main[map_cols["author"]].mode()[0]

df_main["brand"] = MAIN_BRAND
if not df_comp.empty:
    df_comp["brand"] = df_comp[map_cols["author"]]

# ───────────────────────────────────── Tabs ────────────────────────────────────────
TABS = ["Overview", "Top 10", "Google Insight"]
if not df_comp.empty:
    TABS.insert(1, "Compare")
TABS.append("Raw")

pages = st.tabs(["📊 " + t for t in TABS])
idx = {name: i for i, name in enumerate(TABS)}

# ─────────────────────────────── Overview tab ──────────────────────────────────────
with pages[idx["Overview"]]:
    st.subheader(f"Overview – {MAIN_BRAND}")
    a, b, c, d = st.columns(4)
    a.metric("Avg Likes", f"{df_main[map_cols['likes']].mean():.1f}")
    b.metric("Avg Comments", f"{df_main[map_cols['comments']].mean():.1f}")
    c.metric("Avg Reposts", f"{df_main[map_cols['reposts']].mean():.1f}")
    d.metric("Avg Interactions", f"{df_main['total_interactions'].mean():.1f}")

    st.markdown("#### Scatter: Comments vs Total interactions (Google color)")
    st.altair_chart(
        alt.Chart(df_main).mark_circle(size=60, opacity=0.6).encode(
            x="total_interactions",
            y=map_cols["comments"],
            color="google_topic:N",
            tooltip=[map_cols["content"], "total_interactions", map_cols["comments"]],
        ).interactive(),
        use_container_width=True,
    )

# ─────────────────────────────── Compare tab ──────────────────────────────────────
if "Compare" in TABS:
    with pages[idx["Compare"]]:
        st.subheader("Compare brands")
        combined = pd.concat([df_main, df_comp], ignore_index=True)

        agg = combined.groupby("brand").agg(
            posts=(map_cols["likes"], "count"),
            avg_likes=(map_cols["likes"], "mean"),
            avg_comments=(map_cols["comments"], "mean"),
            avg_reposts=(map_cols["reposts"], "mean"),
            avg_total=("total_interactions", "mean"),
        ).reset_index()

        if map_cols["timestamp"] and map_cols["timestamp"] in combined.columns:
            span = (combined[map_cols["timestamp"]].max() - combined[map_cols["timestamp"]].min()).days / 7
            span = max(span, 1)
            agg["posts_per_week"] = agg["posts"] / span

        hl = lambda row: ["background-color:#dfe6fd" if row["brand"] == MAIN_BRAND else "" for _ in row]
        fmts = {c: "{:.1f}" for c in agg.columns if c != "brand"}
        st.dataframe(agg.style.apply(hl, axis=1).format(fmts), use_container_width=True)

# ─────────────────────────────── Top‑10 tab ──────────────────────────────────────
with pages[idx["Top 10"]]:
    st.subheader(f"Top 10 posts – {MAIN_BRAND}")
    top10 = df_main.sort_values("total_interactions", ascending=False).head(10).copy()

    def linkify(r):
        if map_cols["url"] and pd.notna(r[map_cols["url"]]):
            return f"<a href='{r[map_cols['url']]}' target='_blank'>{str(r[map_cols['content']])[:80]}</a>"
        return str(r[map_cols["content"]])[:80]

    top10["Post"] = top10.apply(linkify, axis=1)
    show_cols = ["Post", "date_time", map_cols["likes"], map_cols["comments"], map_cols["reposts"], "total_interactions", "google_topic"]
    st.write(top10[show_cols].to_html(escape=False), unsafe_allow_html=True)

# ─────────────────────────────── Google Insight ───────────────────────────────────
with pages[idx["Google Insight"]]:
    st.subheader(f"Google topic insight – {MAIN_BRAND}")

    high = df_main[df_main["total_interactions"] >= 10]
    low = df_main[df_main["total_interactions"] < 10]

    g_high = high[high["google_topic"]]
    ng_high = high[~high["google_topic"]]
    g_low = low[low["google_topic"]]
    ng_low = low[~low[
