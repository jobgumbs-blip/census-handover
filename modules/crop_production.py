import streamlit as st
import pandas as pd
import numpy as np
import io
import uuid
import json
import os
import logging
from datetime import datetime, date, timedelta
from typing import Dict, List, Tuple, Optional
from sqlalchemy import text, exc
import sys
import traceback

# Add project root to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Database connection
try:
    from db import engine
except ImportError:
    st.error("Database configuration not found. Running in standalone mode.")
    engine = None

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("crop_production.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("crop_production")

# Page configuration
st.set_page_config(
    page_title="Crop Production Management",
    layout="wide",
    page_icon="🌱"
)

# Custom CSS for better styling
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        color: #2e7d32;
        text-align: center;
        margin-bottom: 2rem;
        font-weight: 700;
        background: linear-gradient(135deg, #2e7d32 0%, #4caf50 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
    }
    .section-header {
        font-size: 1.5rem;
        color: #388e3c;
        border-bottom: 2px solid #c8e6c9;
        padding-bottom: 0.5rem;
        margin-top: 2rem;
        font-weight: 600;
    }
    .success-box {
        background-color: #e8f5e8;
        padding: 1rem;
        border-radius: 0.5rem;
        border-left: 4px solid #4caf50;
        margin: 1rem 0;
    }
    .error-box {
        background-color: #ffebee;
        padding: 1rem;
        border-radius: 0.5rem;
        border-left: 4px solid #f44336;
        margin: 1rem 0;
    }
    .info-box {
        background-color: #e3f2fd;
        padding: 1rem;
        border-radius: 0.5rem;
        border-left: 4px solid #2196f3;
        margin: 1rem 0;
    }
    .warning-box {
        background-color: #fff3cd;
        padding: 1rem;
        border-radius: 0.5rem;
        border-left: 4px solid #ffc107;
        margin: 1rem 0;
    }
    .stButton button {
        background-color: #4caf50;
        color: white;
        border: none;
        padding: 0.5rem 1rem;
        border-radius: 0.25rem;
        cursor: pointer;
        font-weight: 500;
        transition: all 0.3s ease;
    }
    .stButton button:hover {
        background-color: #45a049;
        transform: translateY(-1px);
        box-shadow: 0 2px 4px rgba(0,0,0,0.2);
    }
    .metric-card {
        background: white;
        padding: 1rem;
        border-radius: 0.5rem;
        border: 1px solid #e0e0e0;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        text-align: center;
    }
    .dataframe {
        font-size: 0.9rem;
    }
    .crop-card {
        background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
        padding: 1.5rem;
        border-radius: 0.5rem;
        margin: 0.5rem 0;
        border-left: 4px solid #4caf50;
    }
</style>
""", unsafe_allow_html=True)


class CropProductionManager:
    """Production-level crop production management system"""

    def __init__(self, holder_id=None, integrated_mode=False):
        self.holder_id = holder_id
        self.integrated_mode = integrated_mode
        self.initialize_data()

        # Planting material and market code mappings
        self.PLANTING_MATERIALS = {
            1: "Seeds", 2: "Seedlings", 3: "Cuttings", 4: "Tissue Plantlets",
            5: "Suckers", 6: "Tubers", 7: "Buds", 8: "Other"
        }

        self.MARKET_CODES = {
            1: "Local Market", 2: "Regional Market", 3: "National Market",
            4: "Export", 5: "Direct to Consumer", 6: "Wholesaler",
            7: "Processor", 8: "Institutional", 9: "Community Supported Agriculture",
            10: "Farmers Market", 11: "Other"
        }

        self.QUALITY_GRADES = ["Premium", "Grade A", "Grade B", "Grade C", "Utility"]
        self.CROP_TYPES = {"P": "Permanent", "T": "Temporary"}

    def initialize_data(self):
        """Initialize session state dataframes with production-level structure"""
        crop_columns = [
            "row_id", "holder_id", "Parcel", "Crop Name", "Crop Variety",
            "Cycle #", "Area (acres)", "# Organized", "# Scattered",
            "Planting Material (Code)", "Crop Type (P/T)", "Harvested?",
            "Planting Date", "Expected Harvest Date", "Status", "Notes",
            "created_at", "updated_at"
        ]

        harvest_columns = [
            "row_id", "holder_id", "Linked Crop Row ID", "# Produce Harvested (A-1)",
            "# Plants/Trees Harvested (A-2)", "Area Harvested (acres)",
            "Harvested Quantity (lbs/kg)", "Unit of Measure", "Market/Trade Code",
            "Harvest Date", "Quality Grade", "Revenue Generated", "Storage Location",
            "created_at", "updated_at"
        ]

        if "crop_df" not in st.session_state:
            st.session_state.crop_df = pd.DataFrame(columns=crop_columns)

        if "harvest_df" not in st.session_state:
            st.session_state.harvest_df = pd.DataFrame(columns=harvest_columns)

        if "crop_data_loaded" not in st.session_state:
            st.session_state.crop_data_loaded = False

    def load_data_from_database(self):
        """Load crop and harvest data from database"""
        if not engine or not self.holder_id:
            logger.warning("No database connection or holder ID provided")
            return False

        try:
            with engine.connect() as conn:
                # Load crop data
                crops_df = pd.read_sql(
                    text("""
                        SELECT * FROM crop_production 
                        WHERE holder_id = :holder_id 
                        ORDER BY created_at DESC
                    """),
                    conn,
                    params={"holder_id": self.holder_id}
                )

                # Load harvest data
                harvests_df = pd.read_sql(
                    text("""
                        SELECT * FROM harvest_records 
                        WHERE holder_id = :holder_id 
                        ORDER BY harvest_date DESC
                    """),
                    conn,
                    params={"holder_id": self.holder_id}
                )

                if not crops_df.empty:
                    st.session_state.crop_df = crops_df
                    logger.info(f"Loaded {len(crops_df)} crop records for holder {self.holder_id}")

                if not harvests_df.empty:
                    st.session_state.harvest_df = harvests_df
                    logger.info(f"Loaded {len(harvests_df)} harvest records for holder {self.holder_id}")

                st.session_state.crop_data_loaded = True
                return True

        except Exception as e:
            logger.error(f"Error loading crop data from database: {str(e)}")
            st.error(f"Failed to load existing crop data: {str(e)}")
            return False

    def save_data_to_database(self):
        """Save crop and harvest data to database"""
        if not engine or not self.holder_id:
            logger.warning("Cannot save data: No database connection or holder ID")
            return False

        try:
            with engine.begin() as conn:
                # Clear existing data for this holder
                conn.execute(
                    text("DELETE FROM harvest_records WHERE holder_id = :holder_id"),
                    {"holder_id": self.holder_id}
                )
                conn.execute(
                    text("DELETE FROM crop_production WHERE holder_id = :holder_id"),
                    {"holder_id": self.holder_id}
                )

                # Prepare and save crop data
                if not st.session_state.crop_df.empty:
                    crop_data = st.session_state.crop_df.copy()
                    crop_data["holder_id"] = self.holder_id
                    crop_data["updated_at"] = datetime.now()

                    # Ensure required columns exist
                    for col in ["created_at", "Status", "Notes"]:
                        if col not in crop_data.columns:
                            crop_data[col] = "" if col == "Notes" else "Active" if col == "Status" else datetime.now()

                    crop_data.to_sql("crop_production", conn, if_exists="append", index=False)
                    logger.info(f"Saved {len(crop_data)} crop records to database")

                # Prepare and save harvest data
                if not st.session_state.harvest_df.empty:
                    harvest_data = st.session_state.harvest_df.copy()
                    harvest_data["holder_id"] = self.holder_id
                    harvest_data["updated_at"] = datetime.now()

                    # Ensure required columns exist
                    for col in ["created_at", "Unit of Measure", "Revenue Generated", "Storage Location"]:
                        if col not in harvest_data.columns:
                            harvest_data[col] = "" if col in ["Unit of Measure",
                                                              "Storage Location"] else 0.0 if col == "Revenue Generated" else datetime.now()

                    harvest_data.to_sql("harvest_records", conn, if_exists="append", index=False)
                    logger.info(f"Saved {len(harvest_data)} harvest records to database")

                st.success("✅ Crop production data saved successfully!")
                return True

        except Exception as e:
            logger.error(f"Error saving crop data to database: {str(e)}")
            st.error(f"Failed to save crop data: {str(e)}")
            return False

    def add_crop_row(self):
        """Add a new crop row with default values"""
        new_id = str(uuid.uuid4())
        today = datetime.now().date()

        new_row = {
            "row_id": new_id,
            "holder_id": self.holder_id,
            "Parcel": "",
            "Crop Name": "",
            "Crop Variety": "",
            "Cycle #": 1,
            "Area (acres)": 0.0,
            "# Organized": 0,
            "# Scattered": 0,
            "Planting Material (Code)": 1,
            "Crop Type (P/T)": "T",
            "Harvested?": False,
            "Planting Date": today,
            "Expected Harvest Date": today + timedelta(days=90),
            "Status": "Planted",
            "Notes": "",
            "created_at": datetime.now(),
            "updated_at": datetime.now()
        }

        st.session_state.crop_df = pd.concat([
            st.session_state.crop_df,
            pd.DataFrame([new_row])
        ], ignore_index=True)

        logger.info(f"Added new crop row with ID: {new_id}")

    def add_harvest_row(self, linked_row_id=None):
        """Add a new harvest row with optional crop linkage"""
        new_id = str(uuid.uuid4())
        today = datetime.now().date()

        new_row = {
            "row_id": new_id,
            "holder_id": self.holder_id,
            "Linked Crop Row ID": linked_row_id or "",
            "# Produce Harvested (A-1)": 0,
            "# Plants/Trees Harvested (A-2)": 0,
            "Area Harvested (acres)": 0.0,
            "Harvested Quantity (lbs/kg)": 0.0,
            "Unit of Measure": "kg",
            "Market/Trade Code": 1,
            "Harvest Date": today,
            "Quality Grade": "Grade A",
            "Revenue Generated": 0.0,
            "Storage Location": "",
            "created_at": datetime.now(),
            "updated_at": datetime.now()
        }

        st.session_state.harvest_df = pd.concat([
            st.session_state.harvest_df,
            pd.DataFrame([new_row])
        ], ignore_index=True)

        logger.info(f"Added new harvest row with ID: {new_id}")

    def validate_data(self) -> Tuple[List[str], List[str]]:
        """Comprehensive data validation with production-level checks"""
        errors = []
        warnings = []

        # Validate crop data
        for idx, row in st.session_state.crop_df.iterrows():
            rownum = idx + 1

            # Required fields validation
            if not self._validate_required_field(row, "Parcel", f"Crop row {rownum}"):
                errors.append(f"Crop row {rownum}: Parcel name is required")

            if not self._validate_required_field(row, "Crop Name", f"Crop row {rownum}"):
                errors.append(f"Crop row {rownum}: Crop name is required")

            # Numeric validations
            errors.extend(self._validate_numeric_field(row, "Cycle #", 1, 30, f"Crop row {rownum}"))
            errors.extend(self._validate_numeric_field(row, "Area (acres)", 0.001, 1000, f"Crop row {rownum}"))

            # Date validations
            if not self._validate_date_sequence(row, "Planting Date", "Expected Harvest Date", f"Crop row {rownum}"):
                errors.append(f"Crop row {rownum}: Expected harvest date must be after planting date")

        # Validate harvest data
        for idx, row in st.session_state.harvest_df.iterrows():
            rownum = idx + 1

            errors.extend(
                self._validate_numeric_field(row, "Area Harvested (acres)", 0.001, 1000, f"Harvest row {rownum}"))
            errors.extend(
                self._validate_numeric_field(row, "Harvested Quantity (lbs/kg)", 0.01, 100000, f"Harvest row {rownum}"))

            # Link validation
            linked_id = row.get("Linked Crop Row ID")
            if linked_id and linked_id not in st.session_state.crop_df["row_id"].values:
                warnings.append(f"Harvest row {rownum}: Linked crop record not found")

        # Data integrity checks
        integrity_warnings = self._check_data_integrity()
        warnings.extend(integrity_warnings)

        return errors, warnings

    def _validate_required_field(self, row, field_name, context):
        """Validate required field"""
        value = row.get(field_name)
        return value is not None and str(value).strip() != ""

    def _validate_numeric_field(self, row, field_name, min_val, max_val, context):
        """Validate numeric field range"""
        errors = []
        try:
            value = float(row.get(field_name, 0))
            if not (min_val <= value <= max_val):
                errors.append(f"{context}: {field_name} must be between {min_val} and {max_val}")
        except (ValueError, TypeError):
            errors.append(f"{context}: {field_name} must be a valid number")
        return errors

    def _validate_date_sequence(self, row, start_date_field, end_date_field, context):
        """Validate that end date is after start date"""
        try:
            start_date = row.get(start_date_field)
            end_date = row.get(end_date_field)

            if isinstance(start_date, str):
                start_date = datetime.strptime(start_date, "%Y-%m-%d").date()
            if isinstance(end_date, str):
                end_date = datetime.strptime(end_date, "%Y-%m-%d").date()

            return start_date <= end_date
        except:
            return True  # Skip validation if dates are invalid

    def _check_data_integrity(self):
        """Check for data consistency issues"""
        warnings = []

        # Check if harvest area exceeds planted area
        for _, harvest_row in st.session_state.harvest_df.iterrows():
            linked_crop_id = harvest_row["Linked Crop Row ID"]
            if linked_crop_id:
                crop_match = st.session_state.crop_df[
                    st.session_state.crop_df["row_id"] == linked_crop_id
                    ]
                if not crop_match.empty:
                    crop_row = crop_match.iloc[0]
                    crop_area = crop_row["Area (acres)"]
                    harvest_area = harvest_row["Area Harvested (acres)"]

                    if harvest_area > crop_area:
                        warnings.append(
                            f"Harvest area ({harvest_area} acres) exceeds planted area "
                            f"({crop_area} acres) for {crop_row['Crop Name']} in {crop_row['Parcel']}"
                        )

        return warnings

    def generate_analytics(self):
        """Generate comprehensive analytics and insights"""
        analytics = {}

        if not st.session_state.crop_df.empty:
            # Basic metrics
            analytics["total_crops"] = len(st.session_state.crop_df)
            analytics["total_area"] = st.session_state.crop_df["Area (acres)"].sum()
            analytics["harvested_count"] = st.session_state.crop_df["Harvested?"].sum()

            # Crop type distribution
            analytics["crop_type_dist"] = st.session_state.crop_df["Crop Type (P/T)"].value_counts()

            # Top crops by area
            analytics["top_crops"] = st.session_state.crop_df.nlargest(5, "Area (acres)")[["Crop Name", "Area (acres)"]]

        if not st.session_state.harvest_df.empty:
            # Harvest metrics
            analytics["total_harvest_qty"] = st.session_state.harvest_df["Harvested Quantity (lbs/kg)"].sum()
            analytics["total_harvest_area"] = st.session_state.harvest_df["Area Harvested (acres)"].sum()
            analytics["total_revenue"] = st.session_state.harvest_df["Revenue Generated"].sum()

            # Market distribution
            analytics["market_dist"] = st.session_state.harvest_df["Market/Trade Code"].value_counts().head(5)

        return analytics

    def render_crop_management_tab(self):
        """Render the crop management interface"""
        st.markdown('<div class="section-header">🌿 Crop Information Management</div>', unsafe_allow_html=True)

        # Management controls
        col1, col2, col3 = st.columns([1, 1, 1])

        with col1:
            if st.button("➕ Add New Crop", use_container_width=True, key="add_crop"):
                self.add_crop_row()
                st.rerun()

        with col2:
            if st.button("🔄 Load Sample Data", use_container_width=True, key="load_sample"):
                self.load_sample_data()
                st.rerun()

        with col3:
            if st.session_state.crop_df.empty:
                st.info("No crop data")
            else:
                st.metric("Total Crops", len(st.session_state.crop_df))

        # Display and edit crop data
        if st.session_state.crop_df.empty:
            st.markdown(
                '<div class="info-box">No crop records yet. Use "Add New Crop" to get started or load sample data for demonstration.</div>',
                unsafe_allow_html=True)
        else:
            self.render_crop_data_editor()

    def render_crop_data_editor(self):
        """Render editable crop data table"""
        st.subheader("Crop Records")

        # Create display dataframe with friendly names
        display_df = st.session_state.crop_df.copy()
        display_df["Planting Material"] = display_df["Planting Material (Code)"].map(self.PLANTING_MATERIALS)
        display_df["Crop Type"] = display_df["Crop Type (P/T)"].map(self.CROP_TYPES)

        # Select columns to display
        display_columns = [
            "Parcel", "Crop Name", "Crop Variety", "Cycle #", "Area (acres)",
            "Planting Material", "Crop Type", "Harvested?", "Planting Date",
            "Expected Harvest Date", "Status"
        ]

        edited_df = st.data_editor(
            display_df[display_columns],
            column_config={
                "Parcel": st.column_config.TextColumn("Parcel", required=True),
                "Crop Name": st.column_config.TextColumn("Crop Name", required=True),
                "Crop Variety": st.column_config.TextColumn("Variety"),
                "Cycle #": st.column_config.NumberColumn("Cycle", min_value=1, max_value=30),
                "Area (acres)": st.column_config.NumberColumn("Area (acres)", min_value=0.001, max_value=1000,
                                                              format="%.3f"),
                "Planting Material": st.column_config.SelectboxColumn("Planting Material",
                                                                      options=list(self.PLANTING_MATERIALS.values())),
                "Crop Type": st.column_config.SelectboxColumn("Crop Type", options=list(self.CROP_TYPES.values())),
                "Harvested?": st.column_config.CheckboxColumn("Harvested?"),
                "Planting Date": st.column_config.DateColumn("Planting Date"),
                "Expected Harvest Date": st.column_config.DateColumn("Expected Harvest"),
                "Status": st.column_config.SelectboxColumn("Status",
                                                           options=["Planned", "Planted", "Growing", "Harvested",
                                                                    "Failed"])
            },
            num_rows="dynamic",
            use_container_width=True,
            key="crop_editor"
        )

        # Update original dataframe with edits
        if not edited_df.empty and len(edited_df) == len(display_df):
            # Map back to original codes
            reverse_material_map = {v: k for k, v in self.PLANTING_MATERIALS.items()}
            reverse_type_map = {v: k for k, v in self.CROP_TYPES.items()}

            st.session_state.crop_df[display_columns] = edited_df
            st.session_state.crop_df["Planting Material (Code)"] = edited_df["Planting Material"].map(
                reverse_material_map)
            st.session_state.crop_df["Crop Type (P/T)"] = edited_df["Crop Type"].map(reverse_type_map)

    def render_harvest_tracking_tab(self):
        """Render the harvest tracking interface"""
        st.markdown('<div class="section-header">📈 Harvest Information Tracking</div>', unsafe_allow_html=True)

        # Harvest controls
        col1, col2 = st.columns([1, 1])

        with col1:
            if st.button("➕ Add Harvest Record", use_container_width=True, key="add_harvest"):
                self.add_harvest_row()
                st.rerun()

        with col2:
            if st.button("🔗 Auto-link Harvests", use_container_width=True, key="auto_link"):
                self.auto_link_harvests()
                st.rerun()

        # Display harvest data
        if st.session_state.harvest_df.empty:
            st.markdown(
                '<div class="info-box">No harvest records yet. Add harvest records or use auto-link to connect harvests to crops.</div>',
                unsafe_allow_html=True)
        else:
            self.render_harvest_data_editor()

    def render_harvest_data_editor(self):
        """Render editable harvest data table"""
        st.subheader("Harvest Records")

        # Create display dataframe
        display_df = st.session_state.harvest_df.copy()

        # Add crop information for display
        crop_info_map = {}
        for _, crop_row in st.session_state.crop_df.iterrows():
            crop_info_map[crop_row["row_id"]] = f"{crop_row['Parcel']} - {crop_row['Crop Name']}"

        display_df["Linked Crop"] = display_df["Linked Crop Row ID"].map(crop_info_map)
        display_df["Market"] = display_df["Market/Trade Code"].map(self.MARKET_CODES)

        # Select columns to display
        display_columns = [
            "Linked Crop", "# Produce Harvested (A-1)", "# Plants/Trees Harvested (A-2)",
            "Area Harvested (acres)", "Harvested Quantity (lbs/kg)", "Unit of Measure",
            "Market", "Harvest Date", "Quality Grade", "Revenue Generated", "Storage Location"
        ]

        edited_df = st.data_editor(
            display_df[display_columns],
            column_config={
                "Linked Crop": st.column_config.SelectboxColumn(
                    "Linked Crop",
                    options=[""] + [crop_info_map[rid] for rid in st.session_state.crop_df["row_id"]]
                ),
                "# Produce Harvested (A-1)": st.column_config.NumberColumn("Produce Harvested", min_value=0),
                "# Plants/Trees Harvested (A-2)": st.column_config.NumberColumn("Plants/Trees Harvested", min_value=0),
                "Area Harvested (acres)": st.column_config.NumberColumn("Area Harvested", min_value=0.001,
                                                                        format="%.3f"),
                "Harvested Quantity (lbs/kg)": st.column_config.NumberColumn("Quantity", min_value=0.01, format="%.2f"),
                "Unit of Measure": st.column_config.SelectboxColumn("Unit", options=["kg", "lbs", "tons", "bushels"]),
                "Market": st.column_config.SelectboxColumn("Market", options=list(self.MARKET_CODES.values())),
                "Harvest Date": st.column_config.DateColumn("Harvest Date"),
                "Quality Grade": st.column_config.SelectboxColumn("Quality", options=self.QUALITY_GRADES),
                "Revenue Generated": st.column_config.NumberColumn("Revenue", min_value=0, format="%.2f"),
                "Storage Location": st.column_config.TextColumn("Storage Location")
            },
            num_rows="dynamic",
            use_container_width=True,
            key="harvest_editor"
        )

        # Update original dataframe with edits
        if not edited_df.empty and len(edited_df) == len(display_df):
            # Map back to original codes
            reverse_crop_map = {v: k for k, v in crop_info_map.items()}
            reverse_market_map = {v: k for k, v in self.MARKET_CODES.items()}

            st.session_state.harvest_df[display_columns] = edited_df
            st.session_state.harvest_df["Linked Crop Row ID"] = edited_df["Linked Crop"].map(reverse_crop_map)
            st.session_state.harvest_df["Market/Trade Code"] = edited_df["Market"].map(reverse_market_map)

    def auto_link_harvests(self):
        """Automatically create harvest records for harvested crops"""
        added_count = 0
        for _, crop_row in st.session_state.crop_df.iterrows():
            if crop_row.get("Harvested?") and not st.session_state.harvest_df[
                                                      st.session_state.harvest_df["Linked Crop Row ID"] == crop_row[
                                                          "row_id"]
                                                  ].shape[0] > 0:
                self.add_harvest_row(linked_row_id=crop_row["row_id"])
                added_count += 1

        if added_count > 0:
            st.success(f"Added {added_count} harvest records for harvested crops!")
        else:
            st.info("No new harvest records needed.")

    def load_sample_data(self):
        """Load sample data for demonstration"""
        sample_crops = [
            {
                "Parcel": "North Field", "Crop Name": "Maize", "Crop Variety": "Hybrid",
                "Cycle #": 1, "Area (acres)": 5.0, "Planting Material (Code)": 1,
                "Crop Type (P/T)": "T", "Harvested?": True, "Status": "Harvested"
            },
            {
                "Parcel": "South Orchard", "Crop Name": "Mango", "Crop Variety": "Tommy Atkins",
                "Cycle #": 1, "Area (acres)": 2.5, "Planting Material (Code)": 2,
                "Crop Type (P/T)": "P", "Harvested?": False, "Status": "Growing"
            }
        ]

        for crop in sample_crops:
            self.add_crop_row()
            # Update the last added row with sample data
            last_idx = len(st.session_state.crop_df) - 1
            for key, value in crop.items():
                st.session_state.crop_df.at[last_idx, key] = value

        st.success("Sample crop data loaded!")

    def render_validation_tab(self):
        """Render data validation and export interface"""
        st.markdown('<div class="section-header">✅ Data Validation & Export</div>', unsafe_allow_html=True)

        col1, col2 = st.columns([1, 1])

        with col1:
            self.render_validation_section()

        with col2:
            self.render_export_section()

    def render_validation_section(self):
        """Render data validation section"""
        st.subheader("🔍 Data Validation")

        if st.button("Run Comprehensive Validation", use_container_width=True, key="validate_data"):
            with st.spinner("Validating data..."):
                errors, warnings = self.validate_data()

                if errors:
                    st.markdown('<div class="error-box">', unsafe_allow_html=True)
                    st.error("❌ Validation failed with errors:")
                    for error in errors:
                        st.write(f"• {error}")
                    st.markdown('</div>', unsafe_allow_html=True)
                else:
                    st.markdown('<div class="success-box">', unsafe_allow_html=True)
                    st.success("✅ All data valid!")
                    st.markdown('</div>', unsafe_allow_html=True)

                if warnings:
                    st.markdown('<div class="warning-box">', unsafe_allow_html=True)
                    st.warning("⚠️ Data integrity warnings:")
                    for warning in warnings:
                        st.write(f"• {warning}")
                    st.markdown('</div>', unsafe_allow_html=True)

    def render_export_section(self):
        """Render data export section"""
        st.subheader("📤 Data Export")

        if st.session_state.crop_df.empty and st.session_state.harvest_df.empty:
            st.info("No data available for export")
            return

        # Excel Export
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
            if not st.session_state.crop_df.empty:
                export_crop_df = st.session_state.crop_df.drop(columns=['row_id', 'holder_id'], errors='ignore')
                export_crop_df.to_excel(writer, sheet_name='Crop_Information', index=False)

            if not st.session_state.harvest_df.empty:
                export_harvest_df = st.session_state.harvest_df.drop(columns=['row_id', 'holder_id'], errors='ignore')
                export_harvest_df.to_excel(writer, sheet_name='Harvest_Information', index=False)

        buffer.seek(0)

        st.download_button(
            label="📊 Download Excel Report",
            data=buffer,
            file_name=f"crop_production_report_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
            mime="application/vnd.ms-excel",
            use_container_width=True
        )

        # JSON Export
        if st.button("💾 Export as JSON", use_container_width=True):
            export_data = {
                "metadata": {
                    "export_date": datetime.now().isoformat(),
                    "holder_id": self.holder_id,
                    "record_counts": {
                        "crops": len(st.session_state.crop_df),
                        "harvests": len(st.session_state.harvest_df)
                    }
                },
                "crop_data": st.session_state.crop_df.to_dict('records'),
                "harvest_data": st.session_state.harvest_df.to_dict('records')
            }

            st.download_button(
                label="📥 Download JSON Data",
                data=json.dumps(export_data, indent=2, default=str),
                file_name=f"crop_data_{datetime.now().strftime('%Y%m%d')}.json",
                mime="application/json",
                use_container_width=True
            )

    def render_analytics_tab(self):
        """Render analytics and summary dashboard"""
        st.markdown('<div class="section-header">📊 Production Analytics & Summary</div>', unsafe_allow_html=True)

        if st.session_state.crop_df.empty and st.session_state.harvest_df.empty:
            st.info("No data available for analytics. Add crop and harvest records to see insights.")
            return

        analytics = self.generate_analytics()

        # Key Metrics
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric("Total Crops", analytics.get("total_crops", 0))

        with col2:
            st.metric("Total Area", f"{analytics.get('total_area', 0):.2f} acres")

        with col3:
            st.metric("Harvested Crops", f"{analytics.get('harvested_count', 0)}")

        with col4:
            if "total_harvest_qty" in analytics:
                st.metric("Total Harvest", f"{analytics['total_harvest_qty']:.1f} kg")
            else:
                st.metric("Ready for Harvest",
                          f"{analytics.get('total_crops', 0) - analytics.get('harvested_count', 0)}")

        # Detailed Analytics
        col_left, col_right = st.columns(2)

        with col_left:
            st.subheader("Crop Distribution")
            if not st.session_state.crop_df.empty:
                # Crop type distribution
                if "crop_type_dist" in analytics:
                    st.write("**By Crop Type:**")
                    for crop_type, count in analytics["crop_type_dist"].items():
                        st.write(f"- {self.CROP_TYPES.get(crop_type, crop_type)}: {count} crops")

                # Top crops by area
                if "top_crops" in analytics and not analytics["top_crops"].empty:
                    st.write("**Top Crops by Area:**")
                    for _, row in analytics["top_crops"].iterrows():
                        st.write(f"- {row['Crop Name']}: {row['Area (acres)']} acres")

        with col_right:
            st.subheader("Harvest Insights")
            if not st.session_state.harvest_df.empty:
                if "total_revenue" in analytics:
                    st.metric("Total Revenue", f"${analytics['total_revenue']:,.2f}")

                if "market_dist" in analytics:
                    st.write("**Top Markets:**")
                    for market_code, count in analytics["market_dist"].items():
                        market_name = self.MARKET_CODES.get(market_code, "Unknown")
                        st.write(f"- {market_name}: {count} records")

    def render_integration_controls(self):
        """Render integration-specific controls"""
        if not self.integrated_mode:
            return

        st.markdown("---")
        st.markdown("### 🔗 Survey Integration")

        col1, col2 = st.columns(2)

        with col1:
            if st.button("💾 Save to Survey", type="primary", use_container_width=True):
                if self.save_data_to_database():
                    return True

        with col2:
            if st.button("🔄 Reload from Database", use_container_width=True):
                self.load_data_from_database()
                st.rerun()

        return False

    def run(self):
        """Main execution method"""
        # Application title
        st.markdown('<div class="main-header">🌱 Crop Production Management System</div>', unsafe_allow_html=True)

        # Load data if in integrated mode
        if self.integrated_mode and not st.session_state.crop_data_loaded:
            self.load_data_from_database()

        # Create tabs
        tab1, tab2, tab3, tab4 = st.tabs([
            "🌿 Crop Management",
            "📈 Harvest Tracking",
            "✅ Validation & Export",
            "📊 Analytics"
        ])

        with tab1:
            self.render_crop_management_tab()

        with tab2:
            self.render_harvest_tracking_tab()

        with tab3:
            self.render_validation_tab()

        with tab4:
            self.render_analytics_tab()

        # Integration controls
        if self.integrated_mode:
            section_completed = self.render_integration_controls()
            return section_completed

        return False


def main(holder_id=None, integrated_mode=False):
    """
    Main function with production-level error handling and integration support

    Args:
        holder_id: Optional holder ID for database integration
        integrated_mode: Whether running as part of larger application

    Returns:
        bool: Whether the section is considered complete
    """
    try:
        # Initialize manager
        manager = CropProductionManager(holder_id, integrated_mode)

        # Run the application
        section_completed = manager.run()

        # Determine completion status for integrated mode
        if integrated_mode:
            # Consider section complete if there's at least one valid crop record
            if not manager.validate_data()[0]:  # No errors
                if not st.session_state.crop_df.empty:
                    return True

        return section_completed

    except Exception as e:
        logger.error(f"Error in crop production system: {str(e)}")
        logger.error(traceback.format_exc())

        st.markdown('<div class="error-box">', unsafe_allow_html=True)
        st.error(f"🚨 System Error: {str(e)}")
        st.markdown('</div>', unsafe_allow_html=True)

        st.info("💡 Please refresh the page and try again. If the problem persists, contact support.")
        return False


# Standalone execution
if __name__ == "__main__":
    # Run in standalone mode
    main()