"""
LinkedIn / Multi‑Social CSV Analyzer
===================================

Streamlit app to inspect **any** social‑media CSV** (LinkedIn, X, Facebook, IG …)**
with KPIs, Top‑10, weekday/month views and comments‑vs‑interactions scatter.

**2025‑06‑23 Patch**
* Restored *clean* scatter (no Pearson text glitches).
* **Top‑10** now includes:
  * Date‑Time from `postTimestamp` (or mapped column)
  * Post text **hyper‑linked** (opens original post)
  * Grey highlight if the row is a *repost* (detected via `repostCount>0` **or** `action` column == "Repost").
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
# 2. Column mapping
# ----------------------------------------------------------------------

aliases = {
    "likes": ["likeCount", "likes", "favorite_count", "reactionCount"],
    "comments": ["commentCount", "comments", "reply_count"],
    "reposts": ["repostCount", "shares", "retweet_count"],
    "impressions": ["impressions", "views", "reach"],
    "content": ["postContent", "text", "message", "caption"],
    "url": ["postUrl", "url", "link"],
    "timestamp": ["postTimestamp", "created_at", "createdTime", "created_time", "timestamp", "date", "date_time"]
}

cols = list(df.columns)

def auto(alias_key):
    for a in aliases[alias_key]:
        for c in cols:
            if c.lower() == a.lower():
                return c
    return None

map_cols = {}
for key in aliases:
    map_cols[key] = auto(key)

st.sidebar.header("Column mapping")
for key,label in zip(["likes","comments","reposts","impressions","content","url","timestamp"],
                     ["Likes","Comments","Reposts","Impressions (opt.)","Content","URL (opt.)","Timestamp (opt.)"]):
    options=[None]+cols
    default_idx= options.index(map_cols[key]) if map_cols[key] else 0
    map_cols[key]= st.sidebar.selectbox(label, options,index=default_idx)

metric_cols = [map_cols["likes"], map_cols["comments"], map_cols["reposts"]]
if None in metric_cols:
    st.error("❌ Map at least likes, comments and repost columns.")
    st.stop()

# ----------------------------------------------------------------------
# 3. Data prep
# ----------------------------------------------------------------------
for col in metric_cols:
    df[col]= pd.to_numeric(df[col],errors='coerce').fillna(0).astype(int)

df["total_interactions"]= df[metric_cols].sum(axis=1)

# Timestamp handling
if map_cols["timestamp"]:
    ts_col= map_cols["timestamp"]
    df[ts_col]= pd.to_datetime(df[ts_col],errors='coerce')
    df["date_time"]= df[ts_col].dt.strftime("%Y-%m-%d %H:%M")
    df["weekday"]= df[ts_col].dt.day_name()
    df["month"]= df[ts_col].dt.to_period('M').astype(str)
else:
    df["date_time"]="NA"
    df["weekday"]="Unknown"
    df["month"]="Unknown"

# Repost flag (grey highlight when true)
if "action" in df.columns:
    df["is_repost"] = df["action"].str.lower().eq("repost") | (df[map_cols["reposts"]]>0)
else:
    df["is_repost"] = df[map_cols["reposts"]] > 0

# Engagement rate
if map_cols["impressions"]:
    imp_col= map_cols["impressions"]
    df[imp_col]= pd.to_numeric(df[imp_col],errors='coerce')
    df["eng_rate_%"]= (df["total_interactions"] / df[imp_col])*100

# ----------------------------------------------------------------------
# 4. Tabs
# ----------------------------------------------------------------------

t_overview,t_top,t_raw = st.tabs(["📈 Overview","🏆 Top 10","🔧 Raw"])

with t_overview:
    c1,c2,c3,c4 = st.columns(4)
    c1.metric("Avg Likes", f"{df[map_cols['likes']].mean():.2f}")
    c2.metric("Avg Comments", f"{df[map_cols['comments']].mean():.2f}")
    c3.metric("Avg Reposts", f"{df[map_cols['reposts']].mean():.2f}")
    c4.metric("Avg Interactions", f"{df['total_interactions'].mean():.2f}")

    st.markdown("#### Scatter: Comments vs Total interactions")
    scatter= alt.Chart(df).mark_circle(size=60,opacity=0.6).encode(
        x="total_interactions", y=map_cols["comments"],
        tooltip=[map_cols["content"],"total_interactions",map_cols["comments"]]
    ).interactive().properties(height=400)
    st.altair_chart(scatter,use_container_width=True)

with t_top:
    st.markdown("#### Top 10 posts by interactions")
    top10= df.sort_values("total_interactions",ascending=False).head(10).copy()

    # Hyper‑linked content
    if map_cols["url"] and map_cols["content"]:
        top10["Post"] = top10.apply(
            lambda row: f"[ {row[map_cols['content']][:80]} ]({row[map_cols['url']]})", axis=1
        )
    else:
        top10["Post"] = top10[map_cols["content"]].astype(str).str.slice(0,80)

    display_cols=["Post","date_time",map_cols['likes'],map_cols['comments'],map_cols['reposts'],"total_interactions"]

    # Style: grey if repost
    def highlight_repost(row):
        return ["background-color:#e0e0e0" if row["is_repost"] else "" for _ in row]

    styled= top10[display_cols+ ["is_repost"]].style.apply(highlight_repost,axis=1).hide_columns("is_repost")
    st.dataframe(styled,use_container_width=True)

with t_raw:
    st.dataframe(df,use_container_width=True)
    st.download_button("Download enriched CSV", df.to_csv(index=False).encode(),"enriched_data.csv")
