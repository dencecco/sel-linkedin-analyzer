"""
LinkedIn / Social CSV Analyzer
==============================

Streamlit web‑app to explore **any** social‑media CSV export (LinkedIn, X, FB, IG…)
with automatic KPIs, Top‑10 posts, and flexible column mapping.

### New features
* **Link column** (clickable) & **date‑time** shown in Top‑10 table.
* Extra tabs: _Overview_, _Top‑10_, _By Day‑of‑Week_, _By Month_, _Raw Data_.
* Auto‑detect common column names **or** let the user map columns via sidebar.

> Required metrics columns (or their aliases): likes, comments, reposts/retweets.  
> Optional: impressions/views.
"""

import streamlit as st
import pandas as pd
import altair as alt
from datetime import datetime
from io import StringIO

st.set_page_config(page_title="Universal Social Analyzer", layout="wide")
st.title("📊 Universal Social CSV Analyzer")

# ----------------------------------------------------------------------
# 1. File uploader
# ----------------------------------------------------------------------
file = st.sidebar.file_uploader("Upload your social CSV export", type="csv")
if file is None:
    st.info("⬅️ Upload a CSV to start.")
    st.stop()

df = pd.read_csv(file)
st.success(f"Loaded {len(df):,} rows ✅")

# ----------------------------------------------------------------------
# 2. Column mapping (auto + manual override)
# ----------------------------------------------------------------------

def suggest(col_names, aliases):
    for alias in aliases:
        for c in col_names:
            if alias.lower() == c.lower():
                return c
    return None

col_candidates = list(df.columns)
like_col     = suggest(col_candidates, ["likeCount", "likes", "favorite_count", "reactionCount"])
comment_col  = suggest(col_candidates, ["commentCount", "comments", "reply_count"])
repost_col   = suggest(col_candidates, ["repostCount", "shares", "retweet_count"])
imp_col      = suggest(col_candidates, ["impressions", "views", "reach"])
content_col  = suggest(col_candidates, ["postContent", "text", "message", "caption"])
url_col      = suggest(col_candidates, ["postUrl", "url", "link"])
stamp_col    = suggest(col_candidates, ["postTimestamp", "created_at", "timestamp", "date"])

st.sidebar.markdown("### Column mapping (edit if auto‑detect is wrong)")
like_col    = st.sidebar.selectbox("Likes column",     options=[None]+col_candidates, index=col_candidates.index(like_col) if like_col else 0)
comment_col = st.sidebar.selectbox("Comments column", options=[None]+col_candidates, index=col_candidates.index(comment_col) if comment_col else 0)
repost_col  = st.sidebar.selectbox("Reposts/Shares",  options=[None]+col_candidates, index=col_candidates.index(repost_col) if repost_col else 0)
imp_col     = st.sidebar.selectbox("Impressions (opt.)", options=[None]+col_candidates, index=col_candidates.index(imp_col) if imp_col else 0)
content_col = st.sidebar.selectbox("Content column",  options=[None]+col_candidates, index=col_candidates.index(content_col) if content_col else 0)
url_col     = st.sidebar.selectbox("URL column (opt.)", options=[None]+col_candidates, index=col_candidates.index(url_col) if url_col else 0)
stamp_col   = st.sidebar.selectbox("Timestamp column (opt.)", options=[None]+col_candidates, index=col_candidates.index(stamp_col) if stamp_col else 0)

metric_cols = [like_col, comment_col, repost_col]
if None in metric_cols:
    st.error("❌ Please map at least like, comment, and repost columns.")
    st.stop()

# ----------------------------------------------------------------------
# 3. Normalization & derived fields
# ----------------------------------------------------------------------
for col in metric_cols:
    df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)

df["total_interactions"] = df[metric_cols].sum(axis=1)

if stamp_col:
    df[stamp_col] = pd.to_datetime(df[stamp_col], errors="coerce")
    df["date"] = df[stamp_col].dt.date
    df["weekday"] = df[stamp_col].dt.day_name()
    df["month"] = df[stamp_col].dt.to_period("M").astype(str)
else:
    df["weekday"] = "Unknown"
    df["month"] = "Unknown"

if imp_col:
    df[imp_col] = pd.to_numeric(df[imp_col], errors="coerce")
    df["eng_rate_%"] = (df["total_interactions"] / df[imp_col]) * 100

# ----------------------------------------------------------------------
# 4. UI – Tabs
# ----------------------------------------------------------------------

tab_overview, tab_top, tab_week, tab_month, tab_raw = st.tabs([
    "📈 Overview", "🏆 Top 10", "📅 By Weekday", "🗓 By Month", "📝 Raw data"
])

# ---------- Overview ----------
with tab_overview:
    k1,k2,k3,k4 = st.columns(4)
    k1.metric("Avg Likes",     f"{df[like_col].mean():.2f}")
    k2.metric("Avg Comments",  f"{df[comment_col].mean():.2f}")
    k3.metric("Avg Reposts",   f"{df[repost_col].mean():.2f}")
    k4.metric("Avg Interactions", f"{df['total_interactions'].mean():.2f}")

    # Correlation scatter
    st.markdown("#### Comment correlation")
    scatter = alt.Chart(df).mark_circle(size=60, opacity=0.6).encode(
        x="total_interactions",
        y=comment_col,
        tooltip=[content_col, "total_interactions", comment_col]
    ).interactive().properties(height=400)
    st.altair_chart(scatter, use_container_width=True)

# ---------- Top‑10 ----------
with tab_top:
    st.markdown("#### Top 10 posts by total interactions")
    top10 = df.sort_values("total_interactions", ascending=False).head(10).copy()

    # Add clickable link and date‑time
    if url_col:
        top10["link"] = top10[url_col].apply(lambda x: f"🔗 [Open]({x})" if pd.notna(x) else "")
    if stamp_col:
        top10["date_time"] = top10[stamp_col].astype(str)

    display_cols = [
        "link" if url_col else None,
        "date_time" if stamp_col else None,
        content_col,
        like_col, comment_col, repost_col, "total_interactions"
    ]
    display_cols = [c for c in display_cols if c]

    st.dataframe(top10[display_cols], use_container_width=True)

# ---------- By Weekday ----------
with tab_week:
    st.markdown("#### Average interactions by weekday")
    week_df = (df.groupby("weekday")[[like_col, comment_col, repost_col, "total_interactions"]]
                 .mean().round(2).reset_index())
    st.dataframe(week_df)
    bar = alt.Chart(week_df).mark_bar().encode(
        x="weekday",
        y="total_interactions",
        tooltip=["total_interactions"]
    )
    st.altair_chart(bar, use_container_width=True)

# ---------- By Month ----------
with tab_month:
    st.markdown("#### Total interactions by month")
    month_df = (df.groupby("month")[["total_interactions"]].sum().reset_index())
    st.dataframe(month_df)
    line = alt.Chart(month_df).mark_line(point=True).encode(
        x="month",
        y="total_interactions"
    )
    st.altair_chart(line, use_container_width=True)

# ---------- Raw data ----------
with tab_raw:
    st.dataframe(df, use_container_width=True)
    st.download_button(
        label="Download enriched CSV",
        data=df.to_csv(index=False).encode("utf-8"),
        file_name="enriched_social_data.csv",
        mime="text/csv"
    )
