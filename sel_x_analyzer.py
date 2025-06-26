import re
import streamlit as st
import pandas as pd

# ── Page config ──────────────────────────────────────────────────────────
st.set_page_config(page_title="🐦 X CSV Analyzer – Enhanced", layout="wide")
st.title("🐦 X (Twitter) CSV Analyzer – Enhanced Edition")

# ── File uploads ─────────────────────────────────────────────────────────
main_file = st.sidebar.file_uploader("Upload MAIN brand CSV", type="csv", key="main")
if main_file is None:
    st.info("⬅️ Upload your main brand CSV to start.")
    st.stop()
comp_file = st.sidebar.file_uploader("Upload COMPETITOR CSV (optional)", type="csv", key="comp")

# ── Robust CSV reader ──────────────────────────────────────────────────────
import pandas.errors as pde

def safe_read(file):
    try:
        return pd.read_csv(file, low_memory=False)
    except pde.ParserError:
        file.seek(0)
        try:
            return pd.read_csv(file, sep=';', low_memory=False)
        except pde.ParserError:
            file.seek(0)
            return pd.read_csv(file, sep=None, engine='python', on_bad_lines='skip')

# read dataframes
df_main = safe_read(main_file)
df_comp = safe_read(comp_file) if comp_file else pd.DataFrame()

# ── Column mapping ─────────────────────────────────────────────────────────
ALIASES = {
    "likes":   ["like_count", "likes", "favorite_count", "likecount"],
    "replies": ["reply_count", "replies", "comments", "commentcount"],
    "reposts": ["retweet_count", "retweetcount", "repost_count", "shares"],
    "views":   ["view_count", "impression_count", "views", "impressions"],
    "content": ["text", "tweet", "message"],
    "url":     ["url", "tweet_url", "tweetlink"],
    "timestamp": ["created_at", "date", "timestamp"],
    "author":  ["author", "username", "account", "handle"]
}

def _norm(col):
    return re.sub(r"[^a-z0-9]", "", col.lower())

def auto(cols, key):
    normed = [_norm(c) for c in cols]
    for alias in ALIASES[key]:
        a = _norm(alias)
        for i,n in enumerate(normed):
            if a == n or a in n or n in a:
                return cols[i]
    return None

cols_main = df_main.columns.tolist()
map_cols = {k: auto(cols_main, k) for k in ALIASES}

st.sidebar.header("Map columns (MAIN CSV)")
for key,label in zip(
    ["likes","replies","reposts","views","content","url","timestamp","author"],
    ["Likes","Replies","Reposts","Views (opt.)","Content","URL (opt.)","Timestamp (opt.)","Author"]
):
    options = [None] + cols_main
    default = options.index(map_cols.get(key)) if map_cols.get(key) in options else 0
    map_cols[key] = st.sidebar.selectbox(label, options, index=default, key=key)

# require mandatory mappings
mandatory = ["likes","replies","reposts","author"]
if any(map_cols[k] is None for k in mandatory):
    st.error("Please map at least Likes, Replies, Reposts, and Author.")
    st.stop()

# ── Data enrichment ─────────────────────────────────────────────────────────
def enrich(df):
    df = df.copy()
    # ensure numeric
    for k in ["likes","replies","reposts","views"]:
        col = map_cols.get(k)
        if col and col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0).astype(int)
        else:
            # create zero column
            df[k] = 0
            map_cols[k] = k
    # total interactions
    df["total_interactions"] = df[map_cols["likes"]] + df[map_cols["replies"]] + df[map_cols["reposts"]]
    # engagement rate
    if map_cols.get("views") and map_cols["views"] in df.columns:
        df["eng_rate_%"] = (df["total_interactions"] / df[map_cols["views"]].replace({0: pd.NA})) * 100
    else:
        df["eng_rate_%"] = pd.NA
    # timestamp parsing
    ts = map_cols.get("timestamp")
    if ts and ts in df.columns:
        df[ts] = pd.to_datetime(df[ts], errors='coerce')
        df["date_time"] = df[ts].dt.strftime("%Y-%m-%d %H:%M")
    else:
        df["date_time"] = "NA"
    return df

# enrich dataframes
df_main = enrich(df_main)
df_comp = enrich(df_comp) if not df_comp.empty else pd.DataFrame()

# brand labeling
MAIN_BRAND = df_main[map_cols["author"]].mode()[0]
df_main["brand"] = MAIN_BRAND
if not df_comp.empty:
    if map_cols["author"] in df_comp.columns:
        df_comp["brand"] = df_comp[map_cols["author"]]
    else:
        df_comp["brand"] = "Competitor"

# ── Tabs ────────────────────────────────────────────────────────────────────
tabs = ["Overview", "Top 10"]
if not df_comp.empty:
    tabs.insert(1, "Compare")
tabs.append("Raw")
pages = st.tabs([f"🐦 {t}" for t in tabs])
idx = {name: i for i,name in enumerate(tabs)}

# Overview
with pages[idx["Overview"]]:
    st.subheader(f"Overview – {MAIN_BRAND}")
    cols = st.columns(5 if map_cols.get("views") else 4)
    cols[0].metric("Avg Likes", f"{df_main[map_cols['likes']].mean():.1f}")
    cols[1].metric("Avg Replies", f"{df_main[map_cols['replies']].mean():.1f}")
    cols[2].metric("Avg Reposts", f"{df_main[map_cols['reposts']].mean():.1f}")
    if map_cols.get("views"):
        cols[3].metric("Avg Views", f"{df_main[map_cols['views']].mean():.1f}")
        cols[4].metric("Avg Eng.%", f"{df_main['eng_rate_%'].mean():.2f}%")
    else:
        cols[3].metric("Avg Total Interactions", f"{df_main['total_interactions'].mean():.1f}")

# Compare\if not df_comp.empty:
    with pages[idx["Compare"]]:
        st.subheader("Compare brands")
        combo = pd.concat([df_main, df_comp], ignore_index=True)
        agg = combo.groupby("brand").agg(
            posts=(map_cols['likes'], 'count'),
            avg_likes=(map_cols['likes'], 'mean'),
            avg_replies=(map_cols['replies'], 'mean'),
            avg_reposts=(map_cols['reposts'], 'mean'),
            avg_total=('total_interactions', 'mean')
        ).reset_index()
        # add view/engage if available
        if map_cols.get('views') in combo.columns:
            agg['avg_views'] = combo.groupby('brand')[map_cols['views']].mean().values
            agg['avg_eng_%'] = combo.groupby('brand')['eng_rate_%'].mean().values
        # highlight
        def highlight(row):
            return ['background-color:#dfe6fd' if row.brand==MAIN_BRAND else '' for _ in row]
        fmt = {c:"{:.1f}" for c in agg.columns if c!='brand' and c!='posts'}
        st.dataframe(agg.style.apply(highlight, axis=1).format(fmt), use_container_width=True)

# Top 10
with pages[idx["Top 10"]]:
    st.subheader(f"Top 10 Tweets – {MAIN_BRAND}")
    top10 = df_main.sort_values('total_interactions', ascending=False).head(10).copy()
    # make clickable
    if map_cols.get('url') and map_cols['url'] in top10.columns:
        top10['Tweet'] = top10.apply(
            lambda r: f"<a href='{r[map_cols['url']]}' target='_blank'>{str(r[map_cols['content']])[:80]}</a>",
            axis=1
        )
        first = 'Tweet'
    else:
        first = map_cols['content']
    cols_show = [first, 'date_time', map_cols['likes'], map_cols['replies'], map_cols['reposts'], 'total_interactions']
    if map_cols.get('views'):
        cols_show += [map_cols['views'], 'eng_rate_%']
    st.write(top10[cols_show].to_html(escape=False), unsafe_allow_html=True)

# Raw & Download
with pages[idx["Raw"]]:
    st.subheader("Raw Data & Downloads")
    st.dataframe(df_main, use_container_width=True)
    st.download_button("Download enriched CSV", df_main.to_csv(index=False).encode(), "main_enriched_x.csv")
    if not df_comp.empty:
        st.download_button("Download competitor enriched CSV", df_comp.to_csv(index=False).encode(), "comp_enriched_x.csv")
