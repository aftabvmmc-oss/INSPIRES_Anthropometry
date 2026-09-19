import streamlit as st
import pandas as pd
import numpy as np
import io

# --- 1. Page Configuration ---
st.set_page_config(page_title="INSPIRES Study: Anthropometry Tracker", layout="wide")
st.title("INSPIRES Study: Height & Weight Dashboard")

# --- 2. Data Fetching & Processing ---
@st.cache_data
def fetch_and_process_data():
    # Placeholder for actual data fetching logic (e.g., via ODK Central API)
    # credentials = st.secrets["api_credentials"]
    
    # Mock data loading - Replace these with your actual API GET requests returning DataFrames
    # enr_df = pd.read_csv("api_endpoint/ENR_2024")
    # out_df = pd.read_csv("api_endpoint/OUT_2024")
    
    # --- MOCK DATA FOR TESTING PURPOSES ---
    enr_df = pd.DataFrame({
        "ENR_BINFO-C_8": ["P001", "P002", "P003", "P004"],
        "ENR_BINFO-Q1_2": ["NC", "JO", "GU", "KO"],
        "SubmitterName": ["Data_Col_1", "Data_Col_2", "Data_Col_1", "Data_Col_3"],
        "today": ["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04"],
        "ENR_FAHA-Q3_5": [1, 2, 1, 2],
        "ENR_FAHA-Q3_5_1": [170.0, np.nan, 165.0, np.nan],
        "ENR_FAHA-Q3_6": [1, 2, 2, 1],
        "ENR_FAHA-Q3_6_1": [70.0, np.nan, np.nan, 65.0]
    })
    
    out_df = pd.DataFrame({
        "OUT-P_ID": ["P002", "P003", "P004"],
        "SubmitterName": ["Data_Col_2", "Data_Col_1", "Data_Col_3"],
        "today": ["2024-02-01", "2024-02-02", "2024-02-03"],
        "OUT-Q1_11_1a": [180.0, np.nan, 160.0],
        "OUT-Q1_12_1a": [80.0, 75.0, np.nan]
    })
    # --------------------------------------

    # Rename keys for standardizing
    enr_df = enr_df.rename(columns={"ENR_BINFO-C_8": "Participant_ID", "ENR_BINFO-Q1_2": "Site_Code"})
    out_df = out_df.rename(columns={"OUT-P_ID": "Participant_ID"})

    # Map Site Codes to City Names
    site_mapping = {
        "NC": "NCT DELHI",
        "JO": "JODHPUR",
        "GU": "GUWAHATI",
        "KO": "KOLKATA",
        "CH": "CHENNAI",
        "PU": "PUNE"
    }
    enr_df['City'] = enr_df['Site_Code'].map(site_mapping)

    # Prepare Outcome data for merging
    out_subset = out_df[['Participant_ID', 'OUT-Q1_11_1a', 'OUT-Q1_12_1a', 'SubmitterName', 'today']].copy()
    out_subset.columns = ['Participant_ID', 'OUT_Height', 'OUT_Weight', 'OUT_Submitter', 'OUT_Date']

    # Merge datasets on Participant ID
    merged_df = pd.merge(enr_df, out_subset, on="Participant_ID", how="left")

    # Resolve Final Height and Weight (Fallback to Outcome form if Enrolment is NaN)
    merged_df['Final_Height_cm'] = merged_df['ENR_FAHA-Q3_5_1'].fillna(merged_df['OUT_Height'])
    merged_df['Final_Weight_kg'] = merged_df['ENR_FAHA-Q3_6_1'].fillna(merged_df['OUT_Weight'])

    # Determine Source of Data for transparency
    merged_df['Height_Source'] = np.where(merged_df['ENR_FAHA-Q3_5_1'].notna(), 'Enrolment', 
                                 np.where(merged_df['OUT_Height'].notna(), 'Outcome', 'Missing'))
    
    merged_df['Weight_Source'] = np.where(merged_df['ENR_FAHA-Q3_6_1'].notna(), 'Enrolment', 
                                 np.where(merged_df['OUT_Weight'].notna(), 'Outcome', 'Missing'))

    # Flag strictly missing records (missing in BOTH forms)
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