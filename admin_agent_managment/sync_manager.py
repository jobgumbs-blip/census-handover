"""
Offline Data Collection & Auto-Sync Manager
Production-ready module for field agents with robust error handling and recovery
"""

import streamlit as st
import json
import hashlib
import time
import pandas as pd
from datetime import datetime, timedelta
from sqlalchemy import text, exc
import logging
from typing import Dict, List, Optional, Tuple
import uuid

from census_app.db import engine

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('sync_manager')

class OfflineDataCollector:
    """
    Production-ready offline data collector with robust sync capabilities
    Features:
    - Automatic retry with exponential backoff
    - Data integrity verification
    - Conflict resolution
    - Batch processing
    - Progress tracking
    - Error recovery
    """
    
    def __init__(self, agent_id: int, device_id: str):
        self.agent_id = agent_id
        self.device_id = device_id
        self.session_id = None
        
        # Initialize session state
        self._initialize_session_state()
        
        # Sync configuration
        self.config = {
            'max_retries': 3,
            'batch_size': 50,
            'retry_delay': 5,  # seconds
            'sync_timeout': 30,  # seconds
            'checksum_validation': True
        }
    
    def _initialize_session_state(self):
        """Initialize session state for offline operations"""
        if 'offline_queue' not in st.session_state:
            st.session_state['offline_queue'] = []
        
        if 'sync_sessions' not in st.session_state:
            st.session_state['sync_sessions'] = {}
        
        if 'network_status' not in st.session_state:
            st.session_state['network_status'] = 'online'
        
        if 'last_sync_attempt' not in st.session_state:
            st.session_state['last_sync_attempt'] = None
        
        if 'sync_errors' not in st.session_state:
            st.session_state['sync_errors'] = []
    
    def queue_data(self, data_type: str, data_payload: Dict, holder_id: Optional[int] = None, 
                   metadata: Optional[Dict] = None) -> Dict:
        """
        Queue data for offline storage with enhanced metadata
        
        Args:
            data_type: Type of data (e.g., 'holder_info', 'survey_section')
            data_payload: Dictionary containing the data
            holder_id: Optional holder ID
            metadata: Additional metadata (priority, tags, etc.)
        
        Returns:
            dict: Queued item with full metadata
        """
        try:
            # Generate unique ID for this data item
            item_id = str(uuid.uuid4())
            
            # Generate checksum for data integrity
            checksum = self._generate_checksum(data_payload)
            
            # Prepare queued item
            queued_item = {
                'item_id': item_id,
                'agent_id': self.agent_id,
                'holder_id': holder_id,
                'device_id': self.device_id,
                'data_type': data_type,
                'data_payload': data_payload,
                'collected_at': datetime.now().isoformat(),
                'sync_status': 'pending',
                'checksum': checksum,
                'sync_attempts': 0,
                'last_attempt_at': None,
                'error_message': None,
                'metadata': metadata or {},
                'queue_timestamp': datetime.now().timestamp(),
                'priority': metadata.get('priority', 'normal') if metadata else 'normal'
            }
            
            # Add to session state queue
            st.session_state['offline_queue'].append(queued_item)
            
            # Log the queue operation
            logger.info(f"Queued data: {data_type} for holder {holder_id}, ID: {item_id}")
            
            # Try immediate sync if online and auto-sync enabled
            if (st.session_state['network_status'] == 'online' and 
                st.session_state.get('auto_sync_enabled', True)):
                self.attempt_sync_async()
            
            return queued_item
            
        except Exception as e:
            logger.error(f"Error queueing data: {str(e)}")
            st.session_state['sync_errors'].append({
                'timestamp': datetime.now().isoformat(),
                'error': f"Queue error: {str(e)}",
                'data_type': data_type
            })
            raise
    
    def save_to_database(self, queued_item: Dict) -> Tuple[bool, Optional[str]]:
        """
        Save queued item to database with enhanced error handling
        
        Args:
            queued_item: Dictionary containing queued data
        
        Returns:
            tuple: (success_status, queue_id_or_error_message)
        """
        try:
            with engine.begin() as conn:
                result = conn.execute(text("""
                    INSERT INTO offline_data_queue 
                    (agent_id, holder_id, device_id, data_type, data_payload, 
                     collected_at, sync_status, checksum, metadata, priority)
                    VALUES (:aid, :hid, :did, :dtype, :payload, :collected, 
                            :status, :check, :meta, :priority)
                    RETURNING queue_id
                """), {
                    'aid': queued_item['agent_id'],
                    'hid': queued_item.get('holder_id'),
                    'did': queued_item['device_id'],
                    'dtype': queued_item['data_type'],
                    'payload': json.dumps(queued_item['data_payload']),
                    'collected': queued_item['collected_at'],
                    'status': 'pending',
                    'check': queued_item['checksum'],
                    'meta': json.dumps(queued_item.get('metadata', {})),
                    'priority': queued_item.get('priority', 'normal')
                })
                
                queue_id = result.scalar()
                logger.info(f"Saved to database queue: {queue_id}")
                return True, str(queue_id)
                
        except exc.SQLAlchemyError as e:
            error_msg = f"Database save failed: {str(e)}"
            logger.error(error_msg)
            return False, error_msg
        except Exception as e:
            error_msg = f"Unexpected error: {str(e)}"
            logger.error(error_msg)
            return False, error_msg
    
    def attempt_sync(self, force: bool = False) -> Dict:
        """
        Attempt to sync all pending data with enhanced error handling
        
        Args:
            force: Whether to force sync regardless of conditions
        
        Returns:
            dict: Detailed sync results
        """
        if not st.session_state['offline_queue'] and not force:
            return {
                'success': True,
                'synced': 0,
                'failed': 0,
                'pending': 0,
                'errors': [],
                'session_id': None
            }
        
        # Check network conditions
        if (st.session_state['network_status'] == 'offline' and 
            not st.session_state.get('emergency_sync', False)):
            return {
                'success': False,
                'synced': 0,
                'failed': 0,
                'pending': len(st.session_state['offline_queue']),
                'errors': ['Network offline'],
                'session_id': None
            }
        
        # Rate limiting
        last_attempt = st.session_state.get('last_sync_attempt')
        if (last_attempt and not force and 
            (datetime.now() - last_attempt).seconds < 10):  # 10-second cooldown
            return {
                'success': False,
                'synced': 0,
                'failed': 0,
                'pending': len(st.session_state['offline_queue']),
                'errors': ['Rate limited'],
                'session_id': None
            }
        
        st.session_state['last_sync_attempt'] = datetime.now()
        
        try:
            # Create sync session
            self.session_id = self._create_sync_session()
            
            # Process queue in batches
            results = self._process_sync_batches()
            
            # Complete sync session
            self._complete_sync_session(results)
            
            logger.info(f"Sync completed: {results['synced']} synced, {results['failed']} failed")
            
            return {
                'success': results['failed'] == 0,
                'synced': results['synced'],
                'failed': results['failed'],
                'pending': results['pending'],
                'errors': results['errors'],
                'session_id': self.session_id
            }
            
        except Exception as e:
            error_msg = f"Sync process failed: {str(e)}"
            logger.error(error_msg)
            st.session_state['sync_errors'].append({
                'timestamp': datetime.now().isoformat(),
                'error': error_msg,
                'session_id': self.session_id
            })
            
            return {
                'success': False,
                'synced': 0,
                'failed': 0,
                'pending': len(st.session_state['offline_queue']),
                'errors': [error_msg],
                'session_id': self.session_id
            }
    
    def attempt_sync_async(self):
        """Non-blocking sync attempt for background operations"""
        try:
            # This would typically run in a background thread
            # For Streamlit, we'll use session state to track async status
            if not st.session_state.get('sync_in_progress', False):
                st.session_state['sync_in_progress'] = True
                st.session_state['last_async_sync'] = datetime.now()
                
                # In a real implementation, this would be in a separate thread
                results = self.attempt_sync()
                st.session_state['last_sync_results'] = results
                st.session_state['sync_in_progress'] = False
                
        except Exception as e:
            logger.error(f"Async sync error: {e}")
            st.session_state['sync_in_progress'] = False
    
    def _process_sync_batches(self) -> Dict:
        """Process sync queue in batches with error handling"""
        pending_queue = st.session_state['offline_queue'].copy()
        synced_count = 0
        failed_count = 0
        errors = []
        
        # Sort by priority and timestamp
        pending_queue.sort(key=lambda x: (
            {'high': 0, 'normal': 1, 'low': 2}[x.get('priority', 'normal')],
            x['queue_timestamp']
        ))
        
        # Process in batches
        for i in range(0, len(pending_queue), self.config['batch_size']):
            batch = pending_queue[i:i + self.config['batch_size']]
            batch_results = self._sync_batch(batch)
            
            synced_count += batch_results['synced']
            failed_count += batch_results['failed']
            errors.extend(batch_results['errors'])
            
            # Update progress
            progress = (i + len(batch)) / len(pending_queue)
            st.session_state['sync_progress'] = progress
            
            # Small delay between batches to avoid overwhelming the server
            time.sleep(0.1)
        
        # Update the main queue
        self._update_queue_after_sync(pending_queue)
        
        return {
            'synced': synced_count,
            'failed': failed_count,
            'pending': len(st.session_state['offline_queue']),
            'errors': errors
        }
    
    def _sync_batch(self, batch: List[Dict]) -> Dict:
        """Sync a batch of items"""
        synced = 0
        failed = 0
        errors = []
        
        for item in batch:
            if item['sync_status'] == 'pending' or item['sync_status'] == 'failed':
                success = self._sync_single_item(item)
                
                if success:
                    item['sync_status'] = 'synced'
                    item['synced_at'] = datetime.now().isoformat()
                    synced += 1
                else:
                    item['sync_status'] = 'failed'
                    item['sync_attempts'] += 1
                    item['last_attempt_at'] = datetime.now().isoformat()
                    failed += 1
                    
                    # Log error
                    error_msg = f"Failed to sync {item['data_type']} (attempt {item['sync_attempts']})"
                    errors.append(error_msg)
                    item['error_message'] = error_msg
        
        return {
            'synced': synced,
            'failed': failed,
            'errors': errors
        }
    
    def _sync_single_item(self, item: Dict) -> bool:
        """
        Sync individual queued item with retry logic and conflict resolution
        """
        max_attempts = self.config['max_retries']
        
        for attempt in range(max_attempts):
            try:
                # Verify data integrity before sync
                if self.config['checksum_validation']:
                    current_checksum = self._generate_checksum(item['data_payload'])
                    if current_checksum != item['checksum']:
                        logger.warning(f"Data integrity check failed for {item['item_id']}")
                        return False
                
                # Route to appropriate handler
                success = self._route_sync_handler(item)
                
                if success:
                    # Also save to database queue for audit
                    self.save_to_database(item)
                    return True
                else:
                    # Wait before retry (exponential backoff)
                    if attempt < max_attempts - 1:
                        time.sleep(self.config['retry_delay'] * (2 ** attempt))
                        
            except Exception as e:
                logger.error(f"Sync attempt {attempt + 1} failed: {str(e)}")
                if attempt < max_attempts - 1:
                    time.sleep(self.config['retry_delay'] * (2 ** attempt))
                continue
        
        return False
    
    def _route_sync_handler(self, item: Dict) -> bool:
        """Route item to appropriate sync handler"""
        data_payload = item['data_payload']
        data_type = item['data_type']
        
        try:
            with engine.begin() as conn:
                if data_type == 'holder_information':
                    return self._sync_holder_info(conn, data_payload, item)
                
                elif data_type == 'household_information':
                    return self._sync_household_info(conn, data_payload, item)
                
                elif data_type == 'labour_information':
                    return self._sync_labour_info(conn, data_payload, item)
                
                elif data_type == 'machinery_information':
                    return self._sync_machinery_info(conn, data_payload, item)
                
                elif data_type == 'land_use_information':
                    return self._sync_land_use_info(conn, data_payload, item)
                
                elif data_type == 'assignment_update':
                    return self._sync_assignment_update(conn, data_payload, item)
                
                elif data_type == 'location_update':
                    return self._sync_location_update(conn, data_payload, item)
                
                elif data_type == 'interview_setup':
                    return self._sync_interview_setup(conn, data_payload, item)
                
                elif data_type == 'survey_progress':
                    return self._sync_survey_progress(conn, data_payload, item)
                
                else:
                    # Generic handler for unknown types
                    return self._sync_generic_data(conn, data_payload, item)
                    
        except Exception as e:
            logger.error(f"Handler error for {data_type}: {str(e)}")
            return False
    
    def _sync_holder_info(self, conn, data: Dict, item: Dict) -> bool:
        """Sync holder information with conflict resolution"""
        try:
            holder_id = item.get('holder_id')
            
            if holder_id:
                # Update existing holder with conflict detection
                result = conn.execute(text("""
                    UPDATE holders 
                    SET name = COALESCE(:name, name),
                        date_of_birth = COALESCE(:dob, date_of_birth),
                        gender = COALESCE(:gender, gender),
                        education_level = COALESCE(:edu, education_level),
                        marital_status = COALESCE(:marital, marital_status),
                        phone_number = COALESCE(:phone, phone_number),
                        email = COALESCE(:email, email),
                        latitude = COALESCE(:lat, latitude),
                        longitude = COALESCE(:lon, longitude),
                        updated_at = NOW()
                    WHERE holder_id = :hid
                    RETURNING holder_id
                """), {
                    'hid': holder_id,
                    'name': data.get('name'),
                    'dob': data.get('date_of_birth'),
                    'gender': data.get('gender'),
                    'edu': data.get('education_level'),
                    'marital': data.get('marital_status'),
                    'phone': data.get('phone_number'),
                    'email': data.get('email'),
                    'lat': data.get('latitude'),
                    'lon': data.get('longitude')
                })
                
                if result.scalar() is None:
                    logger.warning(f"Holder {holder_id} not found, may have been deleted")
                    return False
                    
            else:
                # Create new holder
                result = conn.execute(text("""
                    INSERT INTO holders 
                    (owner_id, name, date_of_birth, gender, education_level, 
                     marital_status, phone_number, email, latitude, longitude, status)
                    VALUES (:oid, :name, :dob, :gender, :edu, :marital, :phone, :email, :lat, :lon, 'active')
                    RETURNING holder_id
                """), {
                    'oid': self.agent_id,
                    'name': data.get('name'),
                    'dob': data.get('date_of_birth'),
                    'gender': data.get('gender'),
                    'edu': data.get('education_level'),
                    'marital': data.get('marital_status'),
                    'phone': data.get('phone_number'),
                    'email': data.get('email'),
                    'lat': data.get('latitude'),
                    'lon': data.get('longitude')
                })
                
                # Update item with new holder_id for future syncs
                new_holder_id = result.scalar()
                item['holder_id'] = new_holder_id
                logger.info(f"Created new holder: {new_holder_id}")
            
            return True
            
        except Exception as e:
            logger.error(f"Holder sync error: {str(e)}")
            return False
    
    def _sync_household_info(self, conn, data: Dict, item: Dict) -> bool:
        """Sync household information"""
        try:
            conn.execute(text("""
                INSERT INTO household_data 
                (holder_id, household_size, dependents, primary_income_source,
                 secondary_income_source, housing_type, data_json)
                VALUES (:hid, :size, :dep, :primary_income, :secondary_income, :housing, :data)
                ON CONFLICT (holder_id) 
                DO UPDATE SET 
                    household_size = EXCLUDED.household_size,
                    dependents = EXCLUDED.dependents,
                    primary_income_source = EXCLUDED.primary_income_source,
                    secondary_income_source = EXCLUDED.secondary_income_source,
                    housing_type = EXCLUDED.housing_type,
                    data_json = EXCLUDED.data_json,
                    updated_at = NOW()
            """), {
                'hid': item['holder_id'],
                'size': data.get('household_size'),
                'dep': data.get('dependents'),
                'primary_income': data.get('primary_income_source'),
                'secondary_income': data.get('secondary_income_source'),
                'housing': data.get('housing_type'),
                'data': json.dumps(data)
            })
            return True
        except Exception as e:
            logger.error(f"Household sync error: {str(e)}")
            return False
    
    def _sync_labour_info(self, conn, data: Dict, item: Dict) -> bool:
        """Sync labour information"""
        try:
            # Clear existing labour data for this holder
            conn.execute(text("""
                DELETE FROM labour_data WHERE holder_id = :hid
            """), {'hid': item['holder_id']})
            
            # Insert new labour data
            labour_entries = data.get('labour_entries', [])
            for entry in labour_entries:
                conn.execute(text("""
                    INSERT INTO labour_data (holder_id, labour_type, count, description, data_json)
                    VALUES (:hid, :ltype, :count, :desc, :data)
                """), {
                    'hid': item['holder_id'],
                    'ltype': entry.get('labour_type'),
                    'count': entry.get('count'),
                    'desc': entry.get('description'),
                    'data': json.dumps(entry)
                })
            return True
        except Exception as e:
            logger.error(f"Labour sync error: {str(e)}")
            return False
    
    def _sync_machinery_info(self, conn, data: Dict, item: Dict) -> bool:
        """Sync machinery information"""
        try:
            conn.execute(text("""
                INSERT INTO machinery_data (holder_id, machinery_json, updated_at)
                VALUES (:hid, :data, NOW())
                ON CONFLICT (holder_id)
                DO UPDATE SET 
                    machinery_json = EXCLUDED.machinery_json,
                    updated_at = NOW()
            """), {
                'hid': item['holder_id'],
                'data': json.dumps(data)
            })
            return True
        except Exception as e:
            logger.error(f"Machinery sync error: {str(e)}")
            return False
    
    def _sync_land_use_info(self, conn, data: Dict, item: Dict) -> bool:
        """Sync land use information"""
        try:
            conn.execute(text("""
                INSERT INTO land_use_data (holder_id, land_data_json, updated_at)
                VALUES (:hid, :data, NOW())
                ON CONFLICT (holder_id)
                DO UPDATE SET 
                    land_data_json = EXCLUDED.land_data_json,
                    updated_at = NOW()
            """), {
                'hid': item['holder_id'],
                'data': json.dumps(data)
            })
            return True
        except Exception as e:
            logger.error(f"Land use sync error: {str(e)}")
            return False
    
    def _sync_assignment_update(self, conn, data: Dict, item: Dict) -> bool:
        """Sync assignment status updates"""
        try:
            conn.execute(text("""
                UPDATE agent_assignments
                SET status = :status,
                    contact_attempts = :attempts,
                    last_contact_date = :last_contact,
                    notes = CONCAT(COALESCE(notes, ''), '\n', :new_notes),
                    completion_percentage = :progress,
                    updated_at = NOW()
                WHERE assignment_id = :aid AND agent_id = :agent_id
            """), {
                'aid': data.get('assignment_id'),
                'agent_id': self.agent_id,
                'status': data.get('status'),
                'attempts': data.get('contact_attempts'),
                'last_contact': data.get('last_contact_date'),
                'new_notes': data.get('notes', ''),
                'progress': data.get('completion_percentage', 0)
            })
            return True
        except Exception as e:
            logger.error(f"Assignment sync error: {str(e)}")
            return False
    
    def _sync_location_update(self, conn, data: Dict, item: Dict) -> bool:
        """Sync location updates"""
        try:
            conn.execute(text("""
                UPDATE holders
                SET latitude = :lat, longitude = :lon, 
                    location_accuracy = :accuracy, updated_at = NOW()
                WHERE holder_id = :hid
            """), {
                'hid': item['holder_id'],
                'lat': data.get('latitude'),
                'lon': data.get('longitude'),
                'accuracy': data.get('accuracy')
            })
            return True
        except Exception as e:
            logger.error(f"Location sync error: {str(e)}")
            return False
    
    def _sync_interview_setup(self, conn, data: Dict, item: Dict) -> bool:
        """Sync interview setup data"""
        try:
            # Create or update assignment
            result = conn.execute(text("""
                INSERT INTO agent_assignments 
                (agent_id, interview_type, status, scheduled_date, notes, 
                 created_at, updated_at)
                VALUES (:aid, :itype, 'scheduled', :sdate, :notes, NOW(), NOW())
                RETURNING assignment_id
            """), {
                'aid': self.agent_id,
                'itype': data.get('interview_type'),
                'sdate': data.get('scheduled_date'),
                'notes': data.get('notes', '')
            })
            
            assignment_id = result.scalar()
            item['assignment_id'] = assignment_id
            return True
            
        except Exception as e:
            logger.error(f"Interview setup sync error: {str(e)}")
            return False
    
    def _sync_survey_progress(self, conn, data: Dict, item: Dict) -> bool:
        """Sync survey progress"""
        try:
            conn.execute(text("""
                UPDATE agent_assignments
                SET completion_percentage = :progress,
                    last_activity = NOW(),
                    updated_at = NOW()
                WHERE assignment_id = :aid AND agent_id = :agent_id
            """), {
                'aid': data.get('assignment_id'),
                'agent_id': self.agent_id,
                'progress': data.get('completion_percentage', 0)
            })
            return True
        except Exception as e:
            logger.error(f"Survey progress sync error: {str(e)}")
            return False
    
    def _sync_generic_data(self, conn, data: Dict, item: Dict) -> bool:
        """Generic sync handler for unknown data types"""
        try:
            # Store in generic offline data table
            conn.execute(text("""
                INSERT INTO generic_offline_data 
                (agent_id, data_type, data_payload, metadata, created_at)
                VALUES (:aid, :dtype, :payload, :meta, NOW())
            """), {
                'aid': self.agent_id,
                'dtype': item['data_type'],
                'payload': json.dumps(data),
                'meta': json.dumps(item.get('metadata', {}))
            })
            return True
        except Exception as e:
            logger.error(f"Generic sync error: {str(e)}")
            return False
    
    def _create_sync_session(self) -> Optional[int]:
        """Create a new sync session with enhanced metadata"""
        try:
            with engine.begin() as conn:
                result = conn.execute(text("""
                    INSERT INTO sync_sessions 
                    (agent_id, device_id, connection_type, app_version, device_info)
                    VALUES (:aid, :did, :ctype, :version, :device_info)
                    RETURNING session_id
                """), {
                    'aid': self.agent_id,
                    'did': self.device_id,
                    'ctype': st.session_state.get('network_status', 'unknown'),
                    'version': '1.0.0',  # Would come from app config
                    'device_info': json.dumps({
                        'user_agent': 'Streamlit',
                        'screen_resolution': 'N/A',
                        'platform': 'Web'
                    })
                })
                
                session_id = result.scalar()
                logger.info(f"Created sync session: {session_id}")
                return session_id
        except Exception as e:
            logger.error(f"Session creation error: {str(e)}")
            return None
    
    def _complete_sync_session(self, results: Dict):
        """Complete sync session with detailed results"""
        if self.session_id:
            try:
                with engine.begin() as conn:
                    conn.execute(text("""
                        UPDATE sync_sessions
                        SET sync_completed_at = NOW(),
                            records_uploaded = :synced,
                            records_failed = :failed,
                            total_records = :total,
                            sync_duration = EXTRACT(EPOCH FROM (NOW() - sync_started_at)),
                            sync_status = :status,
                            error_details = :errors
                        WHERE session_id = :sid
                    """), {
                        'sid': self.session_id,
                        'synced': results['synced'],
                        'failed': results['failed'],
                        'total': results['synced'] + results['failed'],
                        'status': 'completed' if results['failed'] == 0 else 'partial',
                        'errors': json.dumps(results['errors'])
                    })
            except Exception as e:
                logger.error(f"Session completion error: {str(e)}")
    
    def _update_queue_after_sync(self, processed_queue: List[Dict]):
        """Update the queue after sync operation"""
        # Keep only pending and failed items
        st.session_state['offline_queue'] = [
            item for item in processed_queue
            if item['sync_status'] in ['pending', 'failed']
        ]
    
    def _generate_checksum(self, data: Dict) -> str:
        """Generate MD5 checksum for data integrity"""
        data_string = json.dumps(data, sort_keys=True, separators=(',', ':'))
        return hashlib.md5(data_string.encode()).hexdigest()
    
    # Public API methods
    def get_pending_count(self) -> int:
        """Get count of pending sync items"""
        return len([item for item in st.session_state['offline_queue'] 
                   if item['sync_status'] == 'pending'])
    
    def get_failed_count(self) -> int:
        """Get count of failed sync items"""
        return len([item for item in st.session_state['offline_queue'] 
                   if item['sync_status'] == 'failed'])
    
    def get_total_count(self) -> int:
        """Get total count of items in queue"""
        return len(st.session_state['offline_queue'])
    
    def get_queue_stats(self) -> Dict:
        """Get detailed queue statistics"""
        queue = st.session_state['offline_queue']
        return {
            'total': len(queue),
            'pending': len([item for item in queue if item['sync_status'] == 'pending']),
            'failed': len([item for item in queue if item['sync_status'] == 'failed']),
            'synced': len([item for item in queue if item['sync_status'] == 'synced']),
            'by_type': self._get_queue_stats_by_type(queue),
            'oldest_item': min([item['collected_at'] for item in queue]) if queue else None,
            'newest_item': max([item['collected_at'] for item in queue]) if queue else None
        }
    
    def _get_queue_stats_by_type(self, queue: List[Dict]) -> Dict:
        """Get queue statistics grouped by data type"""
        stats = {}
        for item in queue:
            data_type = item['data_type']
            if data_type not in stats:
                stats[data_type] = {'total': 0, 'pending': 0, 'failed': 0}
            
            stats[data_type]['total'] += 1
            if item['sync_status'] == 'pending':
                stats[data_type]['pending'] += 1
            elif item['sync_status'] == 'failed':
                stats[data_type]['failed'] += 1
        
        return stats
    
    def clear_synced_items(self):
        """Remove synced items from queue"""
        st.session_state['offline_queue'] = [
            item for item in st.session_state['offline_queue']
            if item['sync_status'] != 'synced'
        ]
    
    def retry_failed_items(self) -> Dict:
        """Retry syncing failed items with reset attempts"""
        for item in st.session_state['offline_queue']:
            if item['sync_status'] == 'failed' and item['sync_attempts'] < self.config['max_retries']:
                item['sync_status'] = 'pending'
                item['error_message'] = None
        
        return self.attempt_sync()
    
    def clear_all_items(self):
        """Clear all items from queue (use with caution)"""
        st.session_state['offline_queue'] = []
        logger.warning("All items cleared from offline queue")
    
    def export_queue_data(self) -> pd.DataFrame:
        """Export queue data as pandas DataFrame"""
        return pd.DataFrame(st.session_state['offline_queue'])
    
    def get_recent_errors(self, limit: int = 10) -> List[Dict]:
        """Get recent sync errors"""
        return st.session_state['sync_errors'][-limit:]
    
    def get_sync_history(self, days: int = 7) -> List[Dict]:
        """Get sync history from database"""
        try:
            with engine.connect() as conn:
                result = conn.execute(text("""
                    SELECT session_id, sync_started_at, sync_completed_at,
                           records_uploaded, records_failed, sync_status
                    FROM sync_sessions
                    WHERE agent_id = :aid 
                    AND sync_started_at >= NOW() - INTERVAL ':days days'
                    ORDER BY sync_started_at DESC
                """), {'aid': self.agent_id, 'days': days}).mappings().all()
                
                return [dict(row) for row in result]
        except Exception as e:
            logger.error(f"Error fetching sync history: {str(e)}")
            return []


# UI Components for Streamlit
def offline_data_collection_ui(agent: Dict) -> OfflineDataCollector:
    """
    Comprehensive UI component for offline data collection and sync management
    """
    
    collector = OfflineDataCollector(agent['agent_id'], agent.get('device_id', 'unknown'))
    
    st.markdown("### 📲 Offline Data Collection & Sync")
    
    # Network status and quick stats
    col_status = st.columns([2, 1, 1, 1])
    
    with col_status[0]:
        network_status = st.selectbox(
            "🌐 Network Status",
            ["online", "limited", "offline"],
            index=["online", "limited", "offline"].index(
                st.session_state.get('network_status', 'online')
            ),
            key="network_status_select"
        )
        st.session_state['network_status'] = network_status
        
        # Status indicator
        status_config = {
            'online': ('🟢 Online', 'success'),
            'limited': ('🟡 Limited', 'warning'),
            'offline': ('🔴 Offline', 'error')
        }
        status_text, status_color = status_config[network_status]
        st.markdown(f"**{status_text}**")
    
    with col_status[1]:
        pending = collector.get_pending_count()
        st.metric("📋 Pending", pending)
    
    with col_status[2]:
        failed = collector.get_failed_count()
        st.metric("❌ Failed", failed)
    
    with col_status[3]:
        total = collector.get_total_count()
        st.metric("📊 Total", total)
    
    # Sync actions
    st.markdown("---")
    st.markdown("#### 🔄 Sync Actions")
    
    col_sync = st.columns([1, 1, 1, 2])
    
    with col_sync[0]:
        if st.button("🔄 Sync All", type="primary", use_container_width=True,
                    disabled=st.session_state.get('sync_in_progress', False)):
            with st.spinner("Syncing all data..."):
                results = collector.attempt_sync(force=True)
                display_sync_results(results)
    
    with col_sync[1]:
        if st.button("🔄 Retry Failed", use_container_width=True,
                    disabled=collector.get_failed_count() == 0):
            with st.spinner("Retrying failed items..."):
                results = collector.retry_failed_items()
                display_sync_results(results)
    
    with col_sync[2]:
        if st.button("🧹 Clean Up", use_container_width=True,
                    disabled=collector.get_pending_count() > 0):
            collector.clear_synced_items()
            st.success("✅ Cleared synced items")
            st.rerun()
    
    with col_sync[3]:
        # Auto-sync toggle
        auto_sync = st.checkbox(
            "Enable Auto-Sync", 
            value=st.session_state.get('auto_sync_enabled', True),
            help="Automatically sync when network is available"
        )
        st.session_state['auto_sync_enabled'] = auto_sync
    
    # Emergency mode
    if network_status == 'offline' and collector.get_pending_count() > 0:
        st.markdown("---")
        st.warning("📶 You are currently offline")
        
        col_emergency = st.columns([3, 1])
        with col_emergency[0]:
            st.caption("Emergency sync will attempt to sync data even with limited connectivity")
        with col_emergency[1]:
            if st.button("🆘 Emergency Sync", type="secondary", use_container_width=True):
                st.session_state['emergency_sync'] = True
                with st.spinner("Attempting emergency sync..."):
                    results = collector.attempt_sync(force=True)
                    display_sync_results(results)
                st.session_state['emergency_sync'] = False
    
    # Queue details
    if collector.get_total_count() > 0:
        st.markdown("---")
        st.markdown("#### 📦 Offline Queue Details")
        
        # Queue statistics
        stats = collector.get_queue_stats()
        col_stats = st.columns(4)
        with col_stats[0]:
            st.metric("Total Items", stats['total'])
        with col_stats[1]:
            st.metric("Pending", stats['pending'])
        with col_stats[2]:
            st.metric("Failed", stats['failed'])
        with col_stats[3]:
            st.metric("Synced", stats['synced'])
        
        # Queue table
        queue_df = collector.export_queue_data()
        if not queue_df.empty:
            # Display relevant columns
            display_columns = ['data_type', 'sync_status', 'collected_at', 'sync_attempts', 'priority']
            if 'holder_id' in queue_df.columns:
                display_columns.insert(2, 'holder_id')
            
            available_columns = [col for col in display_columns if col in queue_df.columns]
            st.dataframe(queue_df[available_columns], use_container_width=True)
            
            # Queue actions
            col_queue = st.columns([1, 1, 1, 2])
            with col_queue[0]:
                if st.button("📥 Export CSV", use_container_width=True):
                    csv = queue_df.to_csv(index=False)
                    st.download_button(
                        "Download Queue CSV",
                        csv,
                        f"offline_queue_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                        "text/csv"
                    )
            
            with col_queue[1]:
                if st.button("📊 View Details", use_container_width=True):
                    st.session_state['show_queue_details'] = True
            
            with col_queue[2]:
                if st.button("🗑️ Clear All", use_container_width=True, type="secondary"):
                    if st.checkbox("Confirm clear all queue items"):
                        collector.clear_all_items()
                        st.success("✅ Queue cleared")
                        st.rerun()
    
    # Sync settings
    st.markdown("---")
    with st.expander("⚙️ Sync Settings & Configuration"):
        col_settings = st.columns(2)
        
        with col_settings[0]:
            st.markdown("**Sync Behavior**")
            st.number_input("Max Retry Attempts", 
                          value=collector.config['max_retries'], 
                          min_value=1, max_value=10, key="max_retries")
            st.number_input("Batch Size", 
                          value=collector.config['batch_size'], 
                          min_value=10, max_value=200, key="batch_size")
            st.number_input("Retry Delay (seconds)", 
                          value=collector.config['retry_delay'], 
                          min_value=1, max_value=60, key="retry_delay")
        
        with col_settings[1]:
            st.markdown("**Data Management**")
            checksum_enabled = st.checkbox("Enable Data Integrity Checks", 
                                         value=collector.config['checksum_validation'])
            st.checkbox("Compress Data", value=True)
            st.checkbox("Encrypt Sensitive Data", value=True)
            
            if st.button("💾 Save Settings", use_container_width=True):
                # Update collector config
                collector.config.update({
                    'max_retries': st.session_state.max_retries,
                    'batch_size': st.session_state.batch_size,
                    'retry_delay': st.session_state.retry_delay,
                    'checksum_validation': checksum_enabled
                })
                st.success("✅ Settings saved")
    
    # Sync history
    with st.expander("📈 Sync History & Analytics"):
        sync_history = collector.get_sync_history(days=7)
        if sync_history:
            history_df = pd.DataFrame(sync_history)
            st.dataframe(history_df, use_container_width=True)
            
            # Simple chart
            if len(history_df) > 1:
                chart_data = history_df[['sync_started_at', 'records_uploaded', 'records_failed']]
                chart_data['sync_started_at'] = pd.to_datetime(chart_data['sync_started_at'])
                chart_data = chart_data.set_index('sync_started_at')
                st.line_chart(chart_data[['records_uploaded', 'records_failed']])
        else:
            st.info("No sync history available")
    
    # Error log
    recent_errors = collector.get_recent_errors()
    if recent_errors:
        with st.expander("🚨 Recent Errors", expanded=False):
            for error in recent_errors[-5:]:  # Show last 5 errors
                st.error(f"{error['timestamp']}: {error['error']}")
    
    return collector


def display_sync_results(results: Dict):
    """Display sync results in a user-friendly way"""
    if results['success']:
        if results['synced'] > 0:
            st.success(f"✅ Successfully synced {results['synced']} records")
        else:
            st.info("📭 No records to sync")
    else:
        if results['errors']:
            st.error(f"❌ Sync failed with {len(results['errors'])} errors")
            for error in results['errors'][:3]:  # Show first 3 errors
                st.caption(f"• {error}")
        else:
            st.warning("⚠️ Sync completed with warnings")


# Helper functions for easy integration
def save_survey_data_offline(agent_id: int, device_id: str, data_type: str, 
                           data_payload: Dict, holder_id: Optional[int] = None,
                           metadata: Optional[Dict] = None) -> Dict:
    """
    High-level helper function to save survey data offline
    
    Args:
        agent_id: Agent ID
        device_id: Device identifier
        data_type: Type of data
        data_payload: Data to save
        holder_id: Optional holder ID
        metadata: Additional metadata
    
    Returns:
        dict: Queued item information
    """
    collector = OfflineDataCollector(agent_id, device_id)
    return collector.queue_data(data_type, data_payload, holder_id, metadata)


def get_sync_status(agent_id: int, device_id: str) -> Dict:
    """
    Get current sync status for an agent
    
    Args:
        agent_id: Agent ID
        device_id: Device identifier
    
    Returns:
        dict: Sync status information
    """
    collector = OfflineDataCollector(agent_id, device_id)
    return {
        'queue_stats': collector.get_queue_stats(),
        'network_status': st.session_state.get('network_status', 'unknown'),
        'auto_sync_enabled': st.session_state.get('auto_sync_enabled', True),
        'last_sync_attempt': st.session_state.get('last_sync_attempt'),
        'recent_errors': collector.get_recent_errors(5)
    }


# Utility function for background sync checking
def check_and_sync_pending_data(agent_id: int, device_id: str):
    """
    Background function to check and sync pending data
    This can be called periodically or on app startup
    """
    collector = OfflineDataCollector(agent_id, device_id)
    
    # Only sync if we have pending data and network is online
    if (collector.get_pending_count() > 0 and 
        st.session_state.get('network_status') == 'online' and
        st.session_state.get('auto_sync_enabled', True)):
        
        logger.info(f"Auto-syncing {collector.get_pending_count()} pending items")
        results = collector.attempt_sync()
        
        if not results['success']:
            logger.warning(f"Auto-sync completed with {results['failed']} failures")
        
        return results
    
    return None


# Initialize sync system on module load
def initialize_sync_system():
    """Initialize the sync system with default settings"""
    if 'sync_initialized' not in st.session_state:
        st.session_state.update({
            'offline_queue': [],
            'sync_sessions': {},
            'network_status': 'online',
            'auto_sync_enabled': True,
            'emergency_sync': False,
            'sync_in_progress': False,
            'sync_errors': [],
            'sync_initialized': True
        })
        logger.info("Sync system initialized")


# Initialize on import
initialize_sync_system()