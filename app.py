import streamlit as st
import pandas as pd
import numpy as np
import requests
import io

st.set_page_config(page_title="INSPIRES Study: Anthropometry Tracker", layout="wide")
st.title("INSPIRES Study: Height & Weight Dashboard")

@st.cache_data(ttl=600)
def fetch_and_process_data():
    creds = st.secrets["api_credentials"]
    auth = (creds["username"], creds["password"])
    
    # Construct OData API endpoints for ODK Central forms
    enr_url = f"{creds['base_url']}/forms/ENR_2024.svc/Submissions?$expand=*"
    out_url = f"{creds['base_url']}/forms/OUT_2024.svc/Submissions?$expand=*"
    
    # Fetch Data
    with st.spinner("Fetching data from ODK server..."):
        enr_resp = requests.get(enr_url, auth=auth)
        out_resp = requests.get(out_url, auth=auth)
    
    if enr_resp.status_code != 200 or out_resp.status_code != 200:
        st.error(f"Failed to fetch data. Server responded with ENR: {enr_resp.status_code}, OUT: {out_resp.status_code}")
        st.stop()
        
    enr_data = enr_resp.json().get('value', [])
    out_data = out_resp.json().get('value', [])
    
    # Convert to DataFrame (handles empty lists safely by creating empty DataFrames)
    enr_df = pd.json_normalize(enr_data) if enr_data else pd.DataFrame()
    out_df = pd.json_normalize(out_data) if out_data else pd.DataFrame()

    def get_col(df, target):
        if df.empty: return None
        # Safely find columns containing the target string (case-insensitive to be safe)
        match = [c for c in df.columns if target.lower() in c.lower()]
        return match[0] if match else None

    enr_map = {
        get_col(enr_df, 'ENR_BINFO-C_8'): 'Participant_ID',
        get_col(enr_df, 'ENR_BINFO-Q1_2'): 'Site_Code',
        get_col(enr_df, 'ENR_FAHA-Q3_5_1'): 'ENR_FAHA-Q3_5_1',
        get_col(enr_df, 'ENR_FAHA-Q3_6_1'): 'ENR_FAHA-Q3_6_1',
        get_col(enr_df, 'submitterName'): 'SubmitterName',
        get_col(enr_df, 'submissionDate'): 'today' # Fallback if 'today' is stored as submissionDate
    }
    
    # Remove None keys before renaming
    enr_map = {k: v for k, v in enr_map.items() if k is not None}
    enr_df = enr_df.rename(columns=enr_map)
    
    # Check for exact 'today' column if mapping missed it
    if 'today' not in enr_df.columns and not enr_df.empty:
        alt_today = get_col(enr_df, 'today')
        if alt_today: enr_df = enr_df.rename(columns={alt_today: 'today'})

    expected_enr_cols = ['Participant_ID', 'Site_Code', 'ENR_FAHA-Q3_5_1', 'ENR_FAHA-Q3_6_1', 'SubmitterName', 'today']
    for c in expected_enr_cols:
        if c not in enr_df.columns:
            enr_df[c] = np.nan

    # Map sites
    site_mapping = {
        "NC": "NCT DELHI", "JO": "JODHPUR", "GU": "GUWAHATI",
        "KO": "KOLKATA", "CH": "CHENNAI", "PU": "PUNE"
    }
    enr_df['City'] = enr_df['Site_Code'].map(site_mapping)

    out_map = {
        get_col(out_df, 'OUT-P_ID'): 'Participant_ID',
        get_col(out_df, 'OUT-Q1_11_1a'): 'OUT_Height',
        get_col(out_df, 'OUT-Q1_12_1a'): 'OUT_Weight',
        get_col(out_df, 'submitterName'): 'OUT_Submitter',
        get_col(out_df, 'submissionDate'): 'OUT_Date'
    }
    out_map = {k: v for k, v in out_map.items() if k is not None}
    out_df = out_df.rename(columns=out_map)

    expected_out_cols = ['Participant_ID', 'OUT_Height', 'OUT_Weight', 'OUT_Submitter', 'OUT_Date']
    for c in expected_out_cols:
        if c not in out_df.columns:
            out_df[c] = np.nan
            
    out_subset = out_df[expected_out_cols].copy()

    merged_df = pd.merge(enr_df, out_subset, on="Participant_ID", how="left")

    merged_df['Final_Height_cm'] = merged_df['ENR_FAHA-Q3_5_1'].fillna(merged_df['OUT_Height'])
    merged_df['Final_Weight_kg'] = merged_df['ENR_FAHA-Q3_6_1'].fillna(merged_df['OUT_Weight'])

    merged_df['Height_Source'] = np.where(merged_df['ENR_FAHA-Q3_5_1'].notna(), 'Enrolment', 
                                 np.where(merged_df['OUT_Height'].notna(), 'Outcome', 'Missing'))
    
    merged_df['Weight_Source'] = np.where(merged_df['ENR_FAHA-Q3_6_1'].notna(), 'Enrolment', 
                                 np.where(merged_df['OUT_Weight'].notna(), 'Outcome', 'Missing'))

    merged_df['Height_Missing'] = merged_df['Final_Height_cm'].isna()
    merged_df['Weight_Missing'] = merged_df['Final_Weight_kg'].isna()

    return merged_df

def convert_df_to_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Anthropometry_Data')
    return output.getvalue()

try:
    df = fetch_and_process_data()
except Exception as e:
    st.error(f"Error processing data: {e}")
    st.stop()

# Sidebar Filters
st.sidebar.header("Filters")
available_cities = df['City'].dropna().unique() if 'City' in df.columns else []
selected_cities = st.sidebar.multiselect(
    "Select Site (City):",
    options=available_cities,
    default=available_cities
)

# Apply Filter safely
filtered_df = df[df['City'].isin(selected_cities)] if not df.empty else pd.DataFrame()

st.subheader("Data Quality: Missing Anthropometry Metrics")
st.markdown("Displays counts of participants where height or weight is missing in **both** Enrolment and Outcome forms.")

if not selected_cities:
    st.info("Please select at least one site from the sidebar.")
elif not filtered_df.empty:
    cols = st.columns(len(selected_cities))
    for idx, city in enumerate(selected_cities):
        city_data = filtered_df[filtered_df['City'] == city]
        missing_height = city_data['Height_Missing'].sum()
        missing_weight = city_data['Weight_Missing'].sum()
        
        with cols[idx]:
            st.metric(label=f"{city} - Missing Height", value=int(missing_height))
            st.metric(label=f"{city} - Missing Weight", value=int(missing_weight))
else:
    st.warning("No data available for the selected filters.")

st.divider()

st.subheader("Extracted Participant Data")
columns_to_display = [
    'Participant_ID', 'City', 'SubmitterName', 'today', 
    'Final_Height_cm', 'Height_Source', 
    'Final_Weight_kg', 'Weight_Source'
]

# Ensure all display columns exist before rendering to prevent UI crash
actual_display_cols = [c for c in columns_to_display if c in filtered_df.columns]

st.dataframe(filtered_df[actual_display_cols], use_container_width=True)

if not filtered_df.empty:
    st.subheader("Export Data")
    excel_data = convert_df_to_excel(filtered_df)

    st.download_button(
        label="📥 Download Data as Excel",
        data=excel_data,
        file_name="INSPIRES_Height_Weight_Data.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
