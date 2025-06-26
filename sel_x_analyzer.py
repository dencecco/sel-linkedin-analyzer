# ... (previous code remains the same until the sidebar section)

# ────────────────────────────── Manual Mapping Fallback ─────────────────────────────
st.sidebar.header("Column Mapping (Verify/Correct)")
cols_main = df_main.columns.tolist()

# Show detected columns and allow manual override
for col_type in ["likes", "comments", "reposts", "views", "author", "content", "url", "timestamp"]:
    current = map_cols.get(col_type)
    idx_default = cols_main.index(current) if current and current in cols_main else 0
    options = [None] + cols_main
    index = idx_default + 1 if current and current in cols_main else 0
    map_cols[col_type] = st.sidebar.selectbox(
        f"{col_type.capitalize()} column", 
        options,
        index=index,
        key=f"map_{col_type}"
    )

# Add brand name input since author is optional
MAIN_BRAND = st.sidebar.text_input("Main Brand Name", value="Main Brand")

# NEW: Interaction calculation options
st.sidebar.subheader("Interaction Calculation")
include_reposts = st.sidebar.checkbox("Include reposts in total interactions", value=True)
include_views = st.sidebar.checkbox("Include views as separate metric", value=True)

# ────────────────────────────── Helper: enrich dataframe ─────────────────────────────
def enrich(df: pd.DataFrame) -> pd.DataFrame:
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
    else:
        df["date_time"] = "NA"

    # Topic detection
    if map_cols["content"] and map_cols["content"] in df.columns:
        df["google_topic"] = df[map_cols["content"]].astype(str).str.contains("google", case=False, na=False)
    else:
        df["google_topic"] = False
        
    return df

# ... (rest of the code remains the same with minor adjustments in display)
