"""
LinkedIn / Multi‑Social CSV Analyzer
===================================
Streamlit app to analyse social media CSV exports for a **main brand** and
optionally a **competitor file**. Supports LinkedIn, Twitter/X, Instagram, etc.
Tabs: Overview · Compare · Top‑10 · Google Insight · Raw.
Last update: 2025‑06‑27 – fixed top 10 sorting.
"""

import streamlit as st
import pandas as pd
import altair as alt
import re
import io
from datetime import datetime, timedelta

# Initialize Streamlit
st.set_page_config(page_title="Universal Social Analyzer", layout="wide")
st.title("📊 Universal Social CSV Analyzer – with Competitor Benchmark")

# ───────────────────────────────────── Uploads ──────────────────────────────────────
main_file = st.sidebar.file_uploader("Upload MAIN brand CSV", type="csv", key="main")
if main_file is None:
    st.info("⬅️ Upload your main brand CSV to start.")
    st.stop()

comp_file = st.sidebar.file_uploader("Upload competitor CSV (optional)", type="csv", key="comp")

# Enhanced CSV reading function
def robust_read_csv(file):
    """Read CSV with multiple fallback methods, handling different delimiters"""
    try:
        content = file.getvalue().decode('utf-8', errors='ignore')
    except AttributeError:
        st.error("Invalid file upload")
        return pd.DataFrame()
    
    # First try comma delimiter
    try:
        return pd.read_csv(io.StringIO(content))
    except pd.errors.ParserError:
        try:
            # Try semicolon delimiter
            return pd.read_csv(io.StringIO(content), sep=';')
        except:
            try:
                # Try with different engines and error handling
                return pd.read_csv(io.StringIO(content), engine='python', on_bad_lines='warn')
            except:
                try:
                    # Try with different encoding
                    return pd.read_csv(io.StringIO(content), encoding='latin1')
                except:
                    # Final fallback - manual cleaning
                    lines = content.split('\n')
                    cleaned = []
                    for line in lines:
                        # Handle semicolon-delimited lines
                        if ';' in line:
                            parts = line.split(';')
                            # Filter out empty parts
                            parts = [p for p in parts if p.strip() != '']
                            cleaned.append(parts)
                        # Handle comma-delimited lines
                        elif ',' in line:
                            parts = line.split(',')
                            parts = [p for p in parts if p.strip() != '']
                            cleaned.append(parts)
                    
                    # Convert to DataFrame if we have data
                    if len(cleaned) > 1 and len(cleaned[0]) > 1:
                        header = cleaned[0]
                        data = cleaned[1:]
                        return pd.DataFrame(data, columns=header)
                    else:
                        return pd.DataFrame()

try:
    df_main = robust_read_csv(main_file)
    df_comp = robust_read_csv(comp_file) if comp_file else pd.DataFrame()
    
    # Clean column names
    if not df_main.empty:
        df_main.columns = [col.replace(';', '').strip() for col in df_main.columns]
    if comp_file and not df_comp.empty:
        df_comp.columns = [col.replace(';', '').strip() for col in df_comp.columns]
    
except Exception as e:
    st.error(f"Error reading CSV: {str(e)}")
    st.stop()

# ──────────────────────────── Improved Column Auto-Detection ────────────────────────────
def detect_column(df, patterns):
    """Find best matching column using regex patterns and scoring system"""
    if df.empty or not hasattr(df, 'columns'):
        return None
        
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
            if score > best_score or (score == best_score and len(col) > len(df.columns[best_match].lower() if best_match is not None else '')):
                best_match = i
                best_score = score
    
    return df.columns[best_match] if best_match is not None else None

# Pattern detection with fallback
def detect_columns(df):
    if df.empty:
        return {}
        
    mapping = {}
    patterns = {
        "likes": [r"like", r"favou?rite", r"reaction", r"likecount"],
        "comments": [r"comment", r"reply", r"commentcount"],
        "reposts": [r"repost", r"share", r"retweet", r"repostcount"],
        "content": [r"content", r"text", r"message", r"caption", r"body"],
        "url": [r"url", r"link", r"permalink", r"tweetlink", r"posturl"],
        "timestamp": [r"timestamp", r"date", r"time", r"created", r"tweetdate", r"posttimestamp"],
        "author": [r"author", r"page", r"company", r"account", r"brand", r"handle"],
        "views": [r"view", r"impression", r"viewcount"],
    }
    
    for col_type, pattern_list in patterns.items():
        detected = detect_column(df, pattern_list)
        mapping[col_type] = detected
        
        # Fallback to first numeric column for metrics
        if col_type in ["likes", "comments", "reposts", "views"] and detected is None:
            for c in df.columns:
                if pd.api.types.is_numeric_dtype(df[c]):
                    mapping[col_type] = c
                    break
    
    return mapping

# Auto-detect columns with improved logic
map_cols = detect_columns(df_main)

# ────────────────────────────── Manual Mapping Fallback ─────────────────────────────
if not df_main.empty:
    st.sidebar.header("Column Mapping (Verify/Correct)")
    cols_main = df_main.columns.tolist()

    # Show detected columns and allow manual override
    for col_type in ["likes", "comments", "reposts", "views", "author", "content", "url", "timestamp"]:
        current = map_cols.get(col_type)
        if current and current in cols_main:
            idx_default = cols_main.index(current)
        else:
            idx_default = 0
            
        options = [None] + cols_main
        index = idx_default + 1 if current and current in cols_main else 0
        
        # Handle case where no columns exist
        if not cols_main:
            options = [None]
            index = 0
            
        map_cols[col_type] = st.sidebar.selectbox(
            f"{col_type.capitalize()} column", 
            options,
            index=index,
            key=f"map_{col_type}"
        )

# Add brand name input since author is optional
MAIN_BRAND = st.sidebar.text_input("Main Brand Name", value="Main Brand")

# Interaction calculation options
st.sidebar.subheader("Interaction Calculation")
include_reposts = st.sidebar.checkbox("Include reposts in total interactions", value=True)
include_views = st.sidebar.checkbox("Include views as separate metric", value=True)

# ────────────────────────────── Helper: enrich dataframe ─────────────────────────────
def enrich(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
        
    df = df.copy()
    
    # Create default columns for missing metrics
    for col_type in ["likes", "comments", "reposts", "views"]:
        col_name = map_cols[col_type]
        if col_name and col_name in df.columns:
            df[col_name] = pd.to_numeric(df[col_name], errors="coerce").fillna(0).astype(int)
        else:
            # Create a column of zeros if not mapped
            df[col_type] = 0
            map_cols[col_type] = col_type  # Update mapping to use new column
    
    # Calculate total interactions (configurable)
    interaction_cols = []
    if map_cols["likes"] in df.columns:
        interaction_cols.append(map_cols["likes"])
    if map_cols["comments"] in df.columns:
        interaction_cols.append(map_cols["comments"])
    if include_reposts and map_cols["reposts"] in df.columns:
        interaction_cols.append(map_cols["reposts"])
    
    if interaction_cols:
        df["total_interactions"] = df[interaction_cols].sum(axis=1)
    else:
        df["total_interactions"] = 0

    # Timestamp handling
    if map_cols["timestamp"] and map_cols["timestamp"] in df.columns:
        ts = map_cols["timestamp"]
        df[ts] = pd.to_datetime(df[ts], errors="coerce")
        df["date_time"] = df[ts].dt.strftime("%Y-%m-%d %H:%M")
        
        # Create a date-only column for date range calculation
        df["date"] = df[ts].dt.date
    else:
        df["date_time"] = "NA"
        df["date"] = None

    # Topic detection
    if map_cols["content"] and map_cols["content"] in df.columns:
        df["google_topic"] = df[map_cols["content"]].astype(str).str.contains("google", case=False, na=False)
    else:
        df["google_topic"] = False
        
    return df

df_main = enrich(df_main)
df_comp = enrich(df_comp) if not df_comp.empty else pd.DataFrame()

# Set brand name
df_main["brand"] = MAIN_BRAND
if not df_comp.empty:
    df_comp["brand"] = df_comp[map_cols["author"]] if map_cols.get("author") in df_comp.columns else "Competitor"

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
    
    # Create metrics columns - 7 columns to fit all metrics
    cols = st.columns(7)
    
    # Calculate total posts
    total_posts = len(df_main) if not df_main.empty else 0
    cols[0].metric("Total Posts", total_posts)
    
    # Calculate date range if available
    date_range = "N/A"
    min_date = None
    max_date = None
    if not df_main.empty and "date" in df_main.columns and not df_main["date"].isnull().all():
        valid_dates = df_main[df_main["date"].notnull()]["date"]
        if not valid_dates.empty:
            min_date = valid_dates.min()
            max_date = valid_dates.max()
            date_range = f"{min_date.strftime('%d-%m')} to {max_date.strftime('%d-%m %Y')}"
    cols[1].metric("Date Range", date_range)
    
    # Calculate posts per week
    posts_per_week = "N/A"
    if min_date and max_date and total_posts > 0:
        try:
            days = (max_date - min_date).days
            weeks = max(days / 7.0, 1)  # At least 1 week to avoid division by zero
            posts_per_week = total_posts / weeks
            posts_per_week = f"{posts_per_week:.1f}"
        except:
            posts_per_week = "N/A"
    cols[2].metric("Avg Posts/Week", posts_per_week)
    
    # Engagement metrics
    metrics = [
        ("Avg Likes", map_cols["likes"]),
        ("Avg Comments", map_cols["comments"]),
        ("Avg Reposts", map_cols["reposts"]),
        ("Avg Views", map_cols["views"]),
        ("Avg Interactions", "total_interactions")
    ]
    
    # Position remaining metrics starting from column 3
    for i, ((name, col), column) in enumerate(zip(metrics, cols[3:])):
        if col in df_main.columns and not df_main.empty:
            value = df_main[col].mean()
            column.metric(name, f"{value:.1f}" if not pd.isna(value) else "N/A")
        else:
            column.metric(name, "N/A")
    
    # Store metrics for download
    metrics_data = [
        {"Metric": "Total Posts", "Value": total_posts},
        {"Metric": "Date Range", "Value": date_range},
        {"Metric": "Avg Posts/Week", "Value": posts_per_week}
    ]
    
    for name, col in metrics:
        if col in df_main.columns and not df_main.empty:
            value = df_main[col].mean()
            metrics_data.append({"Metric": name, "Value": value})
        else:
            metrics_data.append({"Metric": name, "Value": "N/A"})
    
    # Create metrics DataFrame for download
    metrics_df = pd.DataFrame(metrics_data)
    
    # Download button for overview metrics
    st.download_button(
        "Download Overview Metrics",
        metrics_df.to_csv(index=False).encode(),
        "overview_metrics.csv",
        key="dl_overview_metrics"
    )
    
    # Scatter plot
    if not df_main.empty:
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
    else:
        st.warning("No data available for visualization")

# ─────────────────────────────── Compare tab ──────────────────────────────────────
if "Compare" in TABS and not df_comp.empty and not df_main.empty:
    with pages[idx["Compare"]]:
        st.subheader("Compare brands")
        combined = pd.concat([df_main, df_comp], ignore_index=True)

        # Create aggregation based on available columns
        agg_config = {
            "posts": ("brand", "count")
        }
        
        # Add metrics that exist in the dataframe
        for metric in ["likes", "comments", "reposts", "views"]:
            col_name = map_cols[metric]
            if col_name in combined.columns:
                agg_config[f"avg_{metric}"] = (col_name, "mean")
        
        if "total_interactions" in combined.columns:
            agg_config["avg_total"] = ("total_interactions", "mean")
        
        agg = combined.groupby("brand").agg(**agg_config).reset_index().round(1)

        # Highlight main brand
        def highlight_row(row):
            color = "#dfe6fd" if row["brand"] == MAIN_BRAND else ""
            return [f"background-color: {color}"] * len(row)

        st.dataframe(agg.style.apply(highlight_row, axis=1), use_container_width=True)
        
        # Download button for comparison data
        st.download_button(
            "Download Comparison Data",
            agg.to_csv(index=False).encode(),
            "comparison_data.csv",
            key="dl_comparison"
        )

# ─────────────────────────────── Top‑10 tab ──────────────────────────────────────
with pages[idx["Top 10"]]:
    st.subheader(f"Top 10 Posts – {MAIN_BRAND}")
    
    if not df_main.empty:
        # FIXED: Always sort by total interactions for top performers
        if "total_interactions" in df_main.columns:
            # Create a sorted copy to avoid modifying original
            sorted_df = df_main.sort_values("total_interactions", ascending=False).copy()
            
            # Get top 10 based on total interactions
            top10 = sorted_df.head(10)
            st.caption("Sorted by Total Interactions")
            
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
            show_cols.extend(["date_time"])
            
            # Add available metrics
            for metric in ["likes", "comments", "reposts", "views"]:
                if map_cols[metric] in top10.columns:
                    show_cols.append(map_cols[metric])
            
            if "total_interactions" in top10.columns:
                show_cols.append("total_interactions")
            
            # Display with interaction counts
            st.write(top10[show_cols].to_html(escape=False), unsafe_allow_html=True)
            
            # Prepare download version with embedded URL
            if not top10.empty:
                # Create a copy for download
                download_top10 = top10.copy()
                
                # Add full content column
                if map_cols["content"] in download_top10.columns:
                    download_top10["Full Content"] = download_top10[map_cols["content"]]
                
                # Add raw URL column
                if map_cols["url"] in download_top10.columns:
                    download_top10["URL"] = download_top10[map_cols["url"]]
                
                # Select columns for download
                download_cols = []
                if "Full Content" in download_top10.columns:
                    download_cols.append("Full Content")
                if "preview" in download_top10.columns:
                    download_cols.append("preview")
                if "URL" in download_top10.columns:
                    download_cols.append("URL")
                if "date_time" in download_top10.columns:
                    download_cols.append("date_time")
                
                # Add metric columns
                for metric in ["likes", "comments", "reposts", "views"]:
                    if map_cols[metric] in download_top10.columns:
                        download_cols.append(map_cols[metric])
                
                if "total_interactions" in download_top10.columns:
                    download_cols.append("total_interactions")
                
                # Create final download dataframe
                download_df = download_top10[download_cols]
                
                # Download button for top posts
                st.download_button(
                    "Download Top 10 Posts",
                    download_df.to_csv(index=False).encode(),
                    "top_10_posts.csv",
                    key="dl_top10"
                )
        else:
            st.warning("No interaction data available for sorting")
    else:
        st.warning("No data available")

# ─────────────────────────────── Google Insight ───────────────────────────────────
with pages[idx["Google Insight"]]:
    st.subheader(f"Google topic insight – {MAIN_BRAND}")
    
    if not df_main.empty and "google_topic" in df_main.columns and "total_interactions" in df_main.columns:
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
            columns_to_show = [map_cols["content"], "date_time", "total_interactions"]
            # Add views if available
            if map_cols["views"] in low_google.columns:
                columns_to_show.append(map_cols["views"])
                
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
