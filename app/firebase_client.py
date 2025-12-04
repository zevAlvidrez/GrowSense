"""
Firebase client initialization and helper functions.
"""

import os
import json
from datetime import datetime, timedelta
import firebase_admin
from firebase_admin import credentials, firestore, storage, auth
from firebase_admin.exceptions import FirebaseError

# Global reference to Firestore client
_firestore_client = None
_storage_bucket = None


def initialize_firebase():
    """
    Initialize Firebase Admin SDK.
    Should be called once at application startup.
    """
    if firebase_admin._apps:
        # Already initialized
        return
    
    # Two methods to load credentials:
    # Method 1: From a JSON file path (recommended for local development)
    cred_path = os.environ.get('FIREBASE_SERVICE_ACCOUNT_PATH')
    
    # Method 2: From a JSON string (recommended for Render deployment)
    cred_json = os.environ.get('FIREBASE_SERVICE_ACCOUNT_JSON')
    
    if cred_json:
        # Parse JSON string from environment variable
        cred_dict = json.loads(cred_json)
        cred = credentials.Certificate(cred_dict)
        print("Firebase: Using credentials from FIREBASE_SERVICE_ACCOUNT_JSON env var")
    elif cred_path:
        # Load from file path
        cred = credentials.Certificate(cred_path)
        print(f"Firebase: Using credentials from file: {cred_path}")
    else:
        raise ValueError(
            "Firebase credentials not found. Set either "
            "FIREBASE_SERVICE_ACCOUNT_PATH or FIREBASE_SERVICE_ACCOUNT_JSON"
        )
    
    # Initialize with storage bucket (optional, for image uploads)
    storage_bucket = os.environ.get('FIREBASE_STORAGE_BUCKET')
    if storage_bucket:
        firebase_admin.initialize_app(cred, {
            'storageBucket': storage_bucket
        })
        print(f"Firebase: Initialized with storage bucket: {storage_bucket}")
    else:
        firebase_admin.initialize_app(cred)
        print("Firebase: Initialized without storage bucket")


def get_firestore():
    """
    Get Firestore client instance (singleton pattern).
    
    Returns:
        firestore.Client: Initialized Firestore client
    """
    global _firestore_client
    
    if _firestore_client is None:
        initialize_firebase()
        _firestore_client = firestore.client()
    
    return _firestore_client


def get_storage_bucket():
    """
    Get Firebase Storage bucket instance (singleton pattern).
    
    Returns:
        storage.Bucket: Initialized Storage bucket (or None if not configured)
    """
    global _storage_bucket
    
    if _storage_bucket is None:
        initialize_firebase()
        try:
            _storage_bucket = storage.bucket()
        except ValueError:
            # Storage bucket not configured
            print("Warning: Firebase Storage bucket not configured")
            return None
    
    return _storage_bucket


def verify_id_token(id_token):
    """
    Verify a Firebase ID token and return the decoded token.
    
    Args:
        id_token: Firebase ID token string from the client
        
    Returns:
        dict: Decoded token containing user information (uid, email, etc.)
        
    Raises:
        ValueError: If token is invalid or expired
    """
    initialize_firebase()
    try:
        decoded_token = auth.verify_id_token(id_token)
        return decoded_token
    except (ValueError, FirebaseError) as e:
        # Token is invalid, expired, or revoked
        # FirebaseError includes InvalidIdTokenError, ExpiredIdTokenError, etc.
        raise ValueError(f"Invalid ID token: {str(e)}")


def get_user_from_token(id_token):
    """
    Extract user information from a Firebase ID token.
    
    Args:
        id_token: Firebase ID token string from the client
        
    Returns:
        dict: User information with keys: uid, email, name (if available)
        
    Raises:
        ValueError: If token is invalid or expired
    """
    decoded_token = verify_id_token(id_token)
    
    user_info = {
        'uid': decoded_token.get('uid'),
        'email': decoded_token.get('email'),
        'name': decoded_token.get('name'),
        'email_verified': decoded_token.get('email_verified', False)
    }
    
    return user_info


# ========================================
# Device Registry Functions
# ========================================

def get_user_id_for_device(device_id):
    """
    Get the user_id associated with a device.
    Checks Firestore first, returns None if not found.
    
    Args:
        device_id: Device identifier
        
    Returns:
        str: User ID if device is registered, None otherwise
    """
    db = get_firestore()
    
    # Check reverse lookup: /devices/{deviceId}
    device_ref = db.collection('devices').document(device_id)
    device_doc = device_ref.get()
    
    if device_doc.exists:
        device_data = device_doc.to_dict()
        return device_data.get('user_id')
    
    return None


def device_exists(device_id):
    """
    Check if a device is registered in Firestore.
    
    Args:
        device_id: Device identifier
        
    Returns:
        bool: True if device exists in Firestore, False otherwise
    """
    db = get_firestore()
    device_ref = db.collection('devices').document(device_id)
    return device_ref.get().exists


def register_device_to_user(user_id, device_id, api_key, name=None):
    """
    Register a device to a user in Firestore.
    Creates entries in both /users/{userId}/devices/{deviceId} and /devices/{deviceId}.
    
    Args:
        user_id: Firebase user ID
        device_id: Device identifier
        api_key: API key for device authentication
        name: Optional user-friendly name for the device
        
    Returns:
        dict: Device information
    """
    db = get_firestore()
    from google.cloud.firestore_v1 import SERVER_TIMESTAMP
    
    now = datetime.utcnow()
    
    # Device data for user's collection
    device_data = {
        'api_key': api_key,
        'name': name or device_id,
        'created_at': SERVER_TIMESTAMP,
        'last_seen': None  # Will be updated when device uploads data
    }
    
    # Register in user's device collection: /users/{userId}/devices/{deviceId}
    user_device_ref = db.collection('users').document(user_id).collection('devices').document(device_id)
    user_device_ref.set(device_data)
    
    # Create reverse lookup: /devices/{deviceId} -> user_id and api_key
    reverse_lookup_data = {
        'user_id': user_id,
        'api_key': api_key,
        'registered_at': SERVER_TIMESTAMP
    }
    device_ref = db.collection('devices').document(device_id)
    device_ref.set(reverse_lookup_data)
    
    return {
        'device_id': device_id,
        'user_id': user_id,
        'name': name or device_id,
        'api_key': api_key  # Note: In production, you might not want to return this
    }


def get_user_devices(user_id):
    """
    Get all devices registered to a user.
    
    Args:
        user_id: Firebase user ID
        
    Returns:
        list: List of device dictionaries with device_id, name, api_key, created_at, last_seen
    """
    db = get_firestore()
    
    devices_ref = db.collection('users').document(user_id).collection('devices')
    devices = devices_ref.stream()
    
    result = []
    for device_doc in devices:
        device_data = device_doc.to_dict()
        device_data['device_id'] = device_doc.id
        
        # Convert timestamps to ISO strings if present
        if 'created_at' in device_data and device_data['created_at']:
            if hasattr(device_data['created_at'], 'isoformat'):
                device_data['created_at'] = device_data['created_at'].isoformat()
        if 'last_seen' in device_data and device_data['last_seen']:
            if hasattr(device_data['last_seen'], 'isoformat'):
                device_data['last_seen'] = device_data['last_seen'].isoformat()
        
        result.append(device_data)
    
    return result


def remove_device_from_user(user_id, device_id):
    """
    Remove a device from a user's collection.
    Also removes the reverse lookup entry.
    
    Args:
        user_id: Firebase user ID
        device_id: Device identifier
        
    Returns:
        bool: True if device was removed, False if device didn't exist or doesn't belong to user
    """
    db = get_firestore()
    
    # Verify device belongs to this user
    device_ref = db.collection('devices').document(device_id)
    device_doc = device_ref.get()
    
    if not device_doc.exists:
        return False
    
    device_data = device_doc.to_dict()
    if device_data.get('user_id') != user_id:
        return False  # Device doesn't belong to this user
    
    # Remove from user's device collection
    user_device_ref = db.collection('users').document(user_id).collection('devices').document(device_id)
    user_device_ref.delete()
    
    # Remove reverse lookup
    device_ref.delete()
    
    return True


def get_device_info(device_id, user_id=None):
    """
    Get device information. If user_id is provided, verifies ownership.
    
    Args:
        device_id: Device identifier
        user_id: Optional user ID to verify ownership
        
    Returns:
        dict: Device information if found and owned by user (if user_id provided), None otherwise
    """
    db = get_firestore()
    
    # Check reverse lookup first
    device_ref = db.collection('devices').document(device_id)
    device_doc = device_ref.get()
    
    if not device_doc.exists:
        return None
    
    device_data = device_doc.to_dict()
    
    # If user_id provided, verify ownership
    if user_id and device_data.get('user_id') != user_id:
        return None
    
    # Get full device info from user's collection
    owner_user_id = device_data.get('user_id')
    user_device_ref = db.collection('users').document(owner_user_id).collection('devices').document(device_id)
    user_device_doc = user_device_ref.get()
    
    if user_device_doc.exists:
        full_device_data = user_device_doc.to_dict()
        full_device_data['device_id'] = device_id
        full_device_data['user_id'] = owner_user_id
        
        # Convert timestamps
        if 'created_at' in full_device_data and full_device_data['created_at']:
            if hasattr(full_device_data['created_at'], 'isoformat'):
                full_device_data['created_at'] = full_device_data['created_at'].isoformat()
        if 'last_seen' in full_device_data and full_device_data['last_seen']:
            if hasattr(full_device_data['last_seen'], 'isoformat'):
                full_device_data['last_seen'] = full_device_data['last_seen'].isoformat()
        
        return full_device_data
    
    return None


def update_device_config(user_id, device_id, config_data):
    """
    Update device configuration settings.
    
    Args:
        user_id: Firebase user ID
        device_id: Device identifier
        config_data: Dictionary of configuration values to update
        
    Returns:
        bool: True if successful
    """
    db = get_firestore()
    
    # Reference to user's device document
    user_device_ref = db.collection('users').document(user_id).collection('devices').document(device_id)
    
    # Check if device exists
    if not user_device_ref.get().exists:
        return False
        
    # Update with new config
    user_device_ref.update(config_data)
    return True


def update_device_description(user_id, device_id, description):
    """
    Update device description field.
    
    Args:
        user_id: Firebase user ID
        device_id: Device identifier
        description: Description text (max 250 words / ~1250 chars)
        
    Returns:
        bool: True if successful, False if device not found or validation fails
    """
    # Validate description length (250 words max, ~1250 chars)
    if description and len(description) > 1500:
        return False
    
    db = get_firestore()
    
    # Reference to user's device document
    user_device_ref = db.collection('users').document(user_id).collection('devices').document(device_id)
    
    # Update description field (no existence check to save 1 read - will fail if not exists)
    try:
        user_device_ref.update({'description': description or ''})
        return True
    except Exception as e:
        print(f"Error updating device description: {e}")
        return False


def get_user_device_readings(user_id, device_ids=None, limit=None, per_device_limit=None):
    """
    Get sensor readings from user's devices.
    
    Args:
        user_id: Firebase user ID
        device_ids: Optional list of specific device IDs to query.
                   If None, queries all user's devices.
        limit: Total number of readings to return across all devices (default: 100, max: 1000)
        per_device_limit: Optional limit per device (useful when user has many devices)
        
    Returns:
        tuple: (readings: list, device_count: int)
               readings is list of dicts with device_id, device_name, and reading data
    """
    db = get_firestore()
    
    # Get list of user's devices
    if device_ids is None:
        # Get all user's devices
        user_devices = get_user_devices(user_id)
        device_ids = [device['device_id'] for device in user_devices]
        device_names = {device['device_id']: device.get('name', device['device_id']) 
                       for device in user_devices}
    else:
        # Verify ownership of specified devices
        user_devices = get_user_devices(user_id)
        user_device_ids = {device['device_id'] for device in user_devices}
        device_names = {device['device_id']: device.get('name', device['device_id']) 
                       for device in user_devices}
        
        # Filter to only devices that belong to user
        device_ids = [did for did in device_ids if did in user_device_ids]
    
    if not device_ids:
        return ([], 0)
    
    # Set defaults
    if limit is None:
        limit = 100
    limit = min(limit, 1000)  # Cap at 1000
    
    # FIX: Calculate per-device limit to distribute total limit evenly
    # This prevents querying `limit` docs from EACH device (N * limit reads)
    # Instead, we query `limit / N` docs from each device (limit reads total)
    if per_device_limit is None:
        per_device_limit = max(1, limit // len(device_ids))
    
    # Collect readings from all devices
    all_readings = []
    
    for device_id in device_ids:
        try:
            device_name = device_names.get(device_id, device_id)
            device_readings = []
            
            # Query user-centric location: /users/{userId}/devices/{deviceId}/readings/
            try:
                readings_ref = db.collection('users').document(user_id).collection('devices').document(device_id).collection('readings')
                query = readings_ref.order_by('server_timestamp', direction='DESCENDING')
                query = query.limit(per_device_limit)  # Always use per_device_limit now
                
                docs = query.stream()
                for doc in docs:
                    reading = doc.to_dict()
                    reading['id'] = doc.id
                    reading['device_id'] = device_id
                    reading['device_name'] = device_name
                    
                    # Convert server_timestamp to string if present
                    if 'server_timestamp' in reading and reading['server_timestamp']:
                        if hasattr(reading['server_timestamp'], 'isoformat'):
                            reading['server_timestamp'] = reading['server_timestamp'].isoformat()
                    
                    device_readings.append(reading)
            except Exception as e:
                # Device might not have readings yet, that's okay
                print(f"Info: No readings found for device {device_id}: {str(e)}")
            
            all_readings.extend(device_readings)
        except Exception as e:
            # If a device has no readings or error, continue with other devices
            print(f"Warning: Error querying device {device_id}: {str(e)}")
            continue
    
    # Sort all readings by server_timestamp (newest first)
    # Handle cases where server_timestamp might be missing
    def get_timestamp(reading):
        if 'server_timestamp' in reading and reading['server_timestamp']:
            try:
                from datetime import datetime
                if isinstance(reading['server_timestamp'], str):
                    return datetime.fromisoformat(reading['server_timestamp'].replace('Z', '+00:00'))
                return reading['server_timestamp']
            except:
                pass
        # Fallback to timestamp field
        if 'timestamp' in reading and reading['timestamp']:
            try:
                from datetime import datetime
                if isinstance(reading['timestamp'], str):
                    return datetime.fromisoformat(reading['timestamp'].replace('Z', '+00:00'))
            except:
                pass
        # Last resort: use current time (will sort to end)
        from datetime import datetime
        return datetime.min
    
    all_readings.sort(key=get_timestamp, reverse=True)
    
    # Apply total limit
    all_readings = all_readings[:limit]
    
    return (all_readings, len(device_ids))


def get_user_device_readings_since(user_id, since_timestamp, limit=100):
    """
    Get sensor readings from user's devices that are newer than since_timestamp.
    Used for incremental fetching to reduce Firestore reads.
    
    Args:
        user_id: Firebase user ID
        since_timestamp: ISO timestamp string - only return readings after this time
        limit: Maximum total number of readings to return (default: 100)
        
    Returns:
        tuple: (readings: list, device_count: int)
    """
    db = get_firestore()
    from datetime import datetime
    
    # Parse the since timestamp
    try:
        if isinstance(since_timestamp, str):
            # Handle ISO format with 'Z' suffix
            since_timestamp = since_timestamp.replace('Z', '+00:00')
            since_dt = datetime.fromisoformat(since_timestamp)
        else:
            since_dt = since_timestamp
    except Exception as e:
        print(f"Error parsing since_timestamp: {e}")
        # Fall back to normal fetch if timestamp is invalid
        return get_user_device_readings(user_id, limit=limit)
    
    # Get user's devices
    user_devices = get_user_devices(user_id)
    device_ids = [device['device_id'] for device in user_devices]
    device_names = {device['device_id']: device.get('name', device['device_id']) 
                   for device in user_devices}
    
    if not device_ids:
        return ([], 0)
    
    all_readings = []
    
    for device_id in device_ids:
        try:
            device_name = device_names.get(device_id, device_id)
            
            # Query only readings newer than since_timestamp
            readings_ref = db.collection('users').document(user_id)\
                             .collection('devices').document(device_id)\
                             .collection('readings')
            
            # Filter by server_timestamp > since_dt
            query = readings_ref.where('server_timestamp', '>', since_dt)\
                               .order_by('server_timestamp', direction='DESCENDING')\
                               .limit(limit)
            
            docs = query.stream()
            
            for doc in docs:
                reading = doc.to_dict()
                reading['id'] = doc.id
                reading['device_id'] = device_id
                reading['device_name'] = device_name
                
                # Convert server_timestamp to string if present
                if 'server_timestamp' in reading and reading['server_timestamp']:
                    if hasattr(reading['server_timestamp'], 'isoformat'):
                        reading['server_timestamp'] = reading['server_timestamp'].isoformat()
                
                all_readings.append(reading)
                
        except Exception as e:
            print(f"Error querying device {device_id} for incremental fetch: {str(e)}")
            continue
    
    # Sort by server_timestamp (newest first)
    def get_timestamp(reading):
        if 'server_timestamp' in reading and reading['server_timestamp']:
            try:
                from datetime import datetime
                if isinstance(reading['server_timestamp'], str):
                    return datetime.fromisoformat(reading['server_timestamp'].replace('Z', '+00:00'))
                return reading['server_timestamp']
            except:
                pass
        return datetime.min
    
    all_readings.sort(key=get_timestamp, reverse=True)
    
    # Apply total limit
    all_readings = all_readings[:limit]
    
    return (all_readings, len(device_ids))


def get_recent_and_historic_readings(user_id, recent_limit=120, historic_limit=120):
    """
    Get both recent and sampled historic readings for a user.
    Minimizes database reads while providing two views of the data.
    
    Strategy:
    1. Recent: Fetch last N readings per device (High Resolution)
    2. Historic: Fetch sampled readings (Low Resolution) by estimating time steps
       to approximate "index 60, 120, 180..."
    
    Args:
        user_id: Firebase user ID
        recent_limit: Number of recent readings per device
        historic_limit: Number of historic samples per device
        
    Returns:
        dict: {
            'recent': [readings...],
            'historic': [readings...]
        }
    """
    db = get_firestore()
    
    # Get user's devices
    user_devices = get_user_devices(user_id)
    if not user_devices:
        return {'recent': [], 'historic': []}
        
    recent_readings = []
    historic_readings = []
    
    for device in user_devices:
        device_id = device['device_id']
        device_name = device.get('name', device_id)
        
        # 1. Fetch Recent Data
        # ====================
        try:
            readings_ref = db.collection('users').document(user_id)\
                            .collection('devices').document(device_id)\
                            .collection('readings')
            
            query = readings_ref.order_by('server_timestamp', direction='DESCENDING').limit(recent_limit)
            docs = list(query.stream())
            
            device_recent = []
            for doc in docs:
                reading = doc.to_dict()
                reading['id'] = doc.id
                reading['device_id'] = device_id
                reading['device_name'] = device_name
                
                if 'server_timestamp' in reading and hasattr(reading['server_timestamp'], 'isoformat'):
                    reading['server_timestamp'] = reading['server_timestamp'].isoformat()
                    
                device_recent.append(reading)
            
            recent_readings.extend(device_recent)
            
            # 2. Fetch Historic Data (Smart Sampling)
            # ==========================================
            # Goal: Get up to historic_limit samples distributed across the available history.
            # Strategy:
            # 1. Get the oldest reading timestamp (1 read).
            # 2. Get the newest reading timestamp (already have it from recent data).
            # 3. Calculate the time range and step size.
            # 4. Issue point queries for N samples distributed over that range.
            
            # This ensures we get data across the *actual* history, whether it's 1 day or 1 year.
            
            device_historic = []
            
            # Only fetch historic if we have recent data (device is active)
            if device_recent and 'server_timestamp' in device_recent[0]:
                try:
                    # Get newest time
                    newest_ts_str = device_recent[0]['server_timestamp']
                    newest_time = datetime.fromisoformat(newest_ts_str.replace('Z', '+00:00')).replace(tzinfo=None)
                    
                    # Get oldest time (1 read)
                    oldest_query = readings_ref.order_by('server_timestamp', direction='ASCENDING').limit(1)
                    oldest_docs = list(oldest_query.stream())
                    
                    if oldest_docs:
                        oldest_doc = oldest_docs[0].to_dict()
                        if 'server_timestamp' in oldest_doc and oldest_doc['server_timestamp']:
                            if hasattr(oldest_doc['server_timestamp'], 'isoformat'):
                                # It's a datetime object
                                oldest_time = oldest_doc['server_timestamp'].replace(tzinfo=None)
                            elif isinstance(oldest_doc['server_timestamp'], str):
                                # It's a string
                                oldest_time = datetime.fromisoformat(oldest_doc['server_timestamp'].replace('Z', '+00:00')).replace(tzinfo=None)
                            else:
                                oldest_time = None
                        else:
                            oldest_time = None
                    else:
                        oldest_time = None
                    
                    if oldest_time and newest_time and oldest_time < newest_time:
                        time_range = newest_time - oldest_time
                        total_seconds = time_range.total_seconds()
                        
                        # We want historic_limit samples.
                        # Step size in seconds.
                        # User requested up to 120 historic points.
                        # 4 devices * 120 = 480 reads. This is acceptable for a one-time load.
                        
                        target_samples = min(historic_limit, 120) 
                        step_seconds = total_seconds / target_samples
                        
                        if step_seconds > 0:
                            for i in range(1, target_samples + 1):
                                # Step backwards from newest (or forwards from oldest)
                                # Let's step backwards to prioritize recent-ish history if we cut off
                                query_time = newest_time - timedelta(seconds=step_seconds * i)
                                
                                # Don't query if it's overlap with "recent" (approx)
                                # But simpler to just query and deduplicate later if needed
                                
                                try:
                                    # Find reading closest to this time (just before)
                                    h_query = readings_ref.where('server_timestamp', '<=', query_time)\
                                                        .order_by('server_timestamp', direction='DESCENDING')\
                                                        .limit(1)
                                    
                                    h_docs = list(h_query.stream())
                                    if h_docs:
                                        doc = h_docs[0]
                                        reading = doc.to_dict()
                                        reading['id'] = doc.id
                                        reading['device_id'] = device_id
                                        reading['device_name'] = device_name
                                        
                                        if 'server_timestamp' in reading and hasattr(reading['server_timestamp'], 'isoformat'):
                                            reading['server_timestamp'] = reading['server_timestamp'].isoformat()
                                        
                                        device_historic.append(reading)
                                except Exception as e:
                                    # Ignore individual failures
                                    continue
                                    
                except Exception as e:
                    print(f"Error in historic fetch logic for {device_id}: {e}")
            
            historic_readings.extend(device_historic)
            
        except Exception as e:
            print(f"Error processing device {device_id}: {e}")
            continue

    # Sort results
    def sort_key(r):
        ts = r.get('server_timestamp') or r.get('timestamp')
        return ts if ts else ''
        
    recent_readings.sort(key=sort_key, reverse=True)
    historic_readings.sort(key=sort_key, reverse=True)
    
    return {
        'recent': recent_readings,
        'historic': historic_readings
    }


def get_sparse_historical_readings(user_id, hours=168, since_timestamp=None):
    """
    [DEPRECATED] - Kept for backward compatibility but routes.py should switch to get_recent_and_historic_readings.
    """
    return []


def write_reading(reading_doc, device_id, user_id):
    """
    Write a reading to the user-centric Firestore location.
    
    Location: /users/{userId}/devices/{deviceId}/readings/{readingId}
    
    Args:
        reading_doc: Dictionary containing reading data
        device_id: Device identifier
        user_id: User ID (required)
        
    Returns:
        DocumentReference: Reference to the created reading document
    """
    if not user_id:
        raise ValueError("user_id is required for write_reading")
    
    db = get_firestore()
    
    # Write to user-centric location
    reading_ref = db.collection('users').document(user_id).collection('devices').document(device_id).collection('readings').document()
    reading_ref.set(reading_doc)
    
    return reading_ref


def prepare_data_for_gemini(user_id, time_range_hours=24, limit_per_device=50):
    """
    Prepare user's device data for Gemini analysis.
    Gets recent readings and calculates summaries for each device.
    
    Args:
        user_id: Firebase user ID
        time_range_hours: Number of hours of data to include (default: 24)
        limit_per_device: Maximum readings per device to analyze (default: 50)
        
    Returns:
        dict: Formatted data structure ready for Gemini analysis
    """
    from datetime import datetime, timedelta
    
    # Get user's devices
    devices = get_user_devices(user_id)
    
    if not devices:
        return {
            "user_id": user_id,
            "device_count": 0,
            "devices": [],
            "overall_summary": {
                "total_readings": 0,
                "time_range": f"last_{time_range_hours}_hours"
            }
        }
    
    # Get recent readings for all devices
    readings, device_count = get_user_device_readings(
        user_id,
        device_ids=None,  # All devices
        limit=limit_per_device * len(devices),  # Total limit
        per_device_limit=limit_per_device
    )
    
    # Organize readings by device
    readings_by_device = {}
    for reading in readings:
        device_id = reading.get('device_id')
        if device_id not in readings_by_device:
            readings_by_device[device_id] = []
        readings_by_device[device_id].append(reading)
    
    # Build formatted data structure
    formatted_devices = []
    all_temperatures = []
    all_humidities = []
    all_soil_moistures = []
    all_lights = []
    all_uv_lights = []
    
    for device in devices:
        device_id = device['device_id']
        device_readings = readings_by_device.get(device_id, [])
        
        # Skip devices with no readings (they've been deleted or are inactive)
        if len(device_readings) == 0:
            continue
        
        # Calculate summary statistics
        temperatures = [r.get('temperature') for r in device_readings if r.get('temperature') is not None]
        humidities = [r.get('humidity') for r in device_readings if r.get('humidity') is not None]
        soil_moistures = [r.get('soil_moisture') for r in device_readings if r.get('soil_moisture') is not None]
        lights = [r.get('light') for r in device_readings if r.get('light') is not None]
        
        # UV light - check both top-level field and raw_json
        uv_lights = []
        for r in device_readings:
            if r.get('uv_light') is not None:
                uv_lights.append(r.get('uv_light'))
            elif r.get('raw_json') and r.get('raw_json').get('uv_light') is not None:
                uv_lights.append(r.get('raw_json').get('uv_light'))
        
        # Calculate averages
        avg_temp = sum(temperatures) / len(temperatures) if temperatures else None
        avg_humidity = sum(humidities) / len(humidities) if humidities else None
        avg_soil = sum(soil_moistures) / len(soil_moistures) if soil_moistures else None
        avg_light = sum(lights) / len(lights) if lights else None
        avg_uv = sum(uv_lights) / len(uv_lights) if uv_lights else None
        
        # Collect for overall summary
        all_temperatures.extend(temperatures)
        all_humidities.extend(humidities)
        all_soil_moistures.extend(soil_moistures)
        all_lights.extend(lights)
        all_uv_lights.extend(uv_lights)
        
        # Prepare device data (remove internal fields like _source)
        clean_readings = []
        for reading in device_readings:
            # Get UV from either top-level or raw_json
            uv_value = reading.get('uv_light')
            if uv_value is None and reading.get('raw_json'):
                uv_value = reading.get('raw_json').get('uv_light')
            
            clean_reading = {
                'timestamp': reading.get('timestamp') or reading.get('server_timestamp'),
                'temperature': reading.get('temperature'),
                'humidity': reading.get('humidity'),
                'light': reading.get('light'),
                'soil_moisture': reading.get('soil_moisture'),
                'uv_light': uv_value
            }
            # Remove None values
            clean_reading = {k: v for k, v in clean_reading.items() if v is not None}
            clean_readings.append(clean_reading)
        
        device_data = {
            'device_id': device_id,
            'name': device.get('name', device_id),
            'last_seen': device.get('last_seen'),
            'recent_readings': clean_readings,
            'summary': {
                'reading_count': len(device_readings),
                'avg_temperature': round(avg_temp, 2) if avg_temp else None,
                'avg_humidity': round(avg_humidity, 2) if avg_humidity else None,
                'avg_light': round(avg_light, 0) if avg_light else None,
                'avg_soil_moisture': round(avg_soil, 2) if avg_soil else None,
                'avg_uv_light': round(avg_uv, 2) if avg_uv else None,
                'min_temperature': round(min(temperatures), 2) if temperatures else None,
                'max_temperature': round(max(temperatures), 2) if temperatures else None,
                'min_humidity': round(min(humidities), 2) if humidities else None,
                'max_humidity': round(max(humidities), 2) if humidities else None,
                'min_soil_moisture': round(min(soil_moistures), 2) if soil_moistures else None,
                'max_soil_moisture': round(max(soil_moistures), 2) if soil_moistures else None,
                'min_uv_light': round(min(uv_lights), 2) if uv_lights else None,
                'max_uv_light': round(max(uv_lights), 2) if uv_lights else None
            }
        }
        formatted_devices.append(device_data)
    
    # Overall summary
    overall_summary = {
        'total_readings': len(readings),
        'time_range': f'last_{time_range_hours}_hours',
        'avg_temperature': round(sum(all_temperatures) / len(all_temperatures), 2) if all_temperatures else None,
        'avg_humidity': round(sum(all_humidities) / len(all_humidities), 2) if all_humidities else None,
        'avg_soil_moisture': round(sum(all_soil_moistures) / len(all_soil_moistures), 2) if all_soil_moistures else None,
        'avg_light': round(sum(all_lights) / len(all_lights), 0) if all_lights else None,
        'avg_uv_light': round(sum(all_uv_lights) / len(all_uv_lights), 2) if all_uv_lights else None
    }
    
    return {
        'user_id': user_id,
        'device_count': len(formatted_devices),
        'devices': formatted_devices,
        'overall_summary': overall_summary
    }
