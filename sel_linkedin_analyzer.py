"""
LinkedIn / Multi‑Social CSV Analyzer
===================================
Streamlit app to explore social‑media CSV exports with automatic KPIs, Top‑10,
**and a dedicated Google‑Topic Insight tab**.

2025‑06‑23 **Feature: Google Topic tab**
* New tab "🔍 Google Insight" checks whether posts that exceed a two‑digit
  interaction threshold (≥ 10) mention "Google" in the content.
* Shows counts & averages for:
  • High performers (≥10) with & without Google
  • Low performers (<10) with & without Google
* Flags any high‑performer (≥10, not repost) that does **not** contain Google.
* Download button for that filtered table.
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
    "timestamp": ["postTimestamp", "created_at", "createdTime", "created_time", "timestamp", "date", "date_time"],
}
cols = list(df.columns)

def auto(key):
    for a in aliases[key]:
        for c in cols:
            if c.lower() == a.lower():
                return c
    return None
map_cols = {k: auto(k) for k in aliases}

st.sidebar.header("Column mapping")
for k,label in zip(["likes","comments","reposts","impressions","content","url","timestamp"],
                   ["Likes","Comments","Reposts","Impressions (opt.)","Content","URL (opt.)","Timestamp (opt.)"]):
    opts=[None]+cols
    idx=opts.index(map_cols[k]) if map_cols[k] else 0
    map_cols[k]=st.sidebar.selectbox(label,opts,index=idx)

if None in [map_cols[x] for x in ("likes","comments","reposts")]:
    st.error("❌ Map at least likes, comments, reposts.")
    st.stop()

# ----------------------------------------------------------------------
# 3. Data prep
# ----------------------------------------------------------------------
for c in (map_cols["likes"], map_cols["comments"], map_cols["reposts"]):
    df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0).astype(int)

df["total_interactions"] = df[[map_cols["likes"], map_cols["comments"], map_cols["reposts"]]].sum(axis=1)

# timestamp & extras
if map_cols["timestamp"]:
    ts = map_cols["timestamp"]
    df[ts] = pd.to_datetime(df[ts], errors="coerce")
    df["date_time"] = df[ts].dt.strftime("%Y-%m-%d %H:%M")
else:
    df["date_time"] = "NA"

if "action" in df.columns:
    df["is_repost"] = df["action"].str.lower().eq("repost")
else:
    df["is_repost"] = False

# flag google topic
df["google_topic"] = df[map_cols["content"]].astype(str).str.contains("google", case=False, na=False)

# ----------------------------------------------------------------------
# 4. Tabs
# ----------------------------------------------------------------------
overview, top, google_tab, raw = st.tabs(["📈 Overview", "🏆 Top 10", "🔍 Google Insight", "🔧 Raw"])

# ---------- Overview ----------
with overview:
    c1,c2,c3,c4 = st.columns(4)
    c1.metric("Avg Likes", f"{df[map_cols['likes']].mean():.2f}")
    c2.metric("Avg Comments", f"{df[map_cols['comments']].mean():.2f}")
    c3.metric("Avg Reposts", f"{df[map_cols['reposts']].mean():.2f}")
    c4.metric("Avg Interactions", f"{df['total_interactions'].mean():.2f}")

    st.markdown("#### Scatter: Comments vs Total interactions")
    st.altair_chart(
        alt.Chart(df).mark_circle(size=60, opacity=0.6).encode(
            x="total_interactions", y=map_cols["comments"],
            tooltip=[map_cols["content"], "total_interactions", map_cols["comments"]],
            color="google_topic:N",
        ).interactive(), use_container_width=True)

# ---------- Top 10 ----------
with top:
    st.markdown("#### Top 10 posts by interactions")
    top10 = df.sort_values("total_interactions", ascending=False).head(10).copy()

    def linkify(r):
        if map_cols["url"] and pd.notna(r[map_cols["url"]]):
            txt = str(r[map_cols["content"]])[:80]
            return f"<a href='{r[map_cols['url']]}' target='_blank'>{txt}</a>"
        return str(r[map_cols["content"]])[:80]

    top10["Post"] = top10.apply(linkify, axis=1)
    disp_cols = ["Post", "date_time", map_cols['likes'], map_cols['comments'], map_cols['reposts'], "total_interactions", "google_topic", "is_repost"]
    top10 = top10[disp_cols]

    style = top10.style.apply(lambda r: ["background-color:#e0e0e0" if r["is_repost"] else "" for _ in r], axis=1)
    style = style.hide(axis="columns", subset=["is_repost"]).format(precision=0, thousands=",")
    st.write(style.to_html(escape=False), unsafe_allow_html=True)

    st.download_button("Download Top‑10 CSV", top10.drop(columns=["is_repost"]).to_csv(index=False).encode(), "top10_high_performers.csv", key="top10_dl")

# ---------- Google Insight ----------
with google_tab:
    st.markdown("### Google Topic vs Performance")
    threshold = 10
    high = df[df["total_interactions"] >= threshold]
    low = df[df["total_interactions"] < threshold]

    g_high = high[high["google_topic"]]
    ng_high = high[~high["google_topic"] & ~high["is_repost"]]
    g_low = low[low["google_topic"]]

    colA, colB, colC, colD = st.columns(4)
    colA.metric("High (≥10) • Google", len(g_high))
    colB.metric("High (≥10) • non‑Google", len(ng_high))
    colC.metric("Low (<10) • Google", len(g_low))
    colD.metric("Total Google posts", df["google_topic"].sum())

    st.markdown("#### High performers without Google (not reposts)")
    if ng_high.empty:
        st.info("Every high‑performer references Google or is a repost.")
    else:
        ng_cols = [map_cols['content'], "date_time", "total_interactions"]
        st.dataframe(ng_high[ng_cols])
        st.download_button("Download non‑Google high posts", ng_high[ng_cols].to_csv(index=False).encode(), "non_google_high.csv", key="dl_ng_high")

    st.markdown("#### Overview table")
    summary = pd.DataFrame({
        "Segment": ["High Google", "High non‑Google (no repost)", "Low Google", "Low non‑Google"],
        "Posts": [len(g_high), len(ng_high), len(g_low), len(low) - len(g_low)],
        "Avg Interactions": [g_high.total_interactions.mean(), ng_high.total_interactions.mean() if not ng_high.empty else 0, g_low.total_interactions.mean(), (low[~low["google_topic"]]).total_interactions.mean()],
    })
    st.dataframe(summary.round(1))

# ---------- Raw ----------
with raw:
    st.dataframe(df, use_container_width=True)
    st.download_button("Download enriched CSV", df.to_csv(index=False).encode(), "enriched_data.csv", key="csv_dl")
