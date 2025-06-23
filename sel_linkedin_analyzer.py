"""
LinkedIn / Multi‑Social CSV Analyzer
===================================

Streamlit app to inspect **any** social‑media CSV (LinkedIn, X, Facebook, IG …)
with KPIs, Top‑10 posts (link + date‑time), weekday/month views and comment‑interaction correlation.

### 2025‑06‑23 Update 2
* **Fix**: removed multiline f‑string causing `SyntaxError` on deploy.
* **Improved**: handles empty correlation gracefully (shows “N/A”).
"""

import streamlit as st
import pandas as pd
import altair as alt
import numpy as np
from pathlib import Path

st.set_page_config(page_title="Universal Social Analyzer", layout="wide")
st.title("📊 Universal Social CSV Analyzer")

# ----------------------------------------------------------------------
# 1. File uploader
# ----------------------------------------------------------------------
file = st.sidebar.file_uploader("Upload your social CSV export", type="csv")
if file is None:
    st.info("⬅️ Upload a CSV to start.")
    st.stop()

# Read CSV
try:
    df = pd.read_csv(file)
except Exception as e:
    st.error(f"Failed to read CSV: {e}")
    st.stop()

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

cols = list(df.columns)
like_col    = suggest(cols, ["likeCount", "likes", "favorite_count", "reactionCount"])
comment_col = suggest(cols, ["commentCount", "comments", "reply_count"])
repost_col  = suggest(cols, ["repostCount", "shares", "retweet_count"])
imp_col     = suggest(cols, ["impressions", "views", "reach"])
content_col = suggest(cols, ["postContent", "text", "message", "caption"])
url_col     = suggest(cols, ["postUrl", "url", "link"])
stamp_col   = suggest(cols, [
    "postTimestamp", "created_at", "createdTime", "created_time", "timestamp", "date", "date_time"
])

st.sidebar.header("Column mapping")
like_col    = st.sidebar.selectbox("Likes",     [None]+cols, index=cols.index(like_col) if like_col else 0)
comment_col = st.sidebar.selectbox("Comments", [None]+cols, index=cols.index(comment_col) if comment_col else 0)
repost_col  = st.sidebar.selectbox("Reposts",   [None]+cols, index=cols.index(repost_col) if repost_col else 0)
imp_col     = st.sidebar.selectbox("Impressions (opt.)", [None]+cols, index=cols.index(imp_col) if imp_col else 0)
content_col = st.sidebar.selectbox("Content",   [None]+cols, index=cols.index(content_col) if content_col else 0)
url_col     = st.sidebar.selectbox("URL (opt.)",[None]+cols, index=cols.index(url_col) if url_col else 0)
stamp_col   = st.sidebar.selectbox("Timestamp (opt.)", [None]+cols, index=cols.index(stamp_col) if stamp_col else 0)

metric_cols = [like_col, comment_col, repost_col]
if None in metric_cols:
    st.error("❌ Map at least likes, comments and repost columns.")
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
    df["date_time"] = df[stamp_col].dt.strftime("%Y-%m-%d %H:%M")
else:
    df["weekday"] = "Unknown"
    df["month"] = "Unknown"
    df["date_time"] = "NA"

if imp_col:
    df[imp_col] = pd.to_numeric(df[imp_col], errors="coerce")
    df["eng_rate_%"] = (df["total_interactions"] / df[imp_col]) * 100

# ----------------------------------------------------------------------
# 4. Tabs
# ----------------------------------------------------------------------

t_overview, t_top, t_week, t_month, t_raw = st.tabs([
    "📈 Overview", "🏆 Top 10", "📅 Weekday", "🗓 Month", "🔧 Raw"
])

# ---------- Overview ----------
with t_overview:
    c1,c2,c3,c4 = st.columns(4)
    c1.metric("Avg Likes", f"{df[like_col].mean():.2f}")
    c2.metric("Avg Comments", f"{df[comment_col].mean():.2f}")
    c3.metric("Avg Reposts", f"{df[repost_col].mean():.2f}")
    c4.metric("Avg Interactions", f"{df['total_interactions'].mean():.2f}")

    # Comments correlation
    try:
        pearson_r = np.corrcoef(df["total_interactions"], df[comment_col])[0,1]
        corr_text = f"Pearson r = {pearson_r:.2f}"
    except Exception:
        corr_text = "Pearson r = N/A"

    st.markdown(f"#### Comments vs Total interactions – {corr_text}")

    scatter = alt.Chart(df).mark_circle(size=60, opacity=0.6).encode(
        x="total_interactions",
        y=comment_col,
        tooltip=[content_col, "total_interactions", comment_col]
    ).interactive().properties(height=400)
    st.altair_chart(scatter, use_container_width=True)

# ---------- Top‑10 ----------
with t_top:
    st.markdown("#### Top 10 posts by interactions")
    top10 = df.sort_values("total_interactions", ascending=False).head(10).copy()

    if url_col:
        top10["link"] = top10[url_col].apply(lambda x: f"🔗 [Open]({x})" if pd.notna(x) else "")

    display_cols = [
        "link" if url_col else None,
        "date_time",
        content_col,
        like_col, comment_col, repost_col, "total_interactions"
    ]
    display_cols = [c for c in display_cols if c]
    st.dataframe(top10[display_cols], use_container_width=True)

# ---------- Weekday ----------
with t_week:
    st.markdown("#### Avg interactions by weekday")
    week_df = (df.groupby("weekday")[[like_col, comment_col, repost_col, "total_interactions"]]
                 .mean().round(2).reset_index())
    st.dataframe(week_df)
    st.altair_chart(alt.Chart(week_df).mark_bar().encode(
        x="weekday", y="total_interactions"), use_container_width=True)

# ---------- Month ----------
with t_month:
    st.markdown("#### Total interactions by month")
    month_df = (df.groupby("month")["total_interactions"].sum().reset_index())
    st.dataframe(month_df)
    st.altair_chart(alt.Chart(month_df).mark_line(point=True).encode(
        x="month", y="total_interactions"), use_container_width=True)

# ---------- Raw ----------
with t_raw:
    st.dataframe(df, use_container_width=True)
    st.download_button("Download enriched CSV", df.to_csv(index=False).encode(), "enriched_data.csv")
