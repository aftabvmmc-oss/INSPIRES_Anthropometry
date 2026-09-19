import streamlit as st
import pandas as pd
import numpy as np
import requests
import io

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
    
    enr_df = pd.json_normalize(enr_data)
    out_df = pd.json_normalize(out_data)

    # Helper to find a column containing a target string, regardless of ODK group prefix
    def get_col(df, target):
        match = [c for c in df.columns if target in c]
        return match[0] if match else None

    # Dynamically map Enrolment columns
    enr_map = {
        get_col(enr_df, 'ENR_BINFO-C_8'): 'Participant_ID',
        get_col(enr_df, 'ENR_BINFO-Q1_2'): 'Site_Code',
        get_col(enr_df, 'ENR_FAHA-Q3_5_1'): 'ENR_FAHA-Q3_5_1',
        get_col(enr_df, 'ENR_FAHA-Q3_6_1'): 'ENR_FAHA-Q3_6_1'
    }
    enr_df = enr_df.rename(columns={k: v for k, v in enr_map.items() if k})

    site_mapping = {
        "NC": "NCT DELHI", "JO": "JODHPUR", "GU": "GUWAHATI",
        "KO": "KOLKATA", "CH": "CHENNAI", "PU": "PUNE"
    }
    
    if 'Site_Code' in enr_df.columns:
        enr_df['City'] = enr_df['Site_Code'].map(site_mapping)
    else:
        enr_df['City'] = np.nan

    # Dynamically map Outcome columns
    out_map = {
        get_col(out_df, 'OUT-P_ID'): 'Participant_ID',
        get_col(out_df, 'OUT-Q1_11_1a'): 'OUT_Height',
        get_col(out_df, 'OUT-Q1_12_1a'): 'OUT_Weight',
        get_col(out_df, 'submitterName'): 'OUT_Submitter',
        get_col(out_df, 'submissionDate'): 'OUT_Date'
    }
    out_df = out_df.rename(columns={k: v for k, v in out_map.items() if k})

    expected_out_cols = ['Participant_ID', 'OUT_Height', 'OUT_Weight', 'OUT_Submitter', 'OUT_Date']
    available_out_cols = [c for c in expected_out_cols if c in out_df.columns]
    out_subset = out_df[available_out_cols].copy()

    for c in expected_out_cols:
        if c not in out_subset.columns:
            out_subset[c] = np.nan

    merged_df = pd.merge(enr_df, out_subset, on="Participant_ID", how="left")

    # Fallback to avoid errors if mapping failed entirely
    if 'ENR_FAHA-Q3_5_1' not in merged_df.columns:
        merged_df['ENR_FAHA-Q3_5_1'] = np.nan
    if 'ENR_FAHA-Q3_6_1' not in merged_df.columns:
        merged_df['ENR_FAHA-Q3_6_1'] = np.nan

    merged_df['Final_Height_cm'] = merged_df['ENR_FAHA-Q3_5_1'].fillna(merged_df['OUT_Height'])
    merged_df['Final_Weight_kg'] = merged_df['ENR_FAHA-Q3_6_1'].fillna(merged_df['OUT_Weight'])

    merged_df['Height_Source'] = np.where(merged_df['ENR_FAHA-Q3_5_1'].notna(), 'Enrolment', 
                                 np.where(merged_df['OUT_Height'].notna(), 'Outcome', 'Missing'))
    
    merged_df['Weight_Source'] = np.where(merged_df['ENR_FAHA-Q3_6_1'].notna(), 'Enrolment', 
                                 np.where(merged_df['OUT_Weight'].notna(), 'Outcome', 'Missing'))

    merged_df['Height_Missing'] = merged_df['Final_Height_cm'].isna()
    merged_df['Weight_Missing'] = merged_df['Final_Weight_kg'].isna()

    return merged_df

# --- 3. Helper Function for Excel Export ---
def convert_df_to_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Anthropometry_Data')
    return output.getvalue()

# --- 4. Main Application UI ---
df = fetch_and_process_data()

# Sidebar Filters
st.sidebar.header("Filters")
selected_cities = st.sidebar.multiselect(
    "Select Site (City):",
    options=df['City'].dropna().unique(),
    default=df['City'].dropna().unique()
)

# Apply Filter
filtered_df = df[df['City'].isin(selected_cities)]

st.subheader("Data Quality: Missing Anthropometry Metrics")
st.markdown("Displays counts of participants where height or weight is missing in **both** Enrolment and Outcome forms.")

# Dynamic Metric Cards per selected site
if not selected_cities:
    st.info("Please select at least one site from the sidebar.")
else:
    cols = st.columns(len(selected_cities))
    for idx, city in enumerate(selected_cities):
        city_data = filtered_df[filtered_df['City'] == city]
        missing_height = city_data['Height_Missing'].sum()
        missing_weight = city_data['Weight_Missing'].sum()
        
        with cols[idx]:
            st.metric(label=f"{city} - Missing Height", value=int(missing_height))
            st.metric(label=f"{city} - Missing Weight", value=int(missing_weight))

st.divider()

# Data Table Display
st.subheader("Extracted Participant Data")
columns_to_display = [
    'Participant_ID', 'City', 'SubmitterName', 'today', 
    'Final_Height_cm', 'Height_Source', 
    'Final_Weight_kg', 'Weight_Source'
]
st.dataframe(filtered_df[columns_to_display], use_container_width=True)

# Excel Download Button
st.subheader("Export Data")
excel_data = convert_df_to_excel(filtered_df)

st.download_button(
    label="📥 Download Data as Excel",
    data=excel_data,
    file_name="INSPIRES_Height_Weight_Data.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)
