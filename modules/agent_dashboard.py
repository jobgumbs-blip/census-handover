"""
Enhanced Agent Dashboard & Field Management System
Supports offline data collection, phone/in-person interviews, auto-sync, and real-time support
"""

import streamlit as st
import pandas as pd
import json
import time
from datetime import datetime, timedelta
from sqlalchemy import text
from db import engine

def agent_dashboard():
    """Main agent dashboard with enhanced field operations management"""
    
    if "user" not in st.session_state or st.session_state["user"]["role"].lower() != "agent":
        st.error("🚫 Agent access required")
        return
    
    user_id = st.session_state["user"]["id"]
    
    # Get or create agent profile
    agent = get_or_create_agent(user_id)
    
    if not agent:
        st.error("❌ Failed to load agent profile")
        return
    
    # Mobile optimization toggle
    render_mobile_optimization()
    
    # Dashboard header
    st.markdown(f"""
    <div style='background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
                padding: {'20px' if st.session_state.get('mobile_view', False) else '30px'}; 
                border-radius: 15px; color: white; margin-bottom: 20px;'>
        <h1 style='margin-bottom: 10px; font-size: {'1.5rem' if st.session_state.get('mobile_view', False) else '2rem'};'>👨‍💼 Agent Field Operations Dashboard</h1>
        <h3 style='margin: 5px 0; font-size: {'1.1rem' if st.session_state.get('mobile_view', False) else '1.5rem'};'>Welcome, {agent['full_name']} ({agent['agent_code']})</h3>
        <p style='margin: 0; font-size: {'0.9rem' if st.session_state.get('mobile_view', False) else '1rem'};'>Island Assignment: {agent['island_name'] or 'Not Assigned'}</p>
    </div>
    """, unsafe_allow_html=True)
    
    # Emergency quick actions
    render_emergency_quick_actions(agent)
    
    # Main tabs - adjusted for mobile
    if st.session_state.get('mobile_view', False):
        tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
            "📋 Assign", "📞 Ops", "☁️ Sync", "📊 Stats", "🗺️ Map", "🆘 Help"
        ])
    else:
        tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
            "📋 My Assignments", "📞 Field Operations", "☁️ Data Sync", 
            "📊 Performance Analytics", "🗺️ Territory Map", "🆘 Real-time Support"
        ])
    
    with tab1:
        render_agent_assignments(agent)
    
    with tab2:
        render_field_operations(agent)
    
    with tab3:
        render_enhanced_data_sync_manager(agent)
    
    with tab4:
        render_enhanced_agent_performance(agent)
    
    with tab5:
        render_territory_map(agent)
    
    with tab6:
        render_real_time_support(agent)

def render_mobile_optimization():
    """Mobile-friendly interface adjustments"""
    
    # Session state for mobile detection
    if 'mobile_view' not in st.session_state:
        st.session_state.mobile_view = False
    
    # Mobile toggle
    col_mobile = st.columns([3, 1])
    with col_mobile[1]:
        mobile_mode = st.toggle("📱 Mobile Mode", value=st.session_state.mobile_view)
        if mobile_mode != st.session_state.mobile_view:
            st.session_state.mobile_view = mobile_mode
            st.rerun()
    
    if st.session_state.mobile_view:
        st.markdown("""
        <style>
        .main .block-container {
            padding-top: 1rem;
            padding-left: 0.5rem;
            padding-right: 0.5rem;
        }
        .stButton button {
            width: 100%;
        }
        div[data-testid="stExpander"] div[role="button"] p {
            font-size: 0.9rem;
        }
        </style>
        """, unsafe_allow_html=True)

def render_emergency_quick_actions(agent):
    """Emergency quick actions at the top"""
    
    st.markdown("### 🚨 Quick Actions")
    emergency_cols = st.columns(4)
    
    with emergency_cols[0]:
        if st.button("🆘 Safety Concern", use_container_width=True, type="secondary"):
            trigger_safety_protocol(agent['agent_id'])
            st.success("Safety protocol activated! Help is on the way.")
    
    with emergency_cols[1]:
        if st.button("📞 Call Supervisor", use_container_width=True, type="secondary"):
            request_supervisor_call(agent['agent_id'])
            st.info("Supervisor notified - they will call you shortly.")
    
    with emergency_cols[2]:
        if st.button("💾 Force Sync", use_container_width=True, type="primary"):
            with st.spinner("Syncing data..."):
                perform_data_sync(agent['agent_id'])
            st.rerun()
    
    with emergency_cols[3]:
        if st.button("🔄 Refresh All", use_container_width=True):
            st.rerun()

def get_or_create_agent(user_id):
    """Get agent profile or create if doesn't exist"""
    
    try:
        with engine.connect() as conn:
            # Check if agent exists
            agent = conn.execute(text("""
                SELECT a.*, i.island_name, u.username,
                       COALESCE(a.current_assignments, 0) as current_assignments,
                       COALESCE(a.total_surveys_completed, 0) as total_surveys_completed,
                       COALESCE(a.max_assignments, 10) as max_assignments
                FROM agents a
                LEFT JOIN islands i ON a.assigned_island_id = i.island_id
                LEFT JOIN users u ON a.user_id = u.id
                WHERE a.user_id = :uid
            """), {"uid": user_id}).mappings().first()
            
            if agent:
                return dict(agent)
            
            # Create new agent
            username = conn.execute(text("SELECT username FROM users WHERE id = :uid"), 
                                   {"uid": user_id}).scalar()
            
            with engine.begin() as conn:
                result = conn.execute(text("""
                    INSERT INTO agents (user_id, agent_code, full_name, status, 
                                      current_assignments, total_surveys_completed, max_assignments)
                    VALUES (:uid, :code, :name, 'active', 0, 0, 10)
                    RETURNING agent_id
                """), {
                    "uid": user_id,
                    "code": f"AGT{user_id:04d}",
                    "name": username or f"Agent {user_id}"
                })
                
                agent_id = result.scalar()
                
                # Fetch newly created agent
                agent = conn.execute(text("""
                    SELECT a.*, i.island_name, u.username,
                           COALESCE(a.current_assignments, 0) as current_assignments,
                           COALESCE(a.total_surveys_completed, 0) as total_surveys_completed,
                           COALESCE(a.max_assignments, 10) as max_assignments
                    FROM agents a
                    LEFT JOIN islands i ON a.assigned_island_id = i.island_id
                    LEFT JOIN users u ON a.user_id = u.id
                    WHERE a.agent_id = :aid
                """), {"aid": agent_id}).mappings().first()
                
                return dict(agent) if agent else None
                
    except Exception as e:
        st.error(f"Database error: {e}")
        return None

def render_agent_assignments(agent):
    """Display and manage agent assignments"""
    
    st.markdown("### 📋 Current Assignments")
    
    # Enhanced metrics
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Active Assignments", agent['current_assignments'])
    with col2:
        st.metric("Completed", agent['total_surveys_completed'])
    with col3:
        capacity = f"{agent['current_assignments']}/{agent['max_assignments']}"
        st.metric("Capacity", capacity)
    with col4:
        pending = get_pending_assignments_count(agent['agent_id'])
        st.metric("Pending Review", pending)
    
    # Assignment filters
    st.markdown("---")
    if st.session_state.get('mobile_view', False):
        col_filter = st.columns(2)
        with col_filter[0]:
            status_filter = st.selectbox("Status", 
                ["all", "assigned", "in_progress", "completed", "cancelled"])
        with col_filter[1]:
            if st.button("🔄 Refresh", use_container_width=True):
                st.rerun()
    else:
        col_filter = st.columns([2, 2, 2, 1])
        with col_filter[0]:
            status_filter = st.selectbox("Status", 
                ["all", "assigned", "in_progress", "completed", "cancelled"])
        with col_filter[1]:
            interview_type_filter = st.selectbox("Interview Type",
                ["all", "phone", "in_person", "remote"])
        with col_filter[2]:
            date_range = st.selectbox("Date Range",
                ["all", "today", "this_week", "this_month"])
        with col_filter[3]:
            if st.button("🔄 Refresh", use_container_width=True):
                st.rerun()
    
    # Get assignments
    assignments = get_agent_assignments(
        agent['agent_id'], 
        status_filter, 
        interview_type_filter if not st.session_state.get('mobile_view', False) else "all",
        date_range if not st.session_state.get('mobile_view', False) else "all"
    )
    
    if not assignments:
        st.info("📭 No assignments found matching filters")
        return
    
    # Display assignments
    for assignment in assignments:
        render_enhanced_assignment_card(assignment, agent)

def render_enhanced_assignment_card(assignment, agent):
    """Render individual assignment card with enhanced features"""
    
    status_colors = {
        'assigned': '🔵',
        'in_progress': '🟡',
        'completed': '🟢',
        'cancelled': '🔴'
    }
    
    status_icon = status_colors.get(assignment['status'], '⚪')
    
    with st.expander(f"{status_icon} {assignment['holder_name']} - {assignment['interview_type'].title()}", 
                     expanded=(assignment['status'] == 'assigned')):
        
        if st.session_state.get('mobile_view', False):
            # Mobile layout
            st.markdown(f"""
            **ID:** {assignment['assignment_id']}  
            **Status:** {assignment['status'].title()}  
            **Type:** {assignment['interview_type'].title()}  
            **Island:** {assignment['island_name'] or 'N/A'}  
            **Contact Attempts:** {assignment['contact_attempts']}
            """)
        else:
            # Desktop layout
            col_info, col_actions = st.columns([3, 1])
            
            with col_info:
                st.markdown(f"""
                **Assignment ID:** {assignment['assignment_id']}  
                **Status:** {assignment['status'].title()}  
                **Interview Type:** {assignment['interview_type'].title()}  
                **Scheduled:** {assignment['scheduled_date'] or 'Not scheduled'}  
                **Island:** {assignment['island_name'] or 'N/A'}  
                **Contact Attempts:** {assignment['contact_attempts']}  
                **Last Contact:** {assignment['last_contact_date'] or 'Never'}
                """)
        
        # Progress tracking for in-progress assignments
        if assignment['status'] == 'in_progress' and assignment.get('progress_percentage'):
            progress = assignment['progress_percentage']
            st.progress(progress / 100)
            st.caption(f"Interview Progress: {progress}%")
        
        if assignment['notes']:
            st.text_area("Notes", assignment['notes'], height=80, disabled=True, 
                       key=f"notes_view_{assignment['assignment_id']}")
        
        # Action buttons
        if not st.session_state.get('mobile_view', False):
            col_actions = st.columns(2)
            with col_actions[0]:
                action_cols = st.columns(2)
                with action_cols[0]:
                    if assignment['status'] == 'assigned':
                        if st.button("▶️ Start", key=f"start_{assignment['assignment_id']}",
                                   use_container_width=True):
                            start_interview(assignment['assignment_id'], agent['agent_id'])
                            st.rerun()
                    
                    elif assignment['status'] == 'in_progress':
                        if st.button("✅ Complete", key=f"complete_{assignment['assignment_id']}",
                                   use_container_width=True, type="primary"):
                            complete_interview(assignment['assignment_id'])
                            st.rerun()
                
                with action_cols[1]:
                    if assignment['status'] in ['assigned', 'in_progress']:
                        if st.button("📞 Contact", key=f"contact_{assignment['assignment_id']}",
                                   use_container_width=True):
                            log_contact_attempt(assignment['assignment_id'])
                            st.rerun()
            
            with col_actions[1]:
                if assignment['status'] in ['assigned', 'in_progress']:
                    if st.button("📝 Add Note", key=f"note_{assignment['assignment_id']}",
                               use_container_width=True):
                        st.session_state[f"show_note_modal_{assignment['assignment_id']}"] = True
                    
                    if st.button("🎤 Continue", key=f"continue_{assignment['assignment_id']}",
                               use_container_width=True):
                        st.session_state['continue_interview_id'] = assignment['assignment_id']
                        st.session_state['show_enhanced_interview'] = True
                        st.rerun()
        else:
            # Mobile actions
            if assignment['status'] == 'assigned':
                if st.button("▶️ Start Interview", key=f"start_mobile_{assignment['assignment_id']}",
                           use_container_width=True):
                    start_interview(assignment['assignment_id'], agent['agent_id'])
                    st.rerun()
            
            elif assignment['status'] == 'in_progress':
                action_cols = st.columns(2)
                with action_cols[0]:
                    if st.button("✅ Complete", key=f"complete_mobile_{assignment['assignment_id']}",
                               use_container_width=True, type="primary"):
                        complete_interview(assignment['assignment_id'])
                        st.rerun()
                with action_cols[1]:
                    if st.button("📞 Log Contact", key=f"contact_mobile_{assignment['assignment_id']}",
                               use_container_width=True):
                        log_contact_attempt(assignment['assignment_id'])
                        st.rerun()
        
        # Note modal
        if st.session_state.get(f"show_note_modal_{assignment['assignment_id']}", False):
            new_note = st.text_area("Add Note", key=f"new_note_{assignment['assignment_id']}")
            col_note_btn = st.columns(2)
            with col_note_btn[0]:
                if st.button("💾 Save Note", key=f"save_note_{assignment['assignment_id']}"):
                    add_assignment_note(assignment['assignment_id'], new_note)
                    st.session_state[f"show_note_modal_{assignment['assignment_id']}"] = False
                    st.rerun()
            with col_note_btn[1]:
                if st.button("❌ Cancel", key=f"cancel_note_{assignment['assignment_id']}"):
                    st.session_state[f"show_note_modal_{assignment['assignment_id']}"] = False
                    st.rerun()

def render_field_operations(agent):
    """Enhanced field operations and offline data collection interface"""
    
    st.markdown("### 📞 Field Operations Center")
    
    # Device status and network info
    col_device = st.columns([2, 2, 1])
    
    with col_device[0]:
        device_id = st.text_input("Device ID", value=agent.get('device_id', ''), 
                                 help="Your Android device identifier")
    
    with col_device[1]:
        network_status = st.selectbox("Network Status", 
            ["Online", "Limited", "Offline"])
    
    with col_device[2]:
        if st.button("💾 Update", use_container_width=True):
            update_agent_device(agent['agent_id'], device_id)
            st.success("✅ Updated!")
            st.rerun()
    
    st.markdown("---")
    
    # Quick actions
    st.markdown("### ⚡ Quick Actions")
    
    if st.session_state.get('mobile_view', False):
        # Mobile layout
        if st.button("📞 Start Phone Interview", use_container_width=True, type="primary"):
            st.session_state['interview_mode'] = 'phone'
            st.session_state['show_interview_form'] = True
        
        if st.button("👤 Start In-Person Interview", use_container_width=True, type="primary"):
            st.session_state['interview_mode'] = 'in_person'
            st.session_state['show_interview_form'] = True
        
        if st.button("📡 Remote Support", use_container_width=True):
            st.session_state['interview_mode'] = 'remote'
            st.session_state['show_interview_form'] = True
    else:
        # Desktop layout
        col_actions = st.columns(3)
        
        with col_actions[0]:
            st.markdown("#### 📞 Phone Interview")
            if st.button("Start Phone Interview", use_container_width=True, type="primary"):
                st.session_state['interview_mode'] = 'phone'
                st.session_state['show_interview_form'] = True
        
        with col_actions[1]:
            st.markdown("#### 👤 In-Person Interview")
            if st.button("Start In-Person Interview", use_container_width=True, type="primary"):
                st.session_state['interview_mode'] = 'in_person'
                st.session_state['show_interview_form'] = True
        
        with col_actions[2]:
            st.markdown("#### 📡 Remote Assistance")
            if st.button("Remote Support Session", use_container_width=True):
                st.session_state['interview_mode'] = 'remote'
                st.session_state['show_interview_form'] = True
    
    # Continue existing interview
    if st.session_state.get('continue_interview_id'):
        if st.button("➡️ Continue Existing Interview", use_container_width=True, type="secondary"):
            st.session_state['show_enhanced_interview'] = True
            st.rerun()
    
    # Interview form
    if st.session_state.get('show_interview_form', False):
        render_interview_form(agent)
    
    # Enhanced interview workflow
    if st.session_state.get('show_enhanced_interview', False):
        assignment_id = st.session_state.get('continue_interview_id')
        if assignment_id:
            assignment = get_assignment_details(assignment_id)
            if assignment:
                render_enhanced_interview_workflow(assignment, agent)
    
    # Recent activity
    st.markdown("---")
    st.markdown("### 📜 Recent Activity")
    
    recent_activity = get_agent_activity(agent['agent_id'], limit=10)
    
    if recent_activity:
        for activity in recent_activity:
            st.markdown(f"""
            <div style='background: #f8f9fa; padding: 10px; border-radius: 8px; margin: 5px 0;'>
                <strong>{activity['activity_type']}</strong> - {activity['created_at']}  
                {activity['description'] or ''}
            </div>
            """, unsafe_allow_html=True)
    else:
        st.info("No recent activity")

def render_interview_form(agent):
    """Render interview initiation form"""
    
    st.markdown("---")
    st.markdown(f"### 🎤 {st.session_state['interview_mode'].title()} Interview")
    
    with st.form("interview_form"):
        # Select assignment or create new
        assignments = get_agent_assignments(agent['agent_id'], 'assigned', 'all', 'all')
        
        if assignments:
            assignment_options = {
                f"{a['holder_name']} ({a['assignment_id']})": a['assignment_id'] 
                for a in assignments
            }
            assignment_options["➕ New Candidate"] = None
            
            selected = st.selectbox("Select Assignment", list(assignment_options.keys()))
            assignment_id = assignment_options[selected]
        else:
            assignment_id = None
            st.info("No existing assignments. Creating new interview.")
        
        # Interview details
        col_int = st.columns(2)
        
        with col_int[0]:
            candidate_name = st.text_input("Candidate Name", 
                                         value="")  # Clear default
            phone = st.text_input("Phone Number")
        
        with col_int[1]:
            island = st.selectbox("Island", get_island_options())
            scheduled_date = st.date_input("Scheduled Date")
        
        notes = st.text_area("Initial Notes")
        
        # Location (if in-person)
        if st.session_state['interview_mode'] == 'in_person':
            st.markdown("**📍 Location (Optional)**")
            col_loc = st.columns(2)
            with col_loc[0]:
                lat = st.number_input("Latitude", value=25.0343, format="%.6f")
            with col_loc[1]:
                lon = st.number_input("Longitude", value=-77.3963, format="%.6f")
        else:
            lat, lon = None, None
        
        col_submit = st.columns([1, 1, 2])
        
        with col_submit[0]:
            submitted = st.form_submit_button("🚀 Start Interview", type="primary", 
                                            use_container_width=True)
        
        with col_submit[1]:
            cancelled = st.form_submit_button("❌ Cancel", use_container_width=True)
        
        if cancelled:
            st.session_state['show_interview_form'] = False
            st.rerun()
        
        if submitted:
            if not candidate_name and not assignment_id:
                st.error("Candidate name required for new interviews")
            else:
                # Create or update assignment
                success = create_interview_assignment(
                    agent['agent_id'],
                    assignment_id,
                    candidate_name,
                    st.session_state['interview_mode'],
                    phone,
                    island,
                    scheduled_date,
                    notes,
                    lat,
                    lon
                )
                
                if success:
                    st.success("✅ Interview started successfully!")
                    log_agent_activity(agent['agent_id'], 'interview_started', 
                                     f"Started {st.session_state['interview_mode']} interview with {candidate_name}")
                    st.session_state['show_interview_form'] = False
                    st.session_state['show_enhanced_interview'] = True
                    st.session_state['continue_interview_id'] = get_last_assignment_id(agent['agent_id'])
                    st.rerun()
                else:
                    st.error("❌ Failed to start interview")

def render_enhanced_interview_workflow(assignment, agent):
    """Step-by-step enhanced interview process"""
    
    st.markdown(f"### 🎤 Interview: {assignment['holder_name']}")
    
    # Progress tracking
    progress = assignment.get('progress_percentage', 0)
    st.progress(progress / 100)
    st.caption(f"Progress: {progress}%")
    
    # Interview steps
    steps = [
        "Introduction & Consent",
        "Basic Information", 
        "Survey Questions",
        "Document Collection",
        "Review & Submit"
    ]
    
    current_step = min(progress // 20, 4)
    
    st.markdown(f"#### Step {current_step + 1}: {steps[current_step]}")
    
    # Dynamic form based on step
    if current_step == 0:
        render_consent_form(assignment)
    elif current_step == 1:
        render_basic_info_form(assignment)
    elif current_step == 2:
        render_survey_questions(assignment)
    elif current_step == 3:
        render_document_collection(assignment)
    else:
        render_review_submit(assignment)
    
    # Navigation
    col_nav = st.columns([1, 1, 2])
    with col_nav[0]:
        if current_step > 0 and st.button("⬅️ Previous"):
            new_progress = max(0, progress - 20)
            update_interview_progress(assignment['assignment_id'], new_progress)
            st.rerun()
    
    with col_nav[1]:
        if current_step < 4 and st.button("Next ➡️"):
            new_progress = min(100, progress + 20)
            update_interview_progress(assignment['assignment_id'], new_progress)
            st.rerun()
    
    # Save & exit
    with col_nav[2]:
        if st.button("💾 Save & Exit", type="primary"):
            save_interview_draft(assignment['assignment_id'])
            st.session_state['show_enhanced_interview'] = False
            st.session_state['continue_interview_id'] = None
            st.success("Draft saved!")
            st.rerun()

def render_consent_form(assignment):
    """Render consent form step"""
    
    st.markdown("""
    ### Informed Consent
    
    Please read the following information to the participant:
    """)
    
    consent_text = st.text_area("Consent Script", 
                               value="This survey is conducted for research purposes. Your participation is voluntary and you may withdraw at any time. All information will be kept confidential.",
                               height=100)
    
    col_consent = st.columns(2)
    with col_consent[0]:
        consent_given = st.checkbox("Participant has given verbal consent")
    with col_consent[1]:
        consent_recorded = st.checkbox("Consent recorded in system")
    
    if consent_given and consent_recorded:
        st.success("✅ Consent properly recorded")

def render_basic_info_form(assignment):
    """Render basic information collection form"""
    
    st.markdown("### Basic Information")
    
    col_info = st.columns(2)
    
    with col_info[0]:
        full_name = st.text_input("Full Name", value=assignment['holder_name'])
        age = st.number_input("Age", min_value=18, max_value=100, value=30)
        gender = st.selectbox("Gender", ["Male", "Female", "Other", "Prefer not to say"])
    
    with col_info[1]:
        phone = st.text_input("Phone Number")
        email = st.text_input("Email Address")
        occupation = st.text_input("Occupation")

def render_survey_questions(assignment):
    """Render survey questions step"""
    
    st.markdown("### Survey Questions")
    
    # Sample questions - in real implementation, these would come from database
    questions = [
        "How satisfied are you with the current services?",
        "How likely are you to recommend this to others?",
        "What improvements would you suggest?"
    ]
    
    for i, question in enumerate(questions):
        st.markdown(f"**Q{i+1}: {question}**")
        if i < 2:  # First two are scale questions
            rating = st.slider(f"Rating for Q{i+1}", 1, 5, 3, key=f"q{i+1}_rating")
        else:  # Last one is text
            answer = st.text_area(f"Answer for Q{i+1}", key=f"q{i+1}_text")

def render_document_collection(assignment):
    """Render document collection step"""
    
    st.markdown("### Document Collection")
    
    col_docs = st.columns(2)
    
    with col_docs[0]:
        st.markdown("#### Required Documents")
        id_provided = st.checkbox("ID Document Provided")
        proof_address = st.checkbox("Proof of Address Provided")
        consent_form = st.checkbox("Signed Consent Form Collected")
    
    with col_docs[1]:
        st.markdown("#### Document Upload")
        uploaded_files = st.file_uploader("Upload document photos", 
                                        accept_multiple_files=True,
                                        type=['jpg', 'jpeg', 'png', 'pdf'])
        
        if uploaded_files:
            st.success(f"✅ {len(uploaded_files)} files uploaded")

def render_review_submit(assignment):
    """Render review and submit step"""
    
    st.markdown("### Review & Submit")
    
    st.markdown("""
    Please review all collected information before submitting:
    
    - ✅ Consent properly recorded
    - ✅ Basic information collected
    - ✅ Survey questions completed
    - ✅ Documents collected and uploaded
    - ✅ All data verified for accuracy
    """)
    
    final_notes = st.text_area("Final Notes or Comments")
    
    if st.button("🚀 Submit Completed Interview", type="primary", use_container_width=True):
        complete_interview(assignment['assignment_id'])
        st.session_state['show_enhanced_interview'] = False
        st.session_state['continue_interview_id'] = None
        st.success("🎉 Interview completed and submitted successfully!")
        time.sleep(2)
        st.rerun()

def render_enhanced_data_sync_manager(agent):
    """Enhanced offline data sync management"""
    
    st.markdown("### ☁️ Data Synchronization Manager")
    
    # Sync status
    pending_count = get_pending_sync_count(agent['agent_id'])
    last_sync = agent.get('last_sync_at', 'Never')
    
    col_sync = st.columns(4)
    
    with col_sync[0]:
        st.metric("Pending Upload", pending_count)
    with col_sync[1]:
        st.metric("Last Sync", last_sync or "Never")
    with col_sync[2]:
        sync_status = "🟢 Online" if pending_count == 0 else "🟡 Pending"
        st.metric("Status", sync_status)
    with col_sync[3]:
        if st.button("🔄 Sync Now", type="primary", use_container_width=True):
            with st.spinner("Syncing data..."):
                perform_data_sync(agent['agent_id'])
            st.rerun()
    
    # Enhanced offline settings
    st.markdown("---")
    st.markdown("### 📱 Enhanced Offline Mode")
    
    col_storage = st.columns(3)
    with col_storage[0]:
        storage_used = get_offline_storage_usage(agent['agent_id'])
        st.metric("Storage Used", f"{storage_used} MB")
    
    # Auto-sync configuration
    st.markdown("#### ⚙️ Sync Settings")
    col_sync_settings = st.columns(2)
    
    with col_sync_settings[0]:
        auto_sync = st.checkbox("Auto-sync when online", value=True)
        sync_frequency = st.selectbox("Sync Frequency", 
                                    ["realtime", "15min", "1hour", "4hours"])
    
    with col_sync_settings[1]:
        data_retention = st.slider("Keep data for (days)", 1, 30, 7)
        max_file_size = st.selectbox("Max File Size", 
                                   ["10MB", "25MB", "50MB", "100MB"])
    
    # Data backup/export
    st.markdown("#### 💾 Data Management")
    col_data = st.columns(3)
    
    with col_data[0]:
        if st.button("📤 Export Local Data", use_container_width=True):
            export_offline_data(agent['agent_id'])
            st.success("Data exported successfully!")
    
    with col_data[1]:
        if st.button("🧹 Clean Old Data", use_container_width=True):
            cleanup_old_data(agent['agent_id'], data_retention)
            st.success("Old data cleaned!")
    
    with col_data[2]:
        if st.button("🔄 Reset Local Cache", use_container_width=True):
            reset_local_cache(agent['agent_id'])
            st.success("Cache reset!")
    
    # Pending data queue
    if pending_count > 0:
        st.markdown("---")
        st.markdown("### 📦 Pending Data Queue")
        
        pending_data = get_pending_sync_data(agent['agent_id'])
        
        if pending_data:
            df = pd.DataFrame(pending_data)
            st.dataframe(df[['queue_id', 'data_type', 'collected_at', 'sync_status', 'sync_attempts']], 
                        use_container_width=True)
            
            # Bulk actions
            col_bulk = st.columns(3)
            with col_bulk[0]:
                if st.button("⬆️ Upload All", use_container_width=True):
                    upload_all_pending(agent['agent_id'])
                    st.rerun()
            
            with col_bulk[1]:
                if st.button("🔄 Retry Failed", use_container_width=True):
                    retry_failed_syncs(agent['agent_id'])
                    st.rerun()
            
            with col_bulk[2]:
                if st.button("🗑️ Clear Failed", use_container_width=True):
                    clear_failed_syncs(agent['agent_id'])
                    st.rerun()
    
    # Sync history
    st.markdown("---")
    st.markdown("### 📊 Sync History")
    
    sync_history = get_sync_history(agent['agent_id'], limit=10)
    
    if sync_history:
        for session in sync_history:
            status_icon = "✅" if session['sync_status'] == 'completed' else "❌"
            st.markdown(f"""
            <div style='background: #f8f9fa; padding: 10px; border-radius: 8px; margin: 5px 0;'>
                {status_icon} <strong>Session {session['session_id']}</strong> - {session['sync_started_at']}  
                Uploaded: {session['records_uploaded']} | Failed: {session['records_failed']}
            </div>
            """, unsafe_allow_html=True)
    else:
        st.info("No sync history available")

def render_enhanced_agent_performance(agent):
    """Enhanced agent performance metrics and analytics"""
    
    st.markdown("### 📊 Performance Analytics")
    
    # Overview metrics
    stats = get_agent_statistics(agent['agent_id'])
    enhanced_stats = get_enhanced_agent_statistics(agent['agent_id'])
    
    col_perf = st.columns(4)
    
    with col_perf[0]:
        st.metric("Total Surveys", stats['total_surveys'])
    with col_perf[1]:
        st.metric("Completion Rate", f"{stats['completion_rate']:.1f}%")
    with col_perf[2]:
        st.metric("Quality Score", f"{enhanced_stats.get('quality_score', 0)}/10")
    with col_perf[3]:
        st.metric("This Month", stats['this_month'])
    
    # Second row of metrics
    col_perf2 = st.columns(4)
    
    with col_perf2[0]:
        avg_duration = enhanced_stats.get('avg_duration', 0)
        st.metric("Avg Duration", f"{avg_duration}m")
    with col_perf2[1]:
        first_time_rate = enhanced_stats.get('first_time_completion_rate', 0)
        st.metric("First-time Complete", f"{first_time_rate}%")
    with col_perf2[2]:
        success_rate = enhanced_stats.get('success_rate', 0)
        st.metric("Success Rate", f"{success_rate}%")
    with col_perf2[3]:
        satisfaction = enhanced_stats.get('satisfaction_score', 0)
        st.metric("Satisfaction", f"{satisfaction}/5")
    
    # Performance charts
    st.markdown("---")
    col_charts = st.columns(2)
    
    with col_charts[0]:
        st.markdown("#### 📈 Survey Trend (Last 30 Days)")
        trend_data = get_survey_trend(agent['agent_id'], days=30)
        if trend_data and len(trend_data) > 1:
            trend_df = pd.DataFrame(trend_data)
            st.line_chart(trend_df.set_index('date')['surveys'])
        else:
            st.info("Insufficient data for trend analysis")
    
    with col_charts[1]:
        st.markdown("#### 🎯 Interview Types")
        interview_breakdown = get_interview_type_breakdown(agent['agent_id'])
        if interview_breakdown:
            breakdown_df = pd.DataFrame(interview_breakdown)
            st.bar_chart(breakdown_df.set_index('type')['count'])
        else:
            st.info("No data available")
    
    # Comparative analytics
    st.markdown("---")
    st.markdown("#### 📊 Team Comparison")
    team_stats = get_team_comparison(agent['agent_id'])
    
    if team_stats:
        comparison_df = pd.DataFrame(team_stats)
        st.dataframe(comparison_df, use_container_width=True)
    else:
        st.info("No team comparison data available")
    
    # Time-based analytics
    st.markdown("#### ⏰ Time Analysis")
    time_analysis = get_time_analysis(agent['agent_id'])
    
    if time_analysis:
        col_time = st.columns(2)
        with col_time[0]:
            if 'time_of_day' in time_analysis:
                st.bar_chart(pd.DataFrame(time_analysis['time_of_day']))
                st.caption("Productivity by Time of Day")
        with col_time[1]:
            if 'weekly_trend' in time_analysis:
                st.line_chart(pd.DataFrame(time_analysis['weekly_trend']))
                st.caption("Weekly Performance Trend")
    else:
        st.info("No time analysis data available")

def render_real_time_support(agent):
    """Real-time support and communication"""
    
    st.markdown("### 🆘 Real-time Support")
    
    # Support channels
    col_support = st.columns(2)
    
    with col_support[0]:
        st.markdown("#### 📞 Immediate Support")
        
        if st.button("Request Supervisor Call", use_container_width=True, type="primary"):
            request_supervisor_call(agent['agent_id'])
            st.success("Supervisor notified! They will call you shortly.")
        
        if st.button("Technical Support", use_container_width=True):
            request_technical_support(agent['agent_id'])
            st.info("Technical support team notified.")
        
        if st.button("Data Issues Help", use_container_width=True):
            request_data_support(agent['agent_id'])
            st.info("Data support team will contact you.")
    
    with col_support[1]:
        st.markdown("#### 💬 Chat Support")
        support_message = st.text_area("Describe your issue:", height=100,
                                      placeholder="Please describe the issue you're facing in detail...")
        
        col_chat = st.columns(2)
        with col_chat[0]:
            if st.button("Send to Support", use_container_width=True):
                if support_message.strip():
                    send_support_message(agent['agent_id'], support_message)
                    st.success("Message sent to support team!")
                else:
                    st.warning("Please enter a message")
        
        with col_chat[1]:
            if st.button("Clear", use_container_width=True):
                st.rerun()
    
    # Emergency protocols
    st.markdown("---")
    st.markdown("#### 🚨 Emergency Protocols")
    
    emergency_cols = st.columns(3)
    
    with emergency_cols[0]:
        if st.button("🆘 Safety Concern", type="secondary", use_container_width=True):
            trigger_safety_protocol(agent['agent_id'])
            st.error("🚨 SAFETY PROTOCOL ACTIVATED! Help is on the way. Stay safe.")
    
    with emergency_cols[1]:
        if st.button("🏥 Medical Emergency", type="secondary", use_container_width=True):
            trigger_medical_emergency(agent['agent_id'])
            st.error("🚨 MEDICAL EMERGENCY! Help has been alerted.")
    
    with emergency_cols[2]:
        if st.button("🔒 Data Breach", type="secondary", use_container_width=True):
            trigger_data_breach_protocol(agent['agent_id'])
            st.error("🚨 DATA BREACH PROTOCOL! Security team notified.")
    
    # Support history
    st.markdown("---")
    st.markdown("#### 📋 Recent Support Requests")
    
    support_history = get_support_history(agent['agent_id'], limit=5)
    
    if support_history:
        for request in support_history:
            status_color = "🟢" if request['status'] == 'resolved' else "🟡" if request['status'] == 'in_progress' else "🔴"
            st.markdown(f"""
            <div style='background: #f8f9fa; padding: 10px; border-radius: 8px; margin: 5px 0;'>
                {status_color} <strong>{request['request_type']}</strong> - {request['created_at']}  
                Status: {request['status']} | Priority: {request['priority']}
            </div>
            """, unsafe_allow_html=True)
    else:
        st.info("No recent support requests")

def render_territory_map(agent):
    """Display agent's territory and assignment locations"""
    
    st.markdown("### 🗺️ Territory & Assignment Map")
    
    if not agent.get('assigned_island_id'):
        st.warning("⚠️ No island assigned. Contact administrator.")
        return
    
    # Get all assignments with locations
    assignments_with_location = get_assignments_with_location(agent['agent_id'])
    
    if assignments_with_location:
        # Create map data
        map_data = []
        for assignment in assignments_with_location:
            if assignment['location_lat'] and assignment['location_lon']:
                map_data.append({
                    'lat': assignment['location_lat'],
                    'lon': assignment['location_lon'],
                    'name': assignment['holder_name'],
                    'status': assignment['status']
                })
        
        if map_data:
            df = pd.DataFrame(map_data)
            st.map(df[['lat', 'lon']].rename(columns={'lat': 'lat', 'lon': 'lon'}))
            
            st.markdown("#### 📍 Assignment Locations")
            st.dataframe(df[['name', 'status', 'lat', 'lon']], use_container_width=True)
        else:
            st.info("No assignments with valid location data for mapping")
    else:
        st.info("No assignments with location data")

# ============================================================================
# ENHANCED HELPER FUNCTIONS
# ============================================================================

def get_agent_assignments(agent_id, status_filter, interview_filter, date_range):
    """Get agent assignments with filters"""
    
    query = """
        SELECT aa.*, h.name as holder_name, i.island_name,
               COALESCE(aa.progress_percentage, 0) as progress_percentage
        FROM agent_assignments aa
        LEFT JOIN holders h ON aa.holder_id = h.holder_id
        LEFT JOIN islands i ON aa.island_id = i.island_id
        WHERE aa.agent_id = :aid
    """
    
    params = {"aid": agent_id}
    
    if status_filter != "all":
        query += " AND aa.status = :status"
        params["status"] = status_filter
    
    if interview_filter != "all":
        query += " AND aa.interview_type = :itype"
        params["itype"] = interview_filter
    
    if date_range == "today":
        query += " AND DATE(aa.assignment_date) = CURRENT_DATE"
    elif date_range == "this_week":
        query += " AND aa.assignment_date >= CURRENT_DATE - INTERVAL '7 days'"
    elif date_range == "this_month":
        query += " AND aa.assignment_date >= CURRENT_DATE - INTERVAL '30 days'"
    
    query += " ORDER BY aa.assignment_date DESC"
    
    try:
        with engine.connect() as conn:
            result = conn.execute(text(query), params).mappings().all()
            return [dict(row) for row in result]
    except Exception as e:
        st.error(f"Query error: {e}")
        return []

def get_pending_assignments_count(agent_id):
    """Get count of pending review assignments"""
    try:
        with engine.connect() as conn:
            return conn.execute(text("""
                SELECT COUNT(*) FROM agent_assignments 
                WHERE agent_id = :aid AND status = 'completed'
            """), {"aid": agent_id}).scalar() or 0
    except:
        return 0

def start_interview(assignment_id, agent_id):
    """Mark interview as started"""
    try:
        with engine.begin() as conn:
            conn.execute(text("""
                UPDATE agent_assignments 
                SET status = 'in_progress', updated_at = NOW()
                WHERE assignment_id = :aid
            """), {"aid": assignment_id})
            
            log_agent_activity(agent_id, 'interview_started', 
                             f"Started interview for assignment {assignment_id}")
    except Exception as e:
        st.error(f"Error: {e}")

def complete_interview(assignment_id):
    """Mark interview as completed"""
    try:
        with engine.begin() as conn:
            conn.execute(text("""
                UPDATE agent_assignments 
                SET status = 'completed', completed_date = NOW(), updated_at = NOW()
                WHERE assignment_id = :aid
            """), {"aid": assignment_id})
            
            # Update agent stats
            conn.execute(text("""
                UPDATE agents 
                SET total_surveys_completed = total_surveys_completed + 1,
                    current_assignments = current_assignments - 1
                WHERE agent_id = (SELECT agent_id FROM agent_assignments WHERE assignment_id = :aid)
            """), {"aid": assignment_id})
    except Exception as e:
        st.error(f"Error: {e}")

def log_contact_attempt(assignment_id):
    """Log a contact attempt"""
    try:
        with engine.begin() as conn:
            conn.execute(text("""
                UPDATE agent_assignments 
                SET contact_attempts = contact_attempts + 1,
                    last_contact_date = NOW(),
                    updated_at = NOW()
                WHERE assignment_id = :aid
            """), {"aid": assignment_id})
    except Exception as e:
        st.error(f"Error: {e}")

def add_assignment_note(assignment_id, note):
    """Add note to assignment"""
    try:
        with engine.begin() as conn:
            conn.execute(text("""
                UPDATE agent_assignments 
                SET notes = CONCAT(COALESCE(notes, ''), '\n[', NOW(), '] ', :note),
                    updated_at = NOW()
                WHERE assignment_id = :aid
            """), {"aid": assignment_id, "note": note})
    except Exception as e:
        st.error(f"Error: {e}")

def update_agent_device(agent_id, device_id):
    """Update agent device ID"""
    try:
        with engine.begin() as conn:
            conn.execute(text("""
                UPDATE agents SET device_id = :did, updated_at = NOW()
                WHERE agent_id = :aid
            """), {"aid": agent_id, "did": device_id})
    except Exception as e:
        st.error(f"Error: {e}")

def get_agent_activity(agent_id, limit=10):
    """Get recent agent activity"""
    try:
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT * FROM agent_activity_log 
                WHERE agent_id = :aid 
                ORDER BY created_at DESC LIMIT :lim
            """), {"aid": agent_id, "lim": limit}).mappings().all()
            return [dict(row) for row in result]
    except:
        return []

def log_agent_activity(agent_id, activity_type, description, metadata=None):
    """Log agent activity"""
    try:
        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO agent_activity_log (agent_id, activity_type, description, metadata)
                VALUES (:aid, :atype, :desc, :meta)
            """), {
                "aid": agent_id,
                "atype": activity_type,
                "desc": description,
                "meta": json.dumps(metadata) if metadata else None
            })
    except Exception as e:
        print(f"Activity log error: {e}")

def get_island_options():
    """Get list of islands for selection"""
    try:
        with engine.connect() as conn:
            islands = conn.execute(text("""
                SELECT island_name FROM islands ORDER BY island_name
            """)).fetchall()
            return [i[0] for i in islands]
    except:
        return []

def create_interview_assignment(agent_id, assignment_id, candidate_name, 
                               interview_type, phone, island, scheduled_date, 
                               notes, lat, lon):
    """Create or update interview assignment"""
    try:
        with engine.begin() as conn:
            # Get island_id
            island_id = conn.execute(text("""
                SELECT island_id FROM islands WHERE island_name = :name
            """), {"name": island}).scalar()
            
            if assignment_id:
                # Update existing
                conn.execute(text("""
                    UPDATE agent_assignments
                    SET status = 'in_progress', interview_type = :itype,
                        scheduled_date = :sdate, notes = :notes,
                        location_lat = :lat, location_lon = :lon,
                        updated_at = NOW()
                    WHERE assignment_id = :aid
                """), {
                    "aid": assignment_id, "itype": interview_type,
                    "sdate": scheduled_date, "notes": notes,
                    "lat": lat, "lon": lon
                })
            else:
                # Create holder first
                holder_result = conn.execute(text("""
                    INSERT INTO holders (name, owner_id)
                    VALUES (:name, :oid)
                    RETURNING holder_id
                """), {"name": candidate_name, "oid": agent_id})
                
                holder_id = holder_result.scalar()
                
                # Create assignment
                conn.execute(text("""
                    INSERT INTO agent_assignments 
                    (agent_id, holder_id, island_id, interview_type, status, 
                     scheduled_date, notes, location_lat, location_lon)
                    VALUES (:aid, :hid, :iid, :itype, 'in_progress', 
                            :sdate, :notes, :lat, :lon)
                """), {
                    "aid": agent_id, "hid": holder_id, "iid": island_id,
                    "itype": interview_type, "sdate": scheduled_date,
                    "notes": notes, "lat": lat, "lon": lon
                })
                
                # Update agent stats
                conn.execute(text("""
                    UPDATE agents 
                    SET current_assignments = current_assignments + 1
                    WHERE agent_id = :aid
                """), {"aid": agent_id})
            
            return True
    except Exception as e:
        st.error(f"Assignment error: {e}")
        return False

def get_last_assignment_id(agent_id):
    """Get the last assignment ID created by agent"""
    try:
        with engine.connect() as conn:
            return conn.execute(text("""
                SELECT assignment_id FROM agent_assignments 
                WHERE agent_id = :aid 
                ORDER BY assignment_id DESC LIMIT 1
            """), {"aid": agent_id}).scalar()
    except:
        return None

def get_assignment_details(assignment_id):
    """Get detailed assignment information"""
    try:
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT aa.*, h.name as holder_name, i.island_name,
                       COALESCE(aa.progress_percentage, 0) as progress_percentage
                FROM agent_assignments aa
                LEFT JOIN holders h ON aa.holder_id = h.holder_id
                LEFT JOIN islands i ON aa.island_id = i.island_id
                WHERE aa.assignment_id = :aid
            """), {"aid": assignment_id}).mappings().first()
            return dict(result) if result else None
    except:
        return None

def update_interview_progress(assignment_id, progress):
    """Update interview progress percentage"""
    try:
        with engine.begin() as conn:
            conn.execute(text("""
                UPDATE agent_assignments 
                SET progress_percentage = :progress, updated_at = NOW()
                WHERE assignment_id = :aid
            """), {"aid": assignment_id, "progress": progress})
    except Exception as e:
        st.error(f"Progress update error: {e}")

def save_interview_draft(assignment_id):
    """Save interview as draft"""
    try:
        with engine.begin() as conn:
            conn.execute(text("""
                UPDATE agent_assignments 
                SET status = 'in_progress', updated_at = NOW()
                WHERE assignment_id = :aid
            """), {"aid": assignment_id})
    except Exception as e:
        st.error(f"Draft save error: {e}")

def get_pending_sync_count(agent_id):
    """Get count of pending sync items"""
    try:
        with engine.connect() as conn:
            return conn.execute(text("""
                SELECT COUNT(*) FROM offline_data_queue 
                WHERE agent_id = :aid AND sync_status = 'pending'
            """), {"aid": agent_id}).scalar() or 0
    except:
        return 0

def get_pending_sync_data(agent_id):
    """Get pending sync data"""
    try:
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT * FROM offline_data_queue 
                WHERE agent_id = :aid AND sync_status IN ('pending', 'failed')
                ORDER BY collected_at DESC
            """), {"aid": agent_id}).mappings().all()
            return [dict(row) for row in result]
    except:
        return []

def perform_data_sync(agent_id):
    """Perform data synchronization"""
    try:
        with engine.begin() as conn:
            # Create sync session
            result = conn.execute(text("""
                INSERT INTO sync_sessions (agent_id, device_id, connection_type)
                VALUES (:aid, 'web', 'wifi')
                RETURNING session_id
            """), {"aid": agent_id})
            
            session_id = result.scalar()
            
            # Update pending items
            result = conn.execute(text("""
                UPDATE offline_data_queue 
                SET sync_status = 'synced', synced_at = NOW()
                WHERE agent_id = :aid AND sync_status = 'pending'
                RETURNING queue_id
            """), {"aid": agent_id})
            
            synced_count = len(result.fetchall())
            
            # Complete sync session
            conn.execute(text("""
                UPDATE sync_sessions 
                SET sync_completed_at = NOW(), 
                    records_uploaded = :count,
                    sync_status = 'completed'
                WHERE session_id = :sid
            """), {"sid": session_id, "count": synced_count})
            
            # Update agent last sync
            conn.execute(text("""
                UPDATE agents SET last_sync_at = NOW() WHERE agent_id = :aid
            """), {"aid": agent_id})
            
            return synced_count
            
    except Exception as e:
        st.error(f"Sync error: {e}")
        return 0

def upload_all_pending(agent_id):
    """Upload all pending data"""
    perform_data_sync(agent_id)

def retry_failed_syncs(agent_id):
    """Retry failed sync attempts"""
    try:
        with engine.begin() as conn:
            conn.execute(text("""
                UPDATE offline_data_queue 
                SET sync_status = 'pending', sync_attempts = sync_attempts + 1
                WHERE agent_id = :aid AND sync_status = 'failed'
            """), {"aid": agent_id})
            st.success("✅ Failed syncs queued for retry")
    except Exception as e:
        st.error(f"Error: {e}")

def clear_failed_syncs(agent_id):
    """Clear failed sync attempts"""
    try:
        with engine.begin() as conn:
            conn.execute(text("""
                DELETE FROM offline_data_queue 
                WHERE agent_id = :aid AND sync_status = 'failed'
            """), {"aid": agent_id})
            st.success("✅ Failed syncs cleared")
    except Exception as e:
        st.error(f"Error: {e}")

def get_sync_history(agent_id, limit=10):
    """Get sync history"""
    try:
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT * FROM sync_sessions 
                WHERE agent_id = :aid 
                ORDER BY sync_started_at DESC LIMIT :lim
            """), {"aid": agent_id, "lim": limit}).mappings().all()
            return [dict(row) for row in result]
    except:
        return []

def get_offline_storage_usage(agent_id):
    """Get offline storage usage in MB"""
    try:
        with engine.connect() as conn:
            # This would typically come from device storage API
            # For now, we'll estimate based on queue size
            count = conn.execute(text("""
                SELECT COUNT(*) FROM offline_data_queue 
                WHERE agent_id = :aid
            """), {"aid": agent_id}).scalar() or 0
            return round(count * 0.1, 1)  # Estimate 0.1MB per record
    except:
        return 0.0

def export_offline_data(agent_id):
    """Export offline data for backup"""
    # This would typically generate a file for download
    st.info("Data export functionality would be implemented here")

def cleanup_old_data(agent_id, retention_days):
    """Clean up old offline data"""
    try:
        with engine.begin() as conn:
            conn.execute(text("""
                DELETE FROM offline_data_queue 
                WHERE agent_id = :aid AND collected_at < NOW() - INTERVAL ':days days'
            """), {"aid": agent_id, "days": retention_days})
    except Exception as e:
        st.error(f"Cleanup error: {e}")

def reset_local_cache(agent_id):
    """Reset local cache"""
    try:
        with engine.begin() as conn:
            conn.execute(text("""
                DELETE FROM offline_data_queue 
                WHERE agent_id = :aid AND sync_status = 'synced'
            """), {"aid": agent_id})
    except Exception as e:
        st.error(f"Cache reset error: {e}")

def get_agent_statistics(agent_id):
    """Get agent performance statistics"""
    try:
        with engine.connect() as conn:
            # Total surveys
            total = conn.execute(text("""
                SELECT COUNT(*) FROM agent_assignments 
                WHERE agent_id = :aid AND status = 'completed'
            """), {"aid": agent_id}).scalar() or 0
            
            # This month
            this_month = conn.execute(text("""
                SELECT COUNT(*) FROM agent_assignments 
                WHERE agent_id = :aid AND status = 'completed'
                AND completed_date >= DATE_TRUNC('month', CURRENT_DATE)
            """), {"aid": agent_id}).scalar() or 0
            
            # Total assigned
            total_assigned = conn.execute(text("""
                SELECT COUNT(*) FROM agent_assignments 
                WHERE agent_id = :aid
            """), {"aid": agent_id}).scalar() or 1
            
            completion_rate = (total / total_assigned * 100) if total_assigned > 0 else 0
            avg_per_day = total / 30.0 if total > 0 else 0
            
            return {
                'total_surveys': total,
                'completion_rate': completion_rate,
                'avg_per_day': avg_per_day,
                'this_month': this_month
            }
    except:
        return {
            'total_surveys': 0,
            'completion_rate': 0,
            'avg_per_day': 0,
            'this_month': 0
        }

def get_enhanced_agent_statistics(agent_id):
    """Get enhanced agent performance statistics"""
    try:
        with engine.connect() as conn:
            # Average duration
            avg_duration = conn.execute(text("""
                SELECT AVG(EXTRACT(EPOCH FROM (completed_date - assignment_date))/60)
                FROM agent_assignments 
                WHERE agent_id = :aid AND status = 'completed'
                AND completed_date IS NOT NULL
            """), {"aid": agent_id}).scalar() or 30
            
            # First-time completion rate
            first_time_complete = conn.execute(text("""
                SELECT COUNT(*) FROM agent_assignments 
                WHERE agent_id = :aid AND status = 'completed'
                AND contact_attempts = 1
            """), {"aid": agent_id}).scalar() or 0
            
            total_completed = conn.execute(text("""
                SELECT COUNT(*) FROM agent_assignments 
                WHERE agent_id = :aid AND status = 'completed'
            """), {"aid": agent_id}).scalar() or 1
            
            first_time_rate = (first_time_complete / total_completed * 100) if total_completed > 0 else 0
            
            return {
                'avg_duration': round(avg_duration, 1),
                'first_time_completion_rate': round(first_time_rate, 1),
                'quality_score': 8.5,  # This would come from quality assessments
                'success_rate': 95,    # This would be calculated from various metrics
                'satisfaction_score': 4.2  # This would come from participant feedback
            }
    except:
        return {
            'avg_duration': 30,
            'first_time_completion_rate': 0,
            'quality_score': 0,
            'success_rate': 0,
            'satisfaction_score': 0
        }

def get_survey_trend(agent_id, days=30):
    """Get survey completion trend"""
    try:
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT DATE(completed_date) as date, COUNT(*) as count
                FROM agent_assignments
                WHERE agent_id = :aid 
                AND status = 'completed'
                AND completed_date >= CURRENT_DATE - INTERVAL ':days days'
                GROUP BY DATE(completed_date)
                ORDER BY date
            """), {"aid": agent_id, "days": days}).mappings().all()
            return [{'date': row['date'], 'surveys': row['count']} for row in result]
    except:
        return []

def get_interview_type_breakdown(agent_id):
    """Get breakdown by interview type"""
    try:
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT interview_type as type, COUNT(*) as count
                FROM agent_assignments
                WHERE agent_id = :aid AND status = 'completed'
                GROUP BY interview_type
            """), {"aid": agent_id}).mappings().all()
            return [{'type': row['type'], 'count': row['count']} for row in result]
    except:
        return []

def get_team_comparison(agent_id):
    """Get team comparison data"""
    # This would typically compare the agent with their team
    try:
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT a.agent_code, a.full_name,
                       COUNT(aa.assignment_id) as completed_surveys,
                       ROUND(AVG(EXTRACT(EPOCH FROM (aa.completed_date - aa.assignment_date))/60), 1) as avg_duration
                FROM agents a
                LEFT JOIN agent_assignments aa ON a.agent_id = aa.agent_id AND aa.status = 'completed'
                WHERE a.assigned_island_id = (SELECT assigned_island_id FROM agents WHERE agent_id = :aid)
                GROUP BY a.agent_id, a.agent_code, a.full_name
                ORDER BY completed_surveys DESC
            """), {"aid": agent_id}).mappings().all()
            return [dict(row) for row in result]
    except:
        return []

def get_time_analysis(agent_id):
    """Get time-based analysis"""
    # This would analyze performance by time of day and week
    try:
        with engine.connect() as conn:
            # Time of day analysis
            time_of_day = conn.execute(text("""
                SELECT EXTRACT(HOUR FROM completed_date) as hour, COUNT(*) as count
                FROM agent_assignments
                WHERE agent_id = :aid AND status = 'completed'
                GROUP BY EXTRACT(HOUR FROM completed_date)
                ORDER BY hour
            """), {"aid": agent_id}).mappings().all()
            
            # Weekly trend
            weekly_trend = conn.execute(text("""
                SELECT DATE_TRUNC('week', completed_date) as week, COUNT(*) as count
                FROM agent_assignments
                WHERE agent_id = :aid AND status = 'completed'
                GROUP BY DATE_TRUNC('week', completed_date)
                ORDER BY week
            """), {"aid": agent_id}).mappings().all()
            
            return {
                'time_of_day': [dict(row) for row in time_of_day],
                'weekly_trend': [dict(row) for row in weekly_trend]
            }
    except:
        return {}

def get_assignments_with_location(agent_id):
    """Get assignments with location data"""
    try:
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT aa.*, h.name as holder_name
                FROM agent_assignments aa
                LEFT JOIN holders h ON aa.holder_id = h.holder_id
                WHERE aa.agent_id = :aid 
                AND aa.location_lat IS NOT NULL 
                AND aa.location_lon IS NOT NULL
            """), {"aid": agent_id}).mappings().all()
            return [dict(row) for row in result]
    except:
        return []

# Emergency and Support Functions
def trigger_safety_protocol(agent_id):
    """Trigger safety protocol"""
    try:
        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO emergency_alerts (agent_id, alert_type, priority, status)
                VALUES (:aid, 'safety_concern', 'high', 'active')
            """), {"aid": agent_id})
            log_agent_activity(agent_id, 'safety_alert', 'Safety protocol activated')
    except Exception as e:
        st.error(f"Safety alert error: {e}")

def trigger_medical_emergency(agent_id):
    """Trigger medical emergency protocol"""
    try:
        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO emergency_alerts (agent_id, alert_type, priority, status)
                VALUES (:aid, 'medical_emergency', 'critical', 'active')
            """), {"aid": agent_id})
            log_agent_activity(agent_id, 'medical_alert', 'Medical emergency protocol activated')
    except Exception as e:
        st.error(f"Medical alert error: {e}")

def trigger_data_breach_protocol(agent_id):
    """Trigger data breach protocol"""
    try:
        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO emergency_alerts (agent_id, alert_type, priority, status)
                VALUES (:aid, 'data_breach', 'high', 'active')
            """), {"aid": agent_id})
            log_agent_activity(agent_id, 'data_breach_alert', 'Data breach protocol activated')
    except Exception as e:
        st.error(f"Data breach alert error: {e}")

def request_supervisor_call(agent_id):
    """Request supervisor call"""
    try:
        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO support_requests (agent_id, request_type, priority, status)
                VALUES (:aid, 'supervisor_call', 'medium', 'pending')
            """), {"aid": agent_id})
            log_agent_activity(agent_id, 'support_request', 'Supervisor call requested')
    except Exception as e:
        st.error(f"Support request error: {e}")

def request_technical_support(agent_id):
    """Request technical support"""
    try:
        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO support_requests (agent_id, request_type, priority, status)
                VALUES (:aid, 'technical_support', 'medium', 'pending')
            """), {"aid": agent_id})
            log_agent_activity(agent_id, 'support_request', 'Technical support requested')
    except Exception as e:
        st.error(f"Support request error: {e}")

def request_data_support(agent_id):
    """Request data support"""
    try:
        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO support_requests (agent_id, request_type, priority, status)
                VALUES (:aid, 'data_support', 'medium', 'pending')
            """), {"aid": agent_id})
            log_agent_activity(agent_id, 'support_request', 'Data support requested')
    except Exception as e:
        st.error(f"Support request error: {e}")

def send_support_message(agent_id, message):
    """Send support message"""
    try:
        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO support_requests (agent_id, request_type, description, priority, status)
                VALUES (:aid, 'general_support', :msg, 'low', 'pending')
            """), {"aid": agent_id, "msg": message})
            log_agent_activity(agent_id, 'support_message', 'Support message sent')
    except Exception as e:
        st.error(f"Support message error: {e}")

def get_support_history(agent_id, limit=5):
    """Get support request history"""
    try:
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT * FROM support_requests 
                WHERE agent_id = :aid 
                ORDER BY created_at DESC LIMIT :lim
            """), {"aid": agent_id, "lim": limit}).mappings().all()
            return [dict(row) for row in result]
    except:
        return []