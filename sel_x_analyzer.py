"""
LinkedIn / Multi‑Social CSV Analyzer
===================================
Streamlit app to analyse LinkedIn‑style CSV exports for a **main brand** and
optionally a **competitor file**. Tabs: Overview · Compare · Top‑10 · Google
Insight · Raw.
Last update: 2025‑06‑27 – fixed CSV reading and bracket syntax error.
"""

import streamlit as st
import pandas as pd
import altair as alt
import re
from datetime import timedelta
import io

st.set_page_config(page_title="Universal Social Analyzer", layout="wide")
st.title("📊 Universal Social CSV Analyzer – with Competitor Benchmark")

# ───────────────────────────────────── Uploads ──────────────────────────────────────
main_file = st.sidebar.file_uploader("Upload MAIN brand CSV", type="csv", key="main")
if main_file is None:
    st.info("⬅️ Upload your main brand CSV to start.")
    st.stop()

comp_file = st.sidebar.file_uploader("Upload competitor CSV (optional)", type="csv", key="comp")

# New robust CSV reading function
def robust_read_csv(file):
    """Read CSV with multiple fallback methods"""
    # First try standard read
    try:
        return pd.read_csv(file)
    except pd.errors.ParserError:
        try:
            # Try with different engines and error handling
            return pd.read_csv(file, engine='python', on_bad_lines='warn')
        except:
            try:
                # Try with different encoding
                return pd.read_csv(file, encoding='latin1')
            except:
                # Final fallback - read as text and clean
                content = file.getvalue().decode('utf-8', errors='ignore')
                lines = content.split('\n')
                cleaned = []
                for line in lines:
                    # Simple cleaning of malformed lines
                    if line.count(',') < 5:  # If too few columns
                        continue
                    cleaned.append(line)
                return pd.read_csv(io.StringIO('\n'.join(cleaned)))

try:
    df_main = robust_read_csv(main_file)
    df_comp = robust_read_csv(comp_file) if comp_file else pd.DataFrame()
except Exception as e:
    st.error(f"Error reading CSV: {str(e)}")
    st.stop()

# ──────────────────────────── Improved Column Auto-Detection ────────────────────────────
def detect_column(df, patterns):
    """Find best matching column using regex patterns and scoring system"""
    cols = df.columns.str.lower()
    best_match = None
    best_score = 0
    
    for pattern in patterns:
        for i, col in enumerate(cols):
            # Score based on match type
            if re.fullmatch(pattern, col):
                score = 3  # Exact match
            elif re.search(pattern, col):
                score = 2  # Partial match
            else:
                continue
                
            # Prefer longer matches and exact matches
            if score > best_score or (score == best_score and len(col) > len(df.columns[best_match].lower())):
                best_match = i
                best_score = score
    
    return df.columns[best_match] if best_match is not None else None

# Pattern detection with fallback
def detect_columns(df):
    mapping = {}
    patterns = {
        "likes": [r"like", r"favou?rite", r"reaction"],
        "comments": [r"comment", r"reply"],
        "reposts": [r"repost", r"share", r"retweet"],
        "content": [r"content", r"text", r"message", r"caption", r"body"],
        "url": [r"url", r"link", r"permalink"],
        "timestamp": [r"timestamp", r"date", r"time", r"created"],
        "author": [r"author", r"page", r"company", r"account", r"brand"],
    }
    
    for col_type, pattern_list in patterns.items():
        detected = detect_column(df, pattern_list)
        mapping[col_type] = detected
        
        # Fallback to first numeric column for metrics
        if col_type in ["likes", "comments", "reposts"] and detected is None:
            for c in df.columns:
                if pd.api.types.is_numeric_dtype(df[c]):
                    mapping[col_type] = c
                    break
    
    # Final fallback for author
    if mapping["author"] is None:
        for c in df.columns:
            if df[c].nunique() < 50:  # Reasonable number of unique values
                mapping["author"] = c
                break
    
    return mapping

# Auto-detect columns with improved logic
map_cols = detect_columns(df_main)

# ────────────────────────────── Manual Mapping Fallback ─────────────────────────────
st.sidebar.header("Column Mapping (Verify/Correct)")
cols_main = df_main.columns.tolist()

# Show detected columns and allow manual override
for col_type in ["likes", "comments", "reposts", "author", "content", "url", "timestamp"]:
    current = map_cols.get(col_type)
    idx_default = cols_main.index(current) if current in cols_main else 0
    map_cols[col_type] = st.sidebar.selectbox(
        f"{col_type.capitalize()} column", 
        [None] + cols_main,
        index=idx_default + 1 if current else 0,
        key=f"map_{col_type}"
    )

# Validate required columns
required = ["likes", "comments", "reposts", "author"]
missing = [col for col in required if not map_cols[col]]

if missing:
    st.error(f"Missing required columns: {', '.join(missing)}. Please map them.")
    st.stop()

# ────────────────────────────── Helper: enrich dataframe ─────────────────────────────
def enrich(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    # Numeric cleaning
    for col in (map_cols["likes"], map_cols["comments"], map_cols["reposts"]):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)
    
    # Calculate total interactions
    interaction_cols = [map_cols[c] for c in ["likes", "comments", "reposts"] if map_cols[c] in df.columns]
    df["total_interactions"] = df[interaction_cols].sum(axis=1)

    # Timestamp handling
    if map_cols["timestamp"] and map_cols["timestamp"] in df.columns:
        ts = map_cols["timestamp"]
        df[ts] = pd.to_datetime(df[ts], errors="coerce")
        df["date_time"] = df[ts].dt.strftime("%Y-%m-%d %H:%M")
    else:
        df["date_time"] = "NA"

    # Topic detection
    if map_cols["content"] and map_cols["content"] in df.columns:
        df["google_topic"] = df[map_cols["content"]].astype(str).str.contains("google", case=False, na=False)
    else:
        df["google_topic"] = False
        
    return df

df_main = enrich(df_main)
df_comp = enrich(df_comp) if not df_comp.empty else pd.DataFrame()

MAIN_BRAND = df_main[map_cols["author"]].mode()[0] if map_cols["author"] in df_main.columns else "Main Brand"

df_main["brand"] = MAIN_BRAND
if not df_comp.empty and map_cols["author"] in df_comp.columns:
    df_comp["brand"] = df_comp[map_cols["author"]]

# ───────────────────────────────────── Tabs ────────────────────────────────────────
TABS = ["Overview", "Top 10", "Google Insight"]
if not df_comp.empty:
    TABS.insert(1, "Compare")
TABS.append("Raw")

pages = st.tabs(["📊 " + t for t in TABS])
idx = {name: i for i, name in enumerate(TABS)}

# ─────────────────────────────── Overview tab ──────────────────────────────────────
with pages[idx["Overview"]]:
    st.subheader(f"Overview – {MAIN_BRAND}")
    
    # Create metrics columns
    cols = st.columns(4)
    metrics = [
        ("Avg Likes", map_cols["likes"]),
        ("Avg Comments", map_cols["comments"]),
        ("Avg Reposts", map_cols["reposts"]),
        ("Avg Interactions", "total_interactions")
    ]
    
    for (name, col), column in zip(metrics, cols):
        if col in df_main.columns:
            value = df_main[col].mean()
            column.metric(name, f"{value:.1f}" if not pd.isna(value) else "N/A")
    
    # Scatter plot
    if map_cols["likes"] in df_main.columns and map_cols["comments"] in df_main.columns:
        st.markdown("#### Scatter: Comments vs Likes")
        chart = alt.Chart(df_main).mark_circle(size=60, opacity=0.6).encode(
            x=alt.X(map_cols["likes"], title="Likes"),
            y=alt.Y(map_cols["comments"], title="Comments"),
            color=alt.Color("google_topic:N", legend=alt.Legend(title="Google Mention")),
            tooltip=[map_cols["content"], map_cols["likes"], map_cols["comments"]]
        ).interactive()
        st.altair_chart(chart, use_container_width=True)
    else:
        st.warning("Missing like or comment data for scatter plot")

# ─────────────────────────────── Compare tab ──────────────────────────────────────
if "Compare" in TABS and not df_comp.empty:
    with pages[idx["Compare"]]:
        st.subheader("Compare brands")
        combined = pd.concat([df_main, df_comp], ignore_index=True)

        agg = combined.groupby("brand").agg(
            posts=("brand", "count"),
            avg_likes=(map_cols["likes"], "mean"),
            avg_comments=(map_cols["comments"], "mean"),
            avg_reposts=(map_cols["reposts"], "mean"),
            avg_total=("total_interactions", "mean"),
        ).reset_index().round(1)

        # Highlight main brand
        def highlight_row(row):
            color = "#dfe6fd" if row["brand"] == MAIN_BRAND else ""
            return [f"background-color: {color}"] * len(row)

        st.dataframe(agg.style.apply(highlight_row, axis=1), use_container_width=True)

# ─────────────────────────────── Top‑10 tab ──────────────────────────────────────
with pages[idx["Top 10"]]:
    st.subheader(f"Top 10 posts – {MAIN_BRAND}")
    
    if "total_interactions" in df_main.columns:
        top10 = df_main.sort_values("total_interactions", ascending=False).head(10)
        
        # Create post previews
        if map_cols["content"] in top10.columns:
            top10["preview"] = top10[map_cols["content"]].str[:80] + "..."
        
        # Create download links if URL exists
        if map_cols["url"] in top10.columns:
            top10["link"] = top10.apply(
                lambda x: f'<a href="{x[map_cols["url"]]}" target="_blank">🔗</a>', 
                axis=1
            )
        
        # Show table
        show_cols = []
        if "preview" in top10.columns:
            show_cols.append("preview")
        if "link" in top10.columns:
            show_cols.append("link")
        show_cols.extend([
            "date_time", 
            map_cols["likes"], 
            map_cols["comments"], 
            map_cols["reposts"], 
            "total_interactions"
        ])
        
        st.write(top10[show_cols].to_html(escape=False), unsafe_allow_html=True)
    else:
        st.warning("No interaction data available")

# ─────────────────────────────── Google Insight ───────────────────────────────────
with pages[idx["Google Insight"]]:
    st.subheader(f"Google topic insight – {MAIN_BRAND}")
    
    if "google_topic" in df_main.columns and "total_interactions" in df_main.columns:
        # Segment data
        high = df_main[df_main["total_interactions"] >= 10]  # High performers
        low = df_main[df_main["total_interactions"] < 10]    # Low performers
        
        # Create segments
        segments = {
            "High ≥10 • Google": high[high["google_topic"]],
            "High ≥10 • non‑Google": high[~high["google_topic"]],
            "Low <10 • Google": low[low["google_topic"]],
            "Low <10 • non‑Google": low[~low["google_topic"]]
        }
        
        # Show metrics
        cols = st.columns(4)
        for (name, segment), col in zip(segments.items(), cols):
            col.metric(name, len(segment))
        
        # Show low performers with Google topic
        st.markdown("#### Low performers with Google topic")
        low_google = segments["Low <10 • Google"]
        
        if not low_google.empty:
            # Simplified to avoid bracket confusion
            columns_to_show = [
                map_cols["content"], 
                "date_time", 
                "total_interactions"
            ]
            st.dataframe(low_google[columns_to_show])
            
            st.download_button(
                "Download Low Google Performers",
                low_google.to_csv(index=False).encode(),
                "low_google.csv",
                key="dl_low_google"
            )
        else:
            st.info("No low-performing posts mentioning Google")
        
        # Summary table
        st.markdown("#### Performance Summary")
        summary_data = []
        for name, segment in segments.items():
            if segment.empty:
                avg = 0
            else:
                avg = segment["total_interactions"].mean()
            summary_data.append({
                "Segment": name,
                "Posts": len(segment),
                "Avg Interactions": round(avg, 1)
            })
        
        st.dataframe(pd.DataFrame(summary_data))
    else:
        st.warning("Google topic analysis not available")

# ─────────────────────────────── Raw tab ─────────────────────────────────────────
with pages[idx["Raw"]]:
    st.subheader("Raw Data & Downloads")
    st.dataframe(df_main, use_container_width=True)
    
    st.download_button(
        "Download Processed Data", 
        df_main.to_csv(index=False).encode(), 
        "processed_data.csv", 
        key="dl_processed"
    )
