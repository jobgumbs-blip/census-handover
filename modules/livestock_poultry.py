import streamlit as st
import pandas as pd
import numpy as np
import uuid
import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from sqlalchemy import text
import sys
import os

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
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("livestock_poultry")

class LivestockPoultryManager:
    """Production-level livestock and poultry management system"""
    
    def __init__(self, holder_id=None, integrated_mode=False):
        self.holder_id = holder_id
        self.integrated_mode = integrated_mode
        self.initialize_session_state()
        
        # Livestock configuration
        self.LIVESTOCK_TYPES = [
            "Cattle", "Sheep", "Goats", "Pigs", "Horse Kind"
        ]
        
        self.POULTRY_TYPES = [
            "Chicken", "Duck", "Goose", "Turkey"
        ]
        
        self.AGE_GROUPS = [
            "Less than 6 months",
            "6 months to 1 year", 
            "1 to 2 years",
            "More than 2 years"
        ]
        
        self.DISPOSAL_CODES = {
            1: "Sold",
            2: "Died", 
            3: "Stolen",
            4: "Slaughtered (settlement)",
            5: "Slaughtered (Abattoir)",
            6: "Slaughtered (self)"
        }
        
        self.PRODUCTION_SYSTEMS = ["Grazing", "Mixed", "Industrial"]
        self.MANAGEMENT_METHODS = ["Free Range", "Penned", "Pasture-raised"]
        self.DEAD_ANIMAL_DISPOSAL = ["Not Applicable", "Burning", "Compost", "Landfill", "Other"]
        
    def initialize_session_state(self):
        """Initialize session state for livestock data"""
        if "livestock_own_animals" not in st.session_state:
            st.session_state.livestock_own_animals = None
            
        if "livestock_data" not in st.session_state:
            st.session_state.livestock_data = {}
            
        if "poultry_data" not in st.session_state:
            st.session_state.poultry_data = {}
            
        if "disposal_data" not in st.session_state:
            st.session_state.disposal_data = {}
            
        if "additional_info" not in st.session_state:
            st.session_state.additional_info = {
                "production_system": "",
                "management_method": "",
                "dead_animal_disposal": "",
                "dead_animal_disposal_other": "",
                "vet_services_used": None,
                "vet_service_type": ""
            }
            
        if "livestock_data_loaded" not in st.session_state:
            st.session_state.livestock_data_loaded = False

    def load_data_from_database(self):
        """Load livestock data from database"""
        if not engine or not self.holder_id:
            logger.warning("No database connection or holder ID provided")
            return False
            
        try:
            with engine.connect() as conn:
                # Load livestock ownership
                ownership = conn.execute(
                    text("SELECT owns_livestock FROM livestock_ownership WHERE holder_id = :holder_id"),
                    {"holder_id": self.holder_id}
                ).scalar()
                
                if ownership is not None:
                    st.session_state.livestock_own_animals = "Yes" if ownership else "No"
                
                # Load livestock inventory
                livestock_inventory = pd.read_sql(
                    text("SELECT * FROM livestock_inventory WHERE holder_id = :holder_id"),
                    conn, 
                    params={"holder_id": self.holder_id}
                )
                
                if not livestock_inventory.empty:
                    for _, row in livestock_inventory.iterrows():
                        animal_type = row['animal_type']
                        st.session_state.livestock_data[animal_type] = {
                            'medicines': row.get('medicines_used', ''),
                            'age_groups': [
                                row.get('age_less_6_months', 0),
                                row.get('age_6_to_12_months', 0),
                                row.get('age_1_to_2_years', 0),
                                row.get('age_more_2_years', 0)
                            ],
                            'males': row.get('males_count', 0),
                            'females': row.get('females_count', 0)
                        }
                
                # Load poultry inventory
                poultry_inventory = pd.read_sql(
                    text("SELECT * FROM poultry_inventory WHERE holder_id = :holder_id"),
                    conn,
                    params={"holder_id": self.holder_id}
                )
                
                if not poultry_inventory.empty:
                    for _, row in poultry_inventory.iterrows():
                        poultry_type = row['poultry_type']
                        st.session_state.poultry_data[poultry_type] = {
                            'cycles': row.get('cycles_count', 1),
                            'males': row.get('males_count', 0),
                            'females': row.get('females_count', 0)
                        }
                
                # Load disposal data
                disposal_records = pd.read_sql(
                    text("SELECT * FROM animal_disposal WHERE holder_id = :holder_id"),
                    conn,
                    params={"holder_id": self.holder_id}
                )
                
                if not disposal_records.empty:
                    for _, row in disposal_records.iterrows():
                        animal_type = row['animal_type']
                        st.session_state.disposal_data[animal_type] = {
                            'disposal_code': row.get('disposal_method_code', 1),
                            'males': row.get('males_disposed', 0),
                            'females': row.get('females_disposed', 0),
                            'avg_weight': float(row.get('avg_dressed_weight', 0)),
                            'avg_price': float(row.get('avg_price_per_unit', 0))
                        }
                
                # Load additional information
                additional_info = conn.execute(
                    text("SELECT * FROM livestock_additional_info WHERE holder_id = :holder_id"),
                    {"holder_id": self.holder_id}
                ).mappings().first()
                
                if additional_info:
                    st.session_state.additional_info = {
                        "production_system": additional_info.get('production_system', ''),
                        "management_method": additional_info.get('management_method', ''),
                        "dead_animal_disposal": additional_info.get('dead_animal_disposal', ''),
                        "dead_animal_disposal_other": additional_info.get('dead_animal_disposal_other', ''),
                        "vet_services_used": additional_info.get('vet_services_used', None),
                        "vet_service_type": additional_info.get('vet_service_type', '')
                    }
                
                st.session_state.livestock_data_loaded = True
                logger.info(f"Loaded livestock data for holder {self.holder_id}")
                return True
                
        except Exception as e:
            logger.error(f"Error loading livestock data: {str(e)}")
            return False

    def save_data_to_database(self):
        """Save livestock data to database"""
        if not engine or not self.holder_id:
            logger.warning("Cannot save data: No database connection or holder ID")
            return False
            
        try:
            with engine.begin() as conn:
                # Save livestock ownership
                conn.execute(
                    text("""
                        INSERT INTO livestock_ownership (holder_id, owns_livestock, created_at, updated_at)
                        VALUES (:holder_id, :owns_livestock, NOW(), NOW())
                        ON CONFLICT (holder_id) 
                        DO UPDATE SET owns_livestock = EXCLUDED.owns_livestock, updated_at = NOW()
                    """),
                    {
                        "holder_id": self.holder_id,
                        "owns_livestock": st.session_state.livestock_own_animals == "Yes"
                    }
                )
                
                # Clear existing inventory data
                conn.execute(
                    text("DELETE FROM livestock_inventory WHERE holder_id = :holder_id"),
                    {"holder_id": self.holder_id}
                )
                conn.execute(
                    text("DELETE FROM poultry_inventory WHERE holder_id = :holder_id"),
                    {"holder_id": self.holder_id}
                )
                
                # Save livestock inventory
                for animal_type, data in st.session_state.livestock_data.items():
                    conn.execute(
                        text("""
                            INSERT INTO livestock_inventory 
                            (holder_id, animal_type, medicines_used, age_less_6_months, 
                             age_6_to_12_months, age_1_to_2_years, age_more_2_years,
                             males_count, females_count, created_at)
                            VALUES (:holder_id, :animal_type, :medicines, :age1, :age2, :age3, :age4,
                                   :males, :females, NOW())
                        """),
                        {
                            "holder_id": self.holder_id,
                            "animal_type": animal_type,
                            "medicines": data.get('medicines', ''),
                            "age1": data.get('age_groups', [0, 0, 0, 0])[0],
                            "age2": data.get('age_groups', [0, 0, 0, 0])[1],
                            "age3": data.get('age_groups', [0, 0, 0, 0])[2],
                            "age4": data.get('age_groups', [0, 0, 0, 0])[3],
                            "males": data.get('males', 0),
                            "females": data.get('females', 0)
                        }
                    )
                
                # Save poultry inventory
                for poultry_type, data in st.session_state.poultry_data.items():
                    conn.execute(
                        text("""
                            INSERT INTO poultry_inventory 
                            (holder_id, poultry_type, cycles_count, males_count, females_count, created_at)
                            VALUES (:holder_id, :poultry_type, :cycles, :males, :females, NOW())
                        """),
                        {
                            "holder_id": self.holder_id,
                            "poultry_type": poultry_type,
                            "cycles": data.get('cycles', 1),
                            "males": data.get('males', 0),
                            "females": data.get('females', 0)
                        }
                    )
                
                # Save disposal data
                conn.execute(
                    text("DELETE FROM animal_disposal WHERE holder_id = :holder_id"),
                    {"holder_id": self.holder_id}
                )
                
                for animal_type, data in st.session_state.disposal_data.items():
                    conn.execute(
                        text("""
                            INSERT INTO animal_disposal 
                            (holder_id, animal_type, disposal_method_code, males_disposed, 
                             females_disposed, avg_dressed_weight, avg_price_per_unit, created_at)
                            VALUES (:holder_id, :animal_type, :method_code, :males, :females, 
                                   :avg_weight, :avg_price, NOW())
                        """),
                        {
                            "holder_id": self.holder_id,
                            "animal_type": animal_type,
                            "method_code": data.get('disposal_code', 1),
                            "males": data.get('males', 0),
                            "females": data.get('females', 0),
                            "avg_weight": data.get('avg_weight', 0.0),
                            "avg_price": data.get('avg_price', 0.0)
                        }
                    )
                
                # Save additional information
                conn.execute(
                    text("""
                        INSERT INTO livestock_additional_info 
                        (holder_id, production_system, management_method, dead_animal_disposal,
                         dead_animal_disposal_other, vet_services_used, vet_service_type, created_at, updated_at)
                        VALUES (:holder_id, :prod_system, :mgmt_method, :disposal_method,
                               :disposal_other, :vet_used, :vet_type, NOW(), NOW())
                        ON CONFLICT (holder_id) 
                        DO UPDATE SET 
                            production_system = EXCLUDED.production_system,
                            management_method = EXCLUDED.management_method,
                            dead_animal_disposal = EXCLUDED.dead_animal_disposal,
                            dead_animal_disposal_other = EXCLUDED.dead_animal_disposal_other,
                            vet_services_used = EXCLUDED.vet_services_used,
                            vet_service_type = EXCLUDED.vet_service_type,
                            updated_at = NOW()
                    """),
                    {
                        "holder_id": self.holder_id,
                        "prod_system": st.session_state.additional_info.get('production_system', ''),
                        "mgmt_method": st.session_state.additional_info.get('management_method', ''),
                        "disposal_method": st.session_state.additional_info.get('dead_animal_disposal', ''),
                        "disposal_other": st.session_state.additional_info.get('dead_animal_disposal_other', ''),
                        "vet_used": st.session_state.additional_info.get('vet_services_used') == "Yes",
                        "vet_type": st.session_state.additional_info.get('vet_service_type', '')
                    }
                )
                
                logger.info(f"Saved livestock data for holder {self.holder_id}")
                return True
                
        except Exception as e:
            logger.error(f"Error saving livestock data: {str(e)}")
            st.error(f"Failed to save livestock data: {str(e)}")
            return False

    def render_ownership_question(self):
        """Render the initial livestock ownership question"""
        st.markdown("### 🐄 Livestock & Poultry Management")
        
        st.radio(
            "**Did the holding own/raise any livestock or poultry from August 1, 2024 to July 31, 2025?**",
            ["Yes", "No"],
            key="livestock_own_animals",
            horizontal=True
        )

    def render_livestock_inventory(self):
        """Render livestock inventory section"""
        st.subheader("📊 Livestock Inventory")
        
        for animal in self.LIVESTOCK_TYPES:
            st.markdown(f"**{animal}**")
            
            # Medicines used
            meds_key = f"meds_{animal}"
            medicines = st.text_input(
                f"Medicines Used for {animal} (indicate type or 'None')", 
                value=st.session_state.livestock_data.get(animal, {}).get('medicines', ''),
                key=meds_key,
                max_chars=50
            )
            
            # Age groups
            st.markdown("**Age Distribution**")
            col1, col2, col3, col4 = st.columns(4)
            age_values = []
            
            for i, age_group in enumerate(self.AGE_GROUPS):
                with [col1, col2, col3, col4][i]:
                    age_key = f"age_{animal}_{i}"
                    default_value = st.session_state.livestock_data.get(animal, {}).get('age_groups', [0, 0, 0, 0])[i]
                    age_val = st.number_input(
                        age_group,
                        min_value=0,
                        max_value=10000,
                        value=default_value,
                        step=1,
                        key=age_key
                    )
                    age_values.append(age_val)
            
            # Gender distribution
            col5, col6 = st.columns(2)
            with col5:
                males_key = f"males_{animal}"
                default_males = st.session_state.livestock_data.get(animal, {}).get('males', 0)
                males = st.number_input(
                    f"# of Males",
                    min_value=0,
                    max_value=10000,
                    value=default_males,
                    step=1,
                    key=males_key
                )
            
            with col6:
                females_key = f"females_{animal}"
                default_females = st.session_state.livestock_data.get(animal, {}).get('females', 0)
                females = st.number_input(
                    f"# of Females",
                    min_value=0,
                    max_value=10000,
                    value=default_females,
                    step=1,
                    key=females_key
                )
            
            # Calculate and display total
            total = sum(age_values)
            st.markdown(f"**Total {animal}: {total}**")
            
            # Store data in session state
            st.session_state.livestock_data[animal] = {
                'medicines': medicines,
                'age_groups': age_values,
                'males': males,
                'females': females,
                'total': total
            }
            
            st.divider()

    def render_poultry_inventory(self):
        """Render poultry inventory section"""
        st.subheader("🐔 Poultry Inventory")
        
        # Poultry medicines (common for all poultry types)
        poultry_meds_key = "poultry_medicines"
        poultry_medicines = st.text_input(
            "Medicines Used for Poultry (indicate type or 'None')",
            value=st.session_state.livestock_data.get('Poultry', {}).get('medicines', ''),
            key=poultry_meds_key,
            max_chars=50
        )
        
        # Store poultry medicines
        st.session_state.livestock_data['Poultry'] = {
            'medicines': poultry_medicines
        }
        
        st.markdown("**Poultry Details**")
        
        for poultry in self.POULTRY_TYPES:
            st.markdown(f"**{poultry}**")
            
            col1, col2, col3 = st.columns(3)
            
            with col1:
                cycles_key = f"cycles_{poultry}"
                default_cycles = st.session_state.poultry_data.get(poultry, {}).get('cycles', 1)
                cycles = st.number_input(
                    "# of Cycles",
                    min_value=1,
                    max_value=100,
                    value=default_cycles,
                    step=1,
                    key=cycles_key
                )
            
            with col2:
                males_key = f"poultry_males_{poultry}"
                default_males = st.session_state.poultry_data.get(poultry, {}).get('males', 0)
                males = st.number_input(
                    "# of Males",
                    min_value=0,
                    max_value=10000,
                    value=default_males,
                    step=1,
                    key=males_key
                )
            
            with col3:
                females_key = f"poultry_females_{poultry}"
                default_females = st.session_state.poultry_data.get(poultry, {}).get('females', 0)
                females = st.number_input(
                    "# of Females", 
                    min_value=0,
                    max_value=10000,
                    value=default_females,
                    step=1,
                    key=females_key
                )
            
            total = males + females
            st.markdown(f"**Total {poultry}: {total}**")
            
            # Store poultry data
            st.session_state.poultry_data[poultry] = {
                'cycles': cycles,
                'males': males,
                'females': females,
                'total': total
            }
            
            st.divider()

    def render_animal_disposal(self):
        """Render animal disposal section"""
        st.subheader("🗑️ Animal Disposal Records")
        
        st.radio(
            "**Have you removed any animal from your herd?**",
            ["Yes", "No"],
            key="animals_removed",
            horizontal=True
        )
        
        if st.session_state.get("animals_removed") == "Yes":
            st.markdown("**Disposal Details by Animal Type**")
            
            for animal in self.LIVESTOCK_TYPES:
                st.markdown(f"**{animal}**")
                
                col1, col2, col3, col4, col5, col6 = st.columns(6)
                
                with col1:
                    disposal_key = f"disposal_{animal}"
                    default_code = st.session_state.disposal_data.get(animal, {}).get('disposal_code', 1)
                    disposal_code = st.selectbox(
                        "Disposal Method",
                        options=list(self.DISPOSAL_CODES.keys()),
                        index=default_code - 1,
                        format_func=lambda x: f"{x} - {self.DISPOSAL_CODES[x]}",
                        key=disposal_key
                    )
                
                with col2:
                    males_key = f"disposal_males_{animal}"
                    default_males = st.session_state.disposal_data.get(animal, {}).get('males', 0)
                    disposal_males = st.number_input(
                        "# Males",
                        min_value=0,
                        max_value=10000,
                        value=default_males,
                        step=1,
                        key=males_key
                    )
                
                with col3:
                    females_key = f"disposal_females_{animal}"
                    default_females = st.session_state.disposal_data.get(animal, {}).get('females', 0)
                    disposal_females = st.number_input(
                        "# Females",
                        min_value=0,
                        max_value=10000,
                        value=default_females,
                        step=1,
                        key=females_key
                    )
                
                with col4:
                    weight_key = f"weight_{animal}"
                    default_weight = st.session_state.disposal_data.get(animal, {}).get('avg_weight', 0.0)
                    avg_weight = st.number_input(
                        "Avg. Weight (kg)",
                        min_value=0.0,
                        value=float(default_weight),
                        step=0.1,
                        format="%.1f",
                        key=weight_key
                    )
                
                with col5:
                    price_key = f"price_{animal}"
                    default_price = st.session_state.disposal_data.get(animal, {}).get('avg_price', 0.0)
                    avg_price = st.number_input(
                        "Avg. Price ($/kg)",
                        min_value=0.0,
                        value=float(default_price),
                        step=0.1,
                        format="%.2f",
                        key=price_key
                    )
                
                with col6:
                    total_value = avg_weight * avg_price
                    st.metric("Total Value", f"${total_value:,.2f}")
                
                # Store disposal data
                st.session_state.disposal_data[animal] = {
                    'disposal_code': disposal_code,
                    'males': disposal_males,
                    'females': disposal_females,
                    'avg_weight': avg_weight,
                    'avg_price': avg_price,
                    'total_value': total_value
                }
                
                st.divider()

    def render_additional_information(self):
        """Render additional information section"""
        st.subheader("📋 Additional Information")
        
        # Production system
        st.radio(
            "**Livestock production system**",
            self.PRODUCTION_SYSTEMS,
            key="production_system",
            horizontal=True
        )
        
        # Management method
        st.radio(
            "**Livestock management methods used**",
            self.MANAGEMENT_METHODS,
            key="management_method", 
            horizontal=True
        )
        
        # Dead animal disposal
        disposal_method = st.radio(
            "**How did you dispose of animals that died on the holding?**",
            self.DEAD_ANIMAL_DISPOSAL,
            key="dead_animal_disposal",
            horizontal=True
        )
        
        if disposal_method == "Other":
            st.text_input(
                "Please specify other disposal method",
                value=st.session_state.additional_info.get('dead_animal_disposal_other', ''),
                key="dead_animal_disposal_other",
                max_chars=100
            )
        
        # Veterinarian services
        vet_service = st.radio(
            "**Did you use any veterinarian services?**",
            ["Yes", "No"],
            key="vet_services_used",
            horizontal=True
        )
        
        if vet_service == "Yes":
            st.text_input(
                "Service Type",
                value=st.session_state.additional_info.get('vet_service_type', ''),
                key="vet_service_type",
                max_chars=100
            )

    def calculate_totals(self) -> Dict:
        """Calculate comprehensive livestock totals"""
        totals = {
            'total_livestock': 0,
            'total_poultry': 0,
            'total_animals': 0,
            'total_disposal_value': 0.0
        }
        
        # Livestock totals
        for animal_data in st.session_state.livestock_data.values():
            if 'total' in animal_data:
                totals['total_livestock'] += animal_data['total']
        
        # Poultry totals  
        for poultry_data in st.session_state.poultry_data.values():
            if 'total' in poultry_data:
                totals['total_poultry'] += poultry_data['total']
        
        # Total animals
        totals['total_animals'] = totals['total_livestock'] + totals['total_poultry']
        
        # Disposal value total
        for disposal_data in st.session_state.disposal_data.values():
            if 'total_value' in disposal_data:
                totals['total_disposal_value'] += disposal_data['total_value']
        
        return totals

    def validate_data(self) -> Tuple[List[str], List[str]]:
        """Validate livestock data"""
        errors = []
        warnings = []
        
        if st.session_state.livestock_own_animals == "Yes":
            # Check if at least one animal type has data
            has_livestock_data = any(
                data.get('total', 0) > 0 
                for data in st.session_state.livestock_data.values()
            )
            has_poultry_data = any(
                data.get('total', 0) > 0
                for data in st.session_state.poultry_data.values()  
            )
            
            if not has_livestock_data and not has_poultry_data:
                warnings.append("No livestock or poultry data entered despite selecting 'Yes' for ownership")
            
            # Validate disposal data if animals were removed
            if st.session_state.get("animals_removed") == "Yes":
                has_disposal_data = any(
                    data.get('males', 0) > 0 or data.get('females', 0) > 0
                    for data in st.session_state.disposal_data.values()
                )
                
                if not has_disposal_data:
                    warnings.append("Animal removal indicated but no disposal records entered")
        
        return errors, warnings

    def render_summary(self):
        """Render data summary"""
        if st.session_state.livestock_own_animals == "No":
            return
        
        st.subheader("📈 Livestock Summary")
        
        totals = self.calculate_totals()
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("Total Livestock", totals['total_livestock'])
        
        with col2:
            st.metric("Total Poultry", totals['total_poultry'])
        
        with col3:
            st.metric("Total Animals", totals['total_animals'])
        
        with col4:
            st.metric("Total Disposal Value", f"${totals['total_disposal_value']:,.2f}")

    def render_integration_controls(self):
        """Render integration controls"""
        if not self.integrated_mode:
            return False
            
        st.markdown("---")
        st.subheader("🔗 Survey Integration")
        
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("💾 Save to Survey", type="primary", use_container_width=True):
                if self.save_data_to_database():
                    st.success("Livestock data saved successfully!")
                    return True
        
        with col2:
            if st.button("🔄 Reload from Database", use_container_width=True):
                self.load_data_from_database()
                st.rerun()
        
        return False

    def run(self):
        """Main execution method"""
        st.header("🐄 Livestock & Poultry Management")
        
        # Load data if in integrated mode
        if self.integrated_mode and not st.session_state.livestock_data_loaded:
            self.load_data_from_database()
        
        # Render ownership question
        self.render_ownership_question()
        
        if st.session_state.livestock_own_animals == "Yes":
            # Render all sections for livestock owners
            self.render_livestock_inventory()
            self.render_poultry_inventory() 
            self.render_animal_disposal()
            self.render_additional_information()
            self.render_summary()
            
            # Validate data
            errors, warnings = self.validate_data()
            if warnings:
                st.warning("Validation warnings: " + "; ".join(warnings))
        
        else:
            st.info("🏁 No livestock/poultry recorded — you may proceed to the next section.")
        
        # Integration controls
        if self.integrated_mode:
            section_completed = self.render_integration_controls()
            return section_completed
        
        return st.session_state.livestock_own_animals is not None

def main(holder_id=None, integrated_mode=False):
    """
    Main livestock/poultry management function
    
    Args:
        holder_id: Optional holder ID for database integration
        integrated_mode: Whether running as part of larger application
    
    Returns:
        bool: Whether the section is considered complete
    """
    try:
        manager = LivestockPoultryManager(holder_id, integrated_mode)
        return manager.run()
        
    except Exception as e:
        logger.error(f"Error in livestock/poultry system: {str(e)}")
        st.error(f"System error: {str(e)}")
        return False

# Standalone execution
if __name__ == "__main__":
    main()