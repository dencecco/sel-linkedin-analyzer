"""
LinkedIn / Multi‑Social CSV Analyzer
===================================
Streamlit app to analyse social media CSV exports for a **main brand** and
optionally a **competitor file**. Supports LinkedIn, Twitter/X, Instagram, etc.
Tabs: Overview · Compare · Top‑10 · Google Insight · Raw.
Last update: 2025‑06‑27 – added download buttons for overview and top posts.
"""

import streamlit as st
import pandas as pd
import altair as alt
import re
import io
from datetime import timedelta

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
        "comments": [r"comment", r"reply", r
