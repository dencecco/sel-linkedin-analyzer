import streamlit as st
import pandas as pd
import altair as alt

st.set_page_config(page_title="LinkedIn SEL Analyzer", layout="wide")
st.title("🔍 Search Engine Land – LinkedIn Performance Analyzer")

st.markdown(
"""
### How to use
1. Export your LinkedIn post data as **CSV**.
2. Upload the file with the widget on the left.
3. Read the automatic insights below (averages, top posts, comment correlation).

*Columns required:* `likeCount`, `commentCount`, `repostCount`  
*Optional:* `impressions` or `views` to compute engagement rate.
"""
)

# ---------- Sidebar – file upload ----------
csv_file = st.sidebar.file_uploader("📤 Upload LinkedIn CSV", type="csv")

if csv_file is None:
    st.info("⬅️ Upload a CSV file to start.")
    st.stop()

df = pd.read_csv(csv_file)

# Make sure numeric columns exist
for col in ["likeCount", "commentCount", "repostCount"]:
    if col not in df.columns:
        df[col] = 0
    df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)

df["total_interactions"] = df[["likeCount", "commentCount", "repostCount"]].sum(axis=1)

# ---------- KPI cards ----------
col1, col2, col3, col4 = st.columns(4)
col1.metric("Avg Likes",  round(df.likeCount.mean(), 2))
col2.metric("Avg Comments", round(df.commentCount.mean(), 2))
col3.metric("Avg Reposts",  round(df.repostCount.mean(), 2))
col4.metric("Avg Total Interactions", round(df.total_interactions.mean(), 2))

# ---------- Top 10 table ----------
top10 = df.sort_values("total_interactions", ascending=False).head(10)
st.subheader("🏆 Top 10 posts by total interactions")
st.dataframe(top10[["postContent", "likeCount", "commentCount", "repostCount", "total_interactions"]])

# ---------- Scatter: comments vs interactions ----------
st.subheader("💬 Do high-interaction posts also get many comments?")
scatter = alt.Chart(df).mark_circle(size=60).encode(
    x="total_interactions",
    y="commentCount",
    tooltip=["postContent", "total_interactions", "commentCount"]
).properties(height=400)
st.altair_chart(scatter, use_container_width=True)

# ---------- Engagement rate (if impressions present) ----------
if {"impressions", "views"}.intersection(df.columns):
    imp_col = "impressions" if "impressions" in df.columns else "views"
    df["eng_rate_%"] = (df.total_interactions / df[imp_col]) * 100
    st.subheader("📈 Engagement rate distribution")
    st.bar_chart(df["eng_rate_%"])
else:
    st.info("Engagement rate cannot be calculated – no impressions/views column found.")
