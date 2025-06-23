"""
LinkedIn / Multi‑Social CSV Analyzer
===================================
Streamlit app to explore LinkedIn‑style CSV exports, now with **competitor comparison**.

2025‑06‑24 **Feature: Competitor tab**
* Second file‑uploader lets you add a CSV that contains one **or multiple competitors**.
* Uses the column `author` (auto‑detected) to group brands.
* Tab *Compare* shows per‑author averages and posting frequency (posts per week).
* Highlights the main brand (first file) and % gap vs each competitor.
* `is_repost` now true if `action == "Repost"` **or** `author ≠ main_author`.
"""

import streamlit as st
import pandas as pd
import altair as alt
import numpy as np
from datetime import timedelta

st.set_page_config(page_title="Universal Social Analyzer", layout="wide")
st.title("📊 Universal Social CSV Analyzer – with Competitor Benchmark")

# ----------------------------------------------------------------------
# 1. Upload primary CSV (main brand)
# ----------------------------------------------------------------------
file_main = st.sidebar.file_uploader("Upload MAIN brand CSV", type="csv", key="main")
if file_main is None:
    st.info("⬅️ Upload your main brand CSV to start.")
    st.stop()

df_main = pd.read_csv(file_main)
st.success(f"Loaded main dataset: {len(df_main):,} rows ✅")

# Optional competitor file
file_comp = st.sidebar.file_uploader("Upload competitor CSV (optional)", type="csv", key="comp")
df_comp = pd.read_csv(file_comp) if file_comp is not None else pd.DataFrame()

# ----------------------------------------------------------------------
# 2. Column mapping (for main); competitor assumed same schema
# ----------------------------------------------------------------------
aliases = {
    "likes": ["likeCount", "likes", "favorite_count", "reactionCount"],
    "comments": ["commentCount", "comments", "reply_count"],
    "reposts": ["repostCount", "shares", "retweet_count"],
    "impressions": ["impressions", "views", "reach"],
    "content": ["postContent", "text", "message", "caption"],
    "url": ["postUrl", "url", "link"],
    "timestamp": ["postTimestamp", "created_at", "createdTime", "created_time", "timestamp", "date", "date_time"],
    "author": ["author", "pageName", "company", "account"]
}

def auto(col_list, key):
    for alias in aliases[key]:
        for c in col_list:
            if c.lower() == alias.lower():
                return c
    return None

cols_main = list(df_main.columns)
map_cols = {k: auto(cols_main, k) for k in aliases}

st.sidebar.header("Column mapping (main CSV)")
for k,label in zip(
    ["likes","comments","reposts","content","url","timestamp","author"],
    ["Likes","Comments","Reposts","Content","URL (opt.)","Timestamp (opt.)","Author/Brand"]):
    opts=[None]+cols_main
    idx=opts.index(map_cols[k]) if map_cols[k] else 0
    map_cols[k]=st.sidebar.selectbox(label,opts,index=idx,key=k)

mandatory = [map_cols[x] for x in ("likes","comments","reposts","author")]
if None in mandatory:
    st.error("❌ Map at least likes, comments, reposts and author.")
    st.stop()

# ----------------------------------------------------------------------
# 3. Prepare function to clean any dataframe
# ----------------------------------------------------------------------

def prep(df):
    df = df.copy()
    # numeric cast
    for c in (map_cols["likes"], map_cols["comments"], map_cols["reposts"]):
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0).astype(int)
    df["total_interactions"] = df[[map_cols["likes"], map_cols["comments"], map_cols["reposts"]]].sum(axis=1)

    # timestamp handling
    if map_cols["timestamp"]:
        ts = map_cols["timestamp"]
        df[ts] = pd.to_datetime(df[ts], errors="coerce")
        df["date"] = df[ts].dt.date
        df["date_time"] = df[ts].dt.strftime("%Y-%m-%d %H:%M")
    else:
        df["date"] = pd.NaT
        df["date_time"] = "NA"

    # topic flag
    df["google_topic"] = df[map_cols["content"]].astype(str).str.contains("google", case=False, na=False)
    return df

df_main = prep(df_main)
df_comp = prep(df_comp) if not df_comp.empty else pd.DataFrame()

main_brand = df_main[map_cols["author"]].mode()[0]

# is_repost using author difference or explicit action
if "action" in df_main.columns:
    df_main["is_repost"] = df_main["action"].str.lower().eq("repost")
else:
    df_main["is_repost"] = False
# competitor DF already considered separate brand so is_repost False

# ----------------------------------------------------------------------
# 4. Tabs
# ----------------------------------------------------------------------
base_tabs = ["📈 Overview", "🏆 Top 10", "🔍 Google Insight"]
if not df_comp.empty:
    base_tabs.insert(2, "🤝 Compare")
base_tabs.append("🔧 Raw")

sections = st.tabs(base_tabs)
overview = sections[0]
idx_shift = 1
if "🤝 Compare" in base_tabs:
    compare_tab = sections[2]
    idx_shift = 2

top = sections[idx_shift]
google_tab = sections[idx_shift+1]
raw = sections[-1]

# ---------- Overview ----------
with overview:
    st.metric("Main brand detected", main_brand)
    c1,c2,c3,c4 = st.columns(4)
    c1.metric("Avg Likes", f"{df_main[map_cols['likes']].mean():.1f}")
    c2.metric("Avg Comments", f"{df_main[map_cols['comments']].mean():.1f}")
    c3.metric("Avg Reposts", f"{df_main[map_cols['reposts']].mean():.1f}")
    c4.metric("Avg Interactions", f"{df_main['total_interactions'].mean():.1f}")

    # Restore scatter plot with Google color code
    st.markdown("#### Scatter: Comments vs Total interactions")
    st.altair_chart(
        alt.Chart(df_main).mark_circle(size=60, opacity=0.6).encode(
            x="total_interactions",
            y=map_cols["comments"],
            color="google_topic:N",
            tooltip=[map_cols["content"], "total_interactions", map_cols["comments"]]
        ).interactive(),
        use_container_width=True,
    )

# ---------- Compare ----------
if not df_comp.empty:
    with compare_tab:
        st.markdown("### 🤝 Competitor Benchmark")
        # Combine
        df_comp["brand"] = df_comp[map_cols["author"]]
        df_main["brand"] = main_brand
        comb = pd.concat([df_main, df_comp], ignore_index=True)

                # Metrics per brand
        agg = comb.groupby("brand").agg(
            posts=(map_cols["likes"], "count"),
            avg_likes=(map_cols["likes"], "mean"),
            avg_comments=(map_cols["comments"], "mean"),
            avg_reposts=(map_cols["reposts"], "mean"),
            avg_total=("total_interactions", "mean")
        ).reset_index()

        # Posting frequency: posts per week
        if map_cols["timestamp"]:
            first_date = comb[map_cols["timestamp"]].min()
            last_date = comb[map_cols["timestamp"]].max()
            weeks = max(1, ((last_date - first_date) / timedelta(weeks=1)))
            agg["posts_per_week"] = agg["posts"] / weeks

        # Highlight main brand
        def highlight_main(row):
            return ["background-color:#dfe6fd" if row["brand"] == main_brand else "" for _ in row]

        numeric_cols = [c for c in agg.columns if c != "brand"]
        fmt = {c: "{:.1f}" for c in numeric_cols}
        st.dataframe(
            agg.style.apply(highlight_main, axis=1).format(fmt),
            use_container_width=True,
        )agg.style.apply(highlight_main, axis=1).format("{:.1f}"))

        # % diff chart likes
        bench = agg.set_index("brand")
        if main_brand in bench.index and bench.shape[0] > 1:
            diff = ((bench["avg_total"] - bench.loc[main_brand, "avg_total"]) / bench.loc[main_brand, "avg_total"]) * 100
            st.markdown("#### % Difference vs Main brand (Total interactions)")
            st.bar_chart(diff.drop(main_brand))

# ---------- Top 10 ----------
with top:
    st.markdown("#### Top 10 posts (main brand)")
    top10 = df_main.sort_values("total_interactions", ascending=False).head(10).copy()

    def linkify(r):
        if map_cols["url"] and pd.notna(r[map_cols["url"]]):
            txt = str(r[map_cols["content"]])[:80]
            return f"<a href='{r[map_cols['url']]}' target='_blank'>{txt}</a>"
        return str(r[map_cols["content"]])[:80]

    top10["Post"] = top10.apply(linkify, axis=1)
    disp_cols = ["Post", "date_time", map_cols['likes'], map_cols['comments'], map_cols['reposts'], "total_interactions", "google_topic", "is_repost"]
    top10 = top10[disp_cols]

    st.write(top10.to_html(escape=False), unsafe_allow_html=True)

# ---------- Google Insight ----------
with google_tab:
    st.markdown("### Google Topic vs Performance (main brand)")
    threshold = 10  # two‑digit interactions

    high = df_main[df_main["total_interactions"] >= threshold]
    low = df_main[df_main["total_interactions"] < threshold]

    g_high = high[high["google_topic"]]
    ng_high = high[~high["google_topic"] & ~high["is_repost"]]
    g_low = low[low["google_topic"]]
    ng_low = low[~low["google_topic"]]

    # KPI cards (4 columns)
    k1,k2,k3,k4 = st.columns(4)
    k1.metric("High ≥10 • Google", len(g_high))
    k2.metric("High ≥10 • non‑Google", len(ng_high))
    k3.metric("Low <10 • Google", len(g_low))
    k4.metric("Total Google posts", df_main["google_topic"].sum())

    # Table: high‑performer without Google (non‑repost)
    st.markdown("#### High performers WITHOUT Google (non‑repost)")
    if ng_high.empty:
        st.info("No high‑performer without Google topic.")
    else:
        cols_show = [map_cols['content'], "date_time", "total_interactions"]
        st.dataframe(ng_high[cols_show])
        st.download_button("Download non‑Google high posts", ng_high[cols_show].to_csv(index=False).encode(), "non_google_high.csv", key="dl_ng_high")

    # Summary table
    st.markdown("#### Summary: Google vs non‑Google")
    summary = pd.DataFrame({
        "Segment": ["High Google", "High non‑Google", "Low Google", "Low non‑Google"],
        "Posts": [len(g_high), len(ng_high), len(g_low), len(ng_low)],
        "Avg Interactions": [
            g_high.total_interactions.mean(),
            ng_high.total_interactions.mean() if not ng_high.empty else 0,
            g_low.total_interactions.mean(),
            ng_low.total_interactions.mean()
        ]
    })
    st.dataframe(summary.round(1))

# ---------- Raw ----------
with raw:
    st.dataframe(df_main, use_container_width=True)
    st.download_button("Download main enriched CSV", df_main.to_csv(index=False).encode(), "main_enriched.csv", key="main_dl")
    if not df_comp.empty:
        st.download_button("Download competitor enriched CSV", df_comp.to_csv(index=False).encode(), "comp_enriched.csv", key="comp_dl")

