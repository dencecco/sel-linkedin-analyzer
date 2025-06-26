import re
import streamlit as st
import pandas as pd
import pandas.errors as pde

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

# Read dataframes
 df_main = safe_read(main_file)
 df_comp = safe_read(comp_file) if comp_file else pd.DataFrame()

# ── Column mapping for MAIN ─────────────────────────────────────────────────
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

def auto_map(cols, key):
    normed = [_norm(c) for c in cols]
    for alias in ALIASES[key]:
        na = _norm(alias)
        for i, n in enumerate(normed):
            if na == n or na in n or n in na:
                return cols[i]
    return None

# Map main columns
cols_main = df_main.columns.tolist()
map_main = {k: auto_map(cols_main, k) for k in ALIASES}
# Sidebar override
st.sidebar.header("Map columns (Main CSV)")
for key, label in zip(
    ["likes","replies","reposts","views","content","url","timestamp","author"],
    ["Likes","Replies","Reposts","Views (opt.)","Content","URL (opt.)","Timestamp (opt.)","Author"]
):
    opts = [None] + cols_main
    default = opts.index(map_main.get(key)) if map_main.get(key) in opts else 0
    map_main[key] = st.sidebar.selectbox(label, opts, index=default, key=key)
# Validate mandatory
for req in ("likes","replies","reposts","author"):
    if map_main[req] is None:
        st.error(f"Map the '{req}' column before proceeding.")
        st.stop()
# Ensure optional mappings exist as dummy
for opt in ("views","content","url","timestamp"):
    if map_main[opt] is None:
        map_main[opt] = f"_{opt}"

# ── Normalize competitor to same schema ──────────────────────────────────────
if not df_comp.empty:
    cols_comp = df_comp.columns.tolist()
    map_comp = {k: auto_map(cols_comp, k) for k in ALIASES}
    # Rename comp cols to main mapping names
    rename_dict = {}
    for k in ALIASES:
        src = map_comp.get(k)
        tgt = map_main[k]
        if src and src in df_comp.columns:
            rename_dict[src] = tgt
    df_comp = df_comp.rename(columns=rename_dict)
    # Add missing cols with zeros or NA
    for k in map_main:
        if map_main[k] not in df_comp.columns:
            df_comp[map_main[k]] = 0 if k in ("likes","replies","reposts","views") else pd.NA

# ── Enrichment ──────────────────────────────────────────────────────────────
def enrich(df, mapping):
    df = df.copy()
    # Numeric cast
    for k in ("likes","replies","reposts","views"):
        col = mapping[k]
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0).astype(int)
    # Total and rate
    df["total_interactions"] = df[mapping["likes"]] + df[mapping["replies"]] + df[mapping["reposts"]]
    df["eng_rate_%"] = df["total_interactions"] / df[mapping["views"]].replace({0: pd.NA}) * 100
    # Timestamp parse
    ts = mapping.get("timestamp")
    try:
        df[ts] = pd.to_datetime(df[ts], errors='coerce')
        df["date_time"] = df[ts].dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        df["date_time"] = "NA"
    return df

# Apply enrichment
df_main = enrich(df_main, map_main)
if not df_comp.empty:
    df_comp = enrich(df_comp, map_main)

# Label brands
MAIN_BRAND = df_main[map_main["author"]].mode()[0]
df_main["brand"] = MAIN_BRAND
if not df_comp.empty:
    df_comp["brand"] = df_comp[map_main["author"]]

# ── UI Tabs ─────────────────────────────────────────────────────────────────
tabs = ["Overview", "Compare" if not df_comp.empty else None, "Top 10", "Raw"]
tabs = [t for t in tabs if t]
pages = st.tabs([f"🐦 {t}" for t in tabs])
idx = {t: i for i, t in enumerate(tabs)}

# Overview
with pages[idx["Overview"]]:
    st.subheader(f"Overview – {MAIN_BRAND}")
    cols = st.columns(5)
    cols[0].metric("Avg Likes", f"{df_main[map_main['likes']].mean():.1f}")
    cols[1].metric("Avg Replies", f"{df_main[map_main['replies']].mean():.1f}")
    cols[2].metric("Avg Reposts", f"{df_main[map_main['reposts']].mean():.1f}")
    cols[3].metric("Avg Views", f"{df_main[map_main['views']].mean():.1f}")
    cols[4].metric("Avg Eng.%", f"{df_main['eng_rate_%'].mean():.2f}%")

# Compare
if not df_comp.empty:
    with pages[idx["Compare"]]:
        st.subheader("Compare brands")
        combined = pd.concat([df_main, df_comp], ignore_index=True)
        agg = combined.groupby("brand").agg(
            posts=(map_main['likes'], 'count'),
            avg_likes=(map_main['likes'], 'mean'),
            avg_replies=(map_main['replies'], 'mean'),
            avg_reposts=(map_main['reposts'], 'mean'),
            avg_total=("total_interactions", 'mean'),
            avg_views=(map_main['views'], 'mean'),
            avg_eng=("eng_rate_%", 'mean')
        ).reset_index()
        def hl(r): return ['background-color:#dfe6fd' if r['brand']==MAIN_BRAND else '' for _ in r]
        fmt = {c:"{:.1f}" for c in agg.columns if c!='brand' and c!='posts'}
        st.dataframe(agg.style.apply(hl, axis=1).format(fmt), use_container_width=True)

# Top 10
with pages[idx["Top 10"]]:
    st.subheader(f"Top 10 Tweets – {MAIN_BRAND}")
    t10 = df_main.nlargest(10, 'total_interactions').copy()
    if map_main['url']: 
        t10['Tweet'] = t10.apply(lambda r: f"<a href='{r[map_main['url']]}' target='_blank'>{str(r[map_main['content']])[:80]}</a>", axis=1)
        first = 'Tweet'
    else:
        first = map_main['content']
    cols_show = [first, 'date_time', map_main['likes'], map_main['replies'], map_main['reposts'], 'total_interactions', map_main['views'], 'eng_rate_%']
    st.write(t10[cols_show].to_html(escape=False), unsafe_allow_html=True)

# Raw & Download
with pages[idx["Raw"]]:
    st.subheader("Raw Data & Downloads")
    st.dataframe(df_main, use_container_width=True)
    st.download_button("Download enriched CSV", df_main.to_csv(index=False).encode(), "main_enriched_x.csv")
    if not df_comp.empty:
        st.download_button("Download competitor enriched CSV", df_comp.to_csv(index=False).encode(), "comp_enriched_x.csv")
