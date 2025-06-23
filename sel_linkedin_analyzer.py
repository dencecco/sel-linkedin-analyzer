"""
LinkedIn / Multi‑Social CSV Analyzer
===================================
Streamlit app to explore social‑media CSV exports with automatic KPIs and Top‑10.

2025‑06‑23 **Hotfix**
* Removed duplicate `download_button` causing *StreamlitDuplicateElementId*.
* Single dataframe + CSV download in **Raw** tab (`key='csv_dl'`).
"""

import streamlit as st
import pandas as pd
import altair as alt
import numpy as np

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
# 2. Column mapping (auto + sidebar override)
# ----------------------------------------------------------------------
aliases = {
    "likes": ["likeCount", "likes", "favorite_count", "reactionCount"],
    "comments": ["commentCount", "comments", "reply_count"],
    "reposts": ["repostCount", "shares", "retweet_count"],
    "impressions": ["impressions", "views", "reach"],
    "content": ["postContent", "text", "message", "caption"],
    "url": ["postUrl", "url", "link"],
    "timestamp": ["postTimestamp", "created_at", "createdTime", "created_time", "timestamp", "date", "date_time"],
}

cols = list(df.columns)

def auto_match(key):
    for alias in aliases[key]:
        for c in cols:
            if c.lower() == alias.lower():
                return c
    return None

map_cols = {k: auto_match(k) for k in aliases}

st.sidebar.header("Column mapping")
for key, label in zip(
    ["likes", "comments", "reposts", "impressions", "content", "url", "timestamp"],
    ["Likes", "Comments", "Reposts", "Impressions (opt.)", "Content", "URL (opt.)", "Timestamp (opt.)"],
):
    opts = [None] + cols
    default = opts.index(map_cols[key]) if map_cols[key] else 0
    map_cols[key] = st.sidebar.selectbox(label, opts, index=default)

if None in [map_cols[k] for k in ("likes", "comments", "reposts")]:
    st.error("❌ Map at least likes, comments, and repost columns.")
    st.stop()

# ----------------------------------------------------------------------
# 3. Data preparation
# ----------------------------------------------------------------------
for col in (map_cols["likes"], map_cols["comments"], map_cols["reposts"]):
    df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)

df["total_interactions"] = df[[map_cols["likes"], map_cols["comments"], map_cols["reposts"]]].sum(axis=1)

if map_cols["timestamp"]:
    ts = map_cols["timestamp"]
    df[ts] = pd.to_datetime(df[ts], errors="coerce")
    df["date_time"] = df[ts].dt.strftime("%Y-%m-%d %H:%M")
else:
    df["date_time"] = "NA"

# Flag true reposts (not shares received)
if "action" in df.columns:
    # Rely solely on the metadata from the platform: "Repost" vs "Post"
    df["is_repost"] = df["action"].str.lower().eq("repost")
else:
    df["is_repost"] = False

# ----------------------------------------------------------------------
# 4. Tabs
# ----------------------------------------------------------------------

overview, top, raw = st.tabs(["📈 Overview", "🏆 Top 10", "🔧 Raw"])

with overview:
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Avg Likes", f"{df[map_cols['likes']].mean():.2f}")
    c2.metric("Avg Comments", f"{df[map_cols['comments']].mean():.2f}")
    c3.metric("Avg Reposts", f"{df[map_cols['reposts']].mean():.2f}")
    c4.metric("Avg Interactions", f"{df['total_interactions'].mean():.2f}")

    st.markdown("#### Scatter: Comments vs Total interactions")
    st.altair_chart(
        alt.Chart(df).mark_circle(size=60, opacity=0.6).encode(
            x="total_interactions",
            y=map_cols["comments"],
            tooltip=[map_cols["content"], "total_interactions", map_cols["comments"]],
        ).interactive(),
        use_container_width=True,
    )

with top:
    st.markdown("#### Top 10 posts by interactions")
    top10 = df.sort_values("total_interactions", ascending=False).head(10).copy()

    def hyperlink(row):
        if map_cols["url"] and pd.notna(row[map_cols["url"]]):
            text = str(row[map_cols["content"]])[:80]
            return f"<a href='{row[map_cols['url']]}' target='_blank'>{text}</a>"
        return str(row[map_cols["content"]])[:80]

    top10["Post"] = top10.apply(hyperlink, axis=1)

    disp_cols = ["Post", "date_time", map_cols["likes"], map_cols["comments"], map_cols["reposts"], "total_interactions", "is_repost"]
    top10 = top10[disp_cols]

    def grey(row):
        return ["background-color:#e0e0e0" if row["is_repost"] else "" for _ in row]

    style = (
        top10.style.apply(grey, axis=1)
        .hide(axis="columns", subset=["is_repost"])
        .format(precision=0, thousands=",")
        .set_properties(**{"text-align": "left"})
        .set_table_styles([{"selector": "th", "props": "text-align:left;"}])
    )

    st.write(style.to_html(escape=False), unsafe_allow_html=True)

with raw:
    st.dataframe(df, use_container_width=True)
    st.download_button(
        "Download enriched CSV",
        df.to_csv(index=False).encode(),
        "enriched_data.csv",
        key="csv_dl",
    )
