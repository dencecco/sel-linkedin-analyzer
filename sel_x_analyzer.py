"""
X / Social CSV Analyzer (minimal, fixed order)
===========================================
Streamlit app to inspect **X (Twitter)** CSV exports for a main brand plus
optional competitor file. Tabs: Overview · Top‑10 · (Compare) · Raw.
Views column is optional; engagement rate calculated only if present.
"""

import re, streamlit as st, pandas as pd, altair as alt, pandas.errors as pde

st.set_page_config(page_title="🐦 X CSV Analyzer", layout="wide")
st.title("🐦 X (Twitter) CSV Analyzer – minimal edition")

# ── Uploads ──────────────────────────────────────────────────────────
main_file = st.sidebar.file_uploader("Upload MAIN brand CSV", type="csv", key="main")
if main_file is None:
    st.info("⬅️ Upload a CSV to start")
    st.stop()
comp_file = st.sidebar.file_uploader("Upload COMPETITOR CSV (opt.)", type="csv", key="comp")

# robust reader (comma ; or auto)

def safe_read(file):
    try:
        return pd.read_csv(file, low_memory=False)
    except pde.ParserError:
        file.seek(0)
        try:
            return pd.read_csv(file, sep=";", low_memory=False)
        except pde.ParserError:
            file.seek(0)
            return pd.read_csv(file, sep=None, engine="python", on_bad_lines="skip")

df_main = safe_read(main_file)
df_comp = safe_read(comp_file) if comp_file else pd.DataFrame()

# ── Column mapping ─────────────────────────────────────────────────
ALIASES = {
    "likes":   ["like_count", "likes", "favorite_count", "likecount"],
    "replies": ["reply_count", "comments", "commentcount"],
    "reposts": ["retweet_count", "repost_count", "shares"],
    "views":   ["view_count", "view count", "viewcount", "impressions", "impression_count"],
    "content": ["text", "tweet", "message"],
    "url":     ["url", "tweet_url", "tweetlink"],
    "timestamp": ["created_at", "date", "timestamp"],
    "author":  ["author", "username", "account", "page", "handle", "profileuser"],
}

def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())

def auto(cols, key):
    norm_cols = [_norm(c) for c in cols]
    for alias in ALIASES[key]:
        na = _norm(alias)
        for i, nc in enumerate(norm_cols):
            if na == nc or na in nc or nc in na:
                return cols[i]
    return None

cols_main = df_main.columns.tolist()
map_cols = {k: auto(cols_main, k) for k in ALIASES}

st.sidebar.header("Column mapping")
for k, lbl in zip(
    ["likes", "replies", "reposts", "views", "content", "url", "timestamp", "author"],
    ["Likes", "Replies", "Reposts", "Views (opt.)", "Content", "URL (opt.)", "Timestamp (opt.)", "Author"]):
    opts = [None] + cols_main
    map_cols[k] = st.sidebar.selectbox(lbl, opts, index=opts.index(map_cols[k]) if map_cols[k] else 0, key=k)

for req in ("likes", "replies", "reposts", "author"):
    if map_cols[req] is None:
        st.error("Please map at least likes, replies, reposts, author.")
        st.stop()

# ── Enrich helper ──────────────────────────────────────────────────

def enrich(df):
    df = df.copy()
    for key in ("likes", "replies", "reposts", "views"):
        col = map_cols[key]
        if col and col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)
    # compute interactions only on columns that exist in this DF
    base_cols = [c for c in (map_cols["likes"], map_cols["replies"], map_cols["reposts"]) if c in df.columns]
    if base_cols:
        df["total_interactions"] = df[base_cols].sum(axis=1)
    else:
        df["total_interactions"] = 0
    if map_cols["views"] and map_cols["views"] in df.columns:
        df["eng_rate_%"] = (df["total_interactions"] / df[map_cols["views"]]).replace([float("inf"), -float("inf")], 0) * 100
    else:
        df["eng_rate_%"] = None
    if map_cols["timestamp"] and map_cols["timestamp"] in df.columns:
        ts = map_cols["timestamp"]
        df[ts] = pd.to_datetime(df[ts], errors="coerce")
        df["date_time"] = df[ts].dt.strftime("%Y-%m-%d %H:%M")
    else:
        df["date_time"] = "NA"
    return df

df_main = enrich(df_main)
df_comp = enrich(df_comp) if not df_comp.empty else pd.DataFrame()

MAIN = df_main[map_cols["author"]].mode()[0]
df_main["brand"] = MAIN
if not df_comp.empty:
    if map_cols["author"] in df_comp.columns:
        df_comp["brand"] = df_comp[map_cols["author"]]
    else:
        st.warning("Author column not found in competitor file – labeling as 'Competitor'.")
        df_comp["brand"] = "Competitor"

# ── Tabs ───────────────────────────────────────────────────────────
TABS = ["Overview", "Top 10"]
if not df_comp.empty:
    TABS.insert(1, "Compare")
TABS.append("Raw")
pages = st.tabs(["🐦 " + t for t in TABS])
idx = {n: i for i, n in enumerate(TABS)}

# Overview
with pages[idx["Overview"]]:
    st.subheader(f"Overview – {MAIN}")
    cols = st.columns(5 if map_cols["views"] else 4)
    cols[0].metric("Avg Likes", f"{df_main[map_cols['likes']].mean():.1f}")
    cols[1].metric("Avg Replies", f"{df_main[map_cols['replies']].mean():.1f}")
    cols[2].metric("Avg Reposts", f"{df_main[map_cols['reposts']].mean():.1f}")
    if map_cols["views"]:
        cols[3].metric("Avg Views", f"{df_main[map_cols['views']].mean():.1f}")
        cols[4].metric("Avg Eng.%", f"{df_main['eng_rate_%'].mean():.2f}%")
    else:
        cols[3].metric("Avg Total", f"{df_main['total_interactions'].mean():.1f}")

# Top‑10
with pages[idx["Top 10"]]:
    st.subheader("Top 10 Tweets – " + MAIN)
    t10 = df_main.sort_values("total_interactions", ascending=False).head(10).copy()

    # clickable link if URL column mapped
    if map_cols["url"] and map_cols["url"] in df_main.columns:
        def make_link(row):
            url = row[map_cols["url"]]
            text = str(row[map_cols["content"]])[:80]
            return f"<a href='{url}' target='_blank'>{text}</a>"
        t10["Tweet"] = t10.apply(make_link, axis=1)
        first_col = "Tweet"
    else:
        first_col = map_cols["content"]

    cols_show = [first_col, "date_time", map_cols["likes"], map_cols["replies"], map_cols["reposts"], "total_interactions"]
    if map_cols["views"]:
        cols_show += [map_cols["views"], "eng_rate_%"]

    st.write(t10[cols_show].to_html(escape=False), unsafe_allow_html=True)

# Compare
if "Compare" in TABS:
    with pages[idx["Compare"]]:
        st.subheader("Compare brands")
        combo = pd.concat([df_main, df_comp])

        agg_dict = {
            "tweets": ("total_interactions", "size"),
            "avg_interactions": ("total_interactions", "mean"),
            "avg_likes": (map_cols["likes"], "mean"),
            "avg_replies": (map_cols["replies"], "mean"),
            "avg_reposts": (map_cols["reposts"], "mean"),
        }
        if map_cols["views"] and map_cols["views"] in combo.columns:
            agg_dict["avg_views"] = (map_cols["views"], "mean")
            agg_dict["avg_eng_%"] = ("eng_rate_%", "mean")

        agg = combo.groupby("brand").agg(**agg_dict).reset_index()
        agg = agg.fillna(0)

        # highlight main brand
        def hl(row):
            return ["background-color:#dfe6fd" if row["brand"] == MAIN else "" for _ in row]

        fmt_cols = {c: "{:.1f}" for c in agg.columns if c != "brand" and c != "tweets"}
        st.dataframe(agg.style.apply(hl, axis=1).format(fmt_cols), use_container_width=True)

# Raw
with pages[idx["Raw"]]:
    st.dataframe(df_main)
    st.download_button("Download enriched CSV", df_main.to_csv(index=False).encode(), "enriched_x.csv")
    if not df_comp.empty:
        st.download_button("Download competitor CSV", df_comp.to_csv(index=False).encode(), "competitor_x.csv")

# End
