import streamlit as st
import pandas as pd
from sqlalchemy import text
from db import engine

def crop_production_section(holder_id):
    """
    Integrated crop production section that works with your main app
    """
    st.markdown("### 🌱 Crop Production Intelligence")
    
    # Check for existing data
    with engine.connect() as conn:
        existing_crops = conn.execute(
            text("SELECT COUNT(*) FROM crop_production WHERE holder_id = :hid"),
            {"hid": holder_id}
        ).scalar()
        
        existing_harvests = conn.execute(
            text("SELECT COUNT(*) FROM harvest_records WHERE holder_id = :hid"),
            {"hid": holder_id}
        ).scalar()
    
    # Initialize session state if needed
    if "crop_data_loaded" not in st.session_state:
        load_crop_data_from_db(holder_id)
        st.session_state.crop_data_loaded = True
    
    # Use the crop production system
    from crop_production import main as crop_main
    
    # Run the crop production system in integrated mode
    completion_status = crop_main(holder_id, integrated_mode=True)
    
    return completion_status

def load_crop_data_from_db(holder_id):
    """Load existing crop data from database into session state"""
    try:
        with engine.connect() as conn:
            # Load crop data
            crops_df = pd.read_sql(
                text("SELECT * FROM crop_production WHERE holder_id = :hid"),
                conn, 
                params={"hid": holder_id}
            )
            
            # Load harvest data  
            harvests_df = pd.read_sql(
                text("SELECT * FROM harvest_records WHERE holder_id = :hid"),
                conn,
                params={"hid": holder_id}
            )
            
            if not crops_df.empty:
                st.session_state.crop_df = crops_df
            if not harvests_df.empty:
                st.session_state.harvest_df = harvests_df
                
    except Exception as e:
        st.info("No existing crop data found. Starting fresh.")
        # Initialize empty dataframes
        st.session_state.crop_df = pd.DataFrame(columns=[
            "row_id", "holder_id", "Parcel", "Crop Name", "Cycle #", 
            "Area (acres)", "# Organized", "# Scattered", "Planting Material (Code)",
            "Crop Type (P/T)", "Harvested?", "Planting Date", "Expected Harvest Date"
        ])
        st.session_state.harvest_df = pd.DataFrame(columns=[
            "row_id", "holder_id", "Linked Crop Row ID", "# Produce Harvested (A-1)",
            "# Plants/Trees Harvested (A-2)", "Area Harvested (acres)", 
            "Harvested Quantity (lbs/kg)", "Market/Trade Code", "Harvest Date", "Quality Grade"
        ])

def save_crop_data_to_db(holder_id):
    """Save crop data to database"""
    try:
        with engine.begin() as conn:
            # Clear existing data
            conn.execute(
                text("DELETE FROM harvest_records WHERE holder_id = :hid"),
                {"hid": holder_id}
            )
            conn.execute(
                text("DELETE FROM crop_production WHERE holder_id = :hid"), 
                {"hid": holder_id}
            )
            
            # Save new crop data
            if not st.session_state.crop_df.empty:
                crop_data = st.session_state.crop_df.copy()
                crop_data["holder_id"] = holder_id
                crop_data.to_sql("crop_production", conn, if_exists="append", index=False)
            
            # Save harvest data
            if not st.session_state.harvest_df.empty:
                harvest_data = st.session_state.harvest_df.copy() 
                harvest_data["holder_id"] = holder_id
                harvest_data.to_sql("harvest_records", conn, if_exists="append", index=False)
                
        return True
    except Exception as e:
        st.error(f"Failed to save crop data: {e}")
        return False

def validate_crop_section_completion():
    """Validate if crop section is complete enough to mark as done"""
    if st.session_state.crop_df.empty:
        return False
    
    # Check required fields in crop data
    required_fields = ["Parcel", "Crop Name", "Area (acres)", "Crop Type (P/T)"]
    for _, row in st.session_state.crop_df.iterrows():
        for field in required_fields:
            if pd.isna(row.get(field)) or row.get(field) in ["", None]:
                return False
    
    return True