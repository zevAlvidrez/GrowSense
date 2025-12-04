"""
Flask routes for GrowSense API endpoints.
"""

import os
import json
from datetime import datetime
from functools import wraps
from flask import Blueprint, request, jsonify, render_template, g
from app.firebase_client import (
    get_firestore, 
    get_user_from_token,
    get_user_id_for_device,
    register_device_to_user,
    get_user_devices,
    remove_device_from_user,
    get_device_info,
    update_device_config,
    get_user_device_readings,
    get_user_device_readings_since,
    write_reading,
    prepare_data_for_gemini,
    get_recent_and_historic_readings,
    get_incremental_recent_readings
)
from app.gemini_client import get_gemini_advice
from app.cache import readings_cache
from google.cloud.firestore_v1 import SERVER_TIMESTAMP

# Global Cache for API Key Validation and Device Config
# Structure: {device_id: {'api_key': '...', 'user_id': '...', 'timestamp': 1234567890}}
_api_key_cache = {}
# Structure: {device_id: {'target_interval': 60, 'timestamp': 1234567890}}
_device_config_cache = {}
CACHE_DURATION_SECONDS = 300  # 5 minutes cache

bp = Blueprint('main', __name__)

# Load device API keys from JSON file
def load_device_keys():
    """Load device API keys from JSON file specified in environment."""
    keys_path = os.environ.get('DEVICE_KEYS_PATH', './device_keys.json')
    try:
        with open(keys_path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Warning: Device keys file not found at {keys_path}")
        return {}
    except json.JSONDecodeError:
        print(f"Error: Invalid JSON in device keys file at {keys_path}")
        return {}


def validate_api_key(device_id, api_key):
    """
    Validate that the provided API key matches the device_id.
    Checks Cache first, then Firestore, then falls back to device_keys.json.
    """
    current_time = datetime.utcnow().timestamp()
    
    # Check cache first
    if device_id in _api_key_cache:
        cached = _api_key_cache[device_id]
        if current_time - cached['timestamp'] < CACHE_DURATION_SECONDS:
            # Cache hit
            if cached['api_key'] == api_key:
                return (True, cached['user_id'])
            else:
                # Invalid key in cache
                return (False, None)
    
    db = get_firestore()
    
    # First, check Firestore (reverse lookup: /devices/{deviceId})
    device_ref = db.collection('devices').document(device_id)
    device_doc = device_ref.get()
    
    if device_doc.exists:
        device_data = device_doc.to_dict()
        stored_key = device_data.get('api_key')
        user_id = device_data.get('user_id')
        
        # Update cache
        _api_key_cache[device_id] = {
            'api_key': stored_key,
            'user_id': user_id,
            'timestamp': current_time
        }
        
        if stored_key == api_key:
            return (True, user_id)
        else:
            return (False, None)
    
    # Fallback to JSON file for backward compatibility
    device_keys = load_device_keys()
    expected_key = device_keys.get(device_id)
    
    if not expected_key:
        return (False, None)
    
    # Handle both old format (string) and potential new format (dict)
    if isinstance(expected_key, dict):
        # New format: {"api_key": "...", "user_id": "..."}
        if expected_key.get('api_key') == api_key:
            return (True, expected_key.get('user_id'))
    elif expected_key == api_key:
        # Old format: just the api_key string
        return (True, None)
    
    return (False, None)


def require_auth(f):
    """
    Decorator to require Firebase authentication for a route.
    
    Expects Authorization header: "Bearer <firebase_id_token>"
    Sets g.user with user info (uid, email, etc.) if authenticated.
    
    Returns 401 if token is missing or invalid.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth_header = request.headers.get('Authorization')
        
        if not auth_header:
            return jsonify({"error": "Missing Authorization header"}), 401
        
        # Extract token from "Bearer <token>"
        try:
            scheme, token = auth_header.split(' ', 1)
            if scheme.lower() != 'bearer':
                return jsonify({"error": "Invalid authorization scheme. Use 'Bearer <token>'"}), 401
        except ValueError:
            return jsonify({"error": "Invalid Authorization header format. Use 'Bearer <token>'"}), 401
        
        # Verify token and get user info
        try:
            user_info = get_user_from_token(token)
            # Store user info in Flask's g object for use in route handler
            g.user = user_info
        except ValueError as e:
            return jsonify({"error": "Invalid or expired token", "details": str(e)}), 401
        
        return f(*args, **kwargs)
    
    return decorated_function


@bp.route('/')
def index():
    """Serve the dashboard HTML page."""
    # Get Firebase web config from environment (for frontend Auth)
    # Format: FIREBASE_WEB_CONFIG='{"apiKey":"...","authDomain":"...","projectId":"...","storageBucket":"...","messagingSenderId":"...","appId":"..."}'
    firebase_config_json = os.environ.get('FIREBASE_WEB_CONFIG', '{}')
    try:
        firebase_config = json.loads(firebase_config_json) if firebase_config_json else {}
    except json.JSONDecodeError:
        print("Warning: Invalid FIREBASE_WEB_CONFIG JSON, using empty config")
        firebase_config = {}
    
    return render_template('index.html', firebase_config=firebase_config)


@bp.route('/firebase-config')
def firebase_config():
    """
    Get Firebase web configuration for frontend.
    Returns the Firebase web app config needed for client-side authentication.
    Useful for debugging - check if config is loaded correctly.
    """
    firebase_config_json = os.environ.get('FIREBASE_WEB_CONFIG', '{}')
    
    # Strip any whitespace and handle empty strings
    if firebase_config_json:
        firebase_config_json = firebase_config_json.strip()
    
    # Debug logging
    print(f"DEBUG: FIREBASE_WEB_CONFIG length: {len(firebase_config_json) if firebase_config_json else 0}")
    print(f"DEBUG: First 100 chars: {repr(firebase_config_json[:100]) if firebase_config_json else 'empty'}")
    
    try:
        if not firebase_config_json or firebase_config_json == '{}':
            return jsonify({
                "config": {},
                "has_config": False,
                "message": "Config missing - set FIREBASE_WEB_CONFIG environment variable"
            }), 200
        
        firebase_config = json.loads(firebase_config_json)
        has_config = bool(firebase_config and firebase_config.get('apiKey'))
        return jsonify({
            "config": firebase_config,
            "has_config": has_config,
            "message": "Config loaded successfully" if has_config else "Config missing - set FIREBASE_WEB_CONFIG environment variable"
        }), 200
    except json.JSONDecodeError as e:
        print(f"ERROR parsing FIREBASE_WEB_CONFIG: {e}")
        print(f"ERROR at position: {e.pos}")
        print(f"ERROR context: {repr(firebase_config_json[max(0, e.pos-30):e.pos+30]) if firebase_config_json else 'empty'}")
        return jsonify({
            "error": "Invalid Firebase config JSON",
            "details": str(e),
            "position": e.pos,
            "raw_length": len(firebase_config_json) if firebase_config_json else 0,
            "raw_preview": firebase_config_json[:150] if firebase_config_json else "empty"
        }), 500


@bp.route('/upload_data', methods=['POST'])
def upload_data():
    """
    Accept sensor data from ESP32 devices.
    
    Expected JSON payload:
    {
        "device_id": "esp32_device_001",
        "api_key": "your-secret-key",
        "timestamp": "2024-10-22T12:34:56Z" or 1234567890,
        "temperature": 23.5,
        "humidity": 65.2,
        "light": 450,
        "soil_moisture": 42.1
    }
    """
    try:
        # Parse JSON body
        data = request.get_json()
        
        if not data:
            return jsonify({"error": "Invalid JSON or empty body"}), 400
        
        # Validate required fields
        device_id = data.get('device_id')
        api_key = data.get('api_key')
        
        if not device_id or not api_key:
            return jsonify({"error": "Missing device_id or api_key"}), 400
        
        # Validate API key (returns tuple: is_valid, user_id)
        is_valid, user_id = validate_api_key(device_id, api_key)
        if not is_valid:
            return jsonify({"error": "Invalid device_id or api_key"}), 401
        
        # Process timestamp
        timestamp = data.get('timestamp')
        if timestamp:
            # If timestamp is a number (epoch seconds), convert to ISO string
            if isinstance(timestamp, (int, float)):
                timestamp = datetime.utcfromtimestamp(timestamp).isoformat() + 'Z'
        else:
            # Use server timestamp if not provided
            timestamp = datetime.utcnow().isoformat() + 'Z'
        
        # Prepare document for Firestore
        reading_doc = {
            'timestamp': timestamp,
            'temperature': data.get('temperature'),
            'humidity': data.get('humidity'),
            'light': data.get('light'),
            'soil_moisture': data.get('soil_moisture'),
            'uv_light': data.get('uv_light'),  # UV Index from GUVA-S12SD sensor
            'raw_json': data,  # Store full payload for debugging
            'server_timestamp': SERVER_TIMESTAMP  # Firestore server timestamp
        }
        
        # Remove None values
        reading_doc = {k: v for k, v in reading_doc.items() if v is not None}
        
        # Write to user-centric location
        if not user_id:
            return jsonify({"error": "Device not registered to a user. Please register device first."}), 400
        
        reading_ref = write_reading(reading_doc, device_id, user_id)
        
        # Update server-side cache with new reading
        try:
            # Add reading ID for cache tracking
            reading_doc['id'] = reading_ref.id
            reading_doc['device_id'] = device_id
            reading_doc['device_name'] = device_id  # Will be updated from device metadata if available
            readings_cache.update_reading(user_id, device_id, reading_doc)
        except Exception as e:
            # Cache update is non-critical
            print(f"Warning: Failed to update cache for user {user_id}, device {device_id}: {str(e)}")
        
        # Update device's last_seen timestamp and check config
        try:
            db = get_firestore()
            user_device_ref = db.collection('users').document(user_id).collection('devices').document(device_id)
            
            current_time = datetime.utcnow().timestamp()
            should_update_last_seen = True
            device_data = None
            
            # Check config cache to reduce reads and writes
            if device_id in _device_config_cache:
                cached = _device_config_cache[device_id]
                # If we cached it less than 60s ago, skip write
                if current_time - cached['timestamp'] < 60:
                    should_update_last_seen = False
                
                # If cache is still valid (5 mins), use it for config
                if current_time - cached['timestamp'] < CACHE_DURATION_SECONDS:
                    device_data = cached['config']
            
            # Update last_seen if needed (throttled to once per minute)
            if should_update_last_seen:
                user_device_ref.update({'last_seen': SERVER_TIMESTAMP})
            
            # Fetch config if not in cache
            if device_data is None:
                device_doc = user_device_ref.get()
                if device_doc.exists:
                    device_data = device_doc.to_dict()
                    # Update cache
                    _device_config_cache[device_id] = {
                        'config': device_data,
                        'timestamp': current_time
                    }
            
            response_data = {
                "success": True,
                "message": "Data uploaded successfully",
                "device_id": device_id,
                "reading_id": reading_ref.id,
                "timestamp": timestamp
            }
            
            if device_data and 'target_interval' in device_data:
                response_data['sleep_duration'] = device_data['target_interval']
            
            return jsonify(response_data), 201
            
        except Exception as e:
            # Non-critical: last_seen update failure shouldn't fail the upload
            print(f"Warning: Failed to update last_seen or fetch config for device {device_id}: {str(e)}")
            # Fallback response
            return jsonify({
                "success": True,
                "message": "Data uploaded successfully (with warnings)",
                "device_id": device_id,
                "reading_id": reading_ref.id,
                "timestamp": timestamp
            }), 201
        
    except Exception as e:
        print(f"Error in upload_data: {str(e)}")
        return jsonify({"error": "Internal server error", "details": str(e)}), 500


@bp.route('/get_data', methods=['GET'])
def get_data():
    """
    [DEPRECATED] Retrieve sensor readings for a specific device.
    
    This endpoint is deprecated. Use /user_data or /user_data/<device_id> instead.
    This endpoint reads from the old /devices/ location and may not return data
    for devices registered to users.
    
    Query parameters:
        device_id: Device identifier (required)
        limit: Number of readings to return (default: 100, max: 1000)
    
    Returns:
        JSON array of readings sorted by timestamp (newest first)
    """
    try:
        device_id = request.args.get('device_id')
        
        if not device_id:
            return jsonify({"error": "Missing device_id parameter"}), 400
        
        # Parse limit parameter
        try:
            limit = int(request.args.get('limit', 100))
            limit = min(limit, 1000)  # Cap at 1000 readings
        except ValueError:
            limit = 100
        
        # Query Firestore
        db = get_firestore()
        readings_ref = db.collection('devices').document(device_id).collection('readings')
        
        # Order by server_timestamp descending, limit results
        query = readings_ref.order_by('server_timestamp', direction='DESCENDING').limit(limit)
        docs = query.stream()
        
        # Convert to list of dictionaries
        readings = []
        for doc in docs:
            reading = doc.to_dict()
            reading['id'] = doc.id  # Include document ID
            
            # Remove raw_json from response to keep it clean (optional)
            # reading.pop('raw_json', None)
            
            # Convert server_timestamp to string if present
            if 'server_timestamp' in reading:
                reading['server_timestamp'] = reading['server_timestamp'].isoformat()
            
            readings.append(reading)
        
        return jsonify({
            "success": True,
            "device_id": device_id,
            "count": len(readings),
            "readings": readings
        }), 200
        
    except Exception as e:
        print(f"Error in get_data: {str(e)}")
        return jsonify({"error": "Internal server error", "details": str(e)}), 500


@bp.route('/health', methods=['GET'])
def health():
    """Health check endpoint for monitoring services."""
    return jsonify({
        "status": "healthy",
        "service": "GrowSense API",
        "timestamp": datetime.utcnow().isoformat() + 'Z'
    }), 200


# ========================================
# Authentication Endpoints
# ========================================

@bp.route('/auth/login', methods=['POST'])
def auth_login():
    """
    Verify a Firebase ID token and return user information.
    
    Expected JSON payload:
    {
        "id_token": "firebase-id-token-string"
    }
    
    Returns:
        JSON with user information (uid, email, etc.)
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({"error": "Invalid JSON or empty body"}), 400
        
        id_token = data.get('id_token')
        
        if not id_token:
            return jsonify({"error": "Missing id_token"}), 400
        
        # Verify token and get user info
        try:
            user_info = get_user_from_token(id_token)
        except ValueError as e:
            return jsonify({"error": "Invalid or expired token", "details": str(e)}), 401
        
        return jsonify({
            "success": True,
            "user": user_info
        }), 200
        
    except Exception as e:
        print(f"Error in auth_login: {str(e)}")
        return jsonify({"error": "Internal server error", "details": str(e)}), 500


@bp.route('/auth/me', methods=['GET'])
@require_auth
def auth_me():
    """
    Get current authenticated user information.
    
    Requires Authorization header: "Bearer <firebase_id_token>"
    
    Returns:
        JSON with user information (uid, email, etc.)
    """
    try:
        # User info is already set in g.user by require_auth decorator
        return jsonify({
            "success": True,
            "user": g.user
        }), 200
        
    except Exception as e:
        print(f"Error in auth_me: {str(e)}")
        return jsonify({"error": "Internal server error", "details": str(e)}), 500


@bp.route('/auth/logout', methods=['POST'])
@require_auth
def auth_logout():
    """
    Logout endpoint (placeholder for session cleanup if needed).
    
    Note: Firebase tokens are stateless, so this is mainly for
    client-side cleanup. The token will naturally expire.
    
    Requires Authorization header: "Bearer <firebase_id_token>"
    
    Returns:
        JSON confirmation
    """
    try:
        # In a stateless token system, logout is handled client-side
        # This endpoint exists for consistency and future session management
        return jsonify({
            "success": True,
            "message": "Logged out successfully"
        }), 200
        
    except Exception as e:
        print(f"Error in auth_logout: {str(e)}")
        return jsonify({"error": "Internal server error", "details": str(e)}), 500


# ========================================
# Device Management Endpoints
# ========================================

@bp.route('/devices/register', methods=['POST'])
@require_auth
def register_device():
    """
    Register a device to the authenticated user.
    
    Requires Authorization header: "Bearer <firebase_id_token>"
    
    Expected JSON payload:
    {
        "device_id": "esp32_device_001",
        "api_key": "your-secret-key",
        "name": "Optional friendly name"
    }
    
    Returns:
        JSON with device information
    """
    try:
        user_id = g.user['uid']
        data = request.get_json()
        
        if not data:
            return jsonify({"error": "Invalid JSON or empty body"}), 400
        
        device_id = data.get('device_id')
        api_key = data.get('api_key')
        name = data.get('name')
        
        if not device_id or not api_key:
            return jsonify({"error": "Missing device_id or api_key"}), 400
        
        # Check if device is already registered to another user
        existing_user_id = get_user_id_for_device(device_id)
        if existing_user_id and existing_user_id != user_id:
            return jsonify({
                "error": "Device already registered to another user",
                "device_id": device_id
            }), 409  # Conflict
        
        # Register device
        device_info = register_device_to_user(user_id, device_id, api_key, name)
        
        return jsonify({
            "success": True,
            "message": "Device registered successfully",
            "device": device_info
        }), 201
        
    except Exception as e:
        print(f"Error in register_device: {str(e)}")
        return jsonify({"error": "Internal server error", "details": str(e)}), 500


@bp.route('/devices', methods=['GET'])
@require_auth
def list_devices():
    """
    Get all devices registered to the authenticated user.
    
    Requires Authorization header: "Bearer <firebase_id_token>"
    
    Returns:
        JSON array of devices
    """
    try:
        user_id = g.user['uid']
        devices = get_user_devices(user_id)
        
        return jsonify({
            "success": True,
            "count": len(devices),
            "devices": devices
        }), 200
        
    except Exception as e:
        print(f"Error in list_devices: {str(e)}")
        return jsonify({"error": "Internal server error", "details": str(e)}), 500


@bp.route('/devices/<device_id>', methods=['GET'])
@require_auth
def get_device(device_id):
    """
    Get information about a specific device.
    Verifies that the device belongs to the authenticated user.
    
    Requires Authorization header: "Bearer <firebase_id_token>"
    
    Args:
        device_id: Device identifier (from URL path)
    
    Returns:
        JSON with device information
    """
    try:
        user_id = g.user['uid']
        device_info = get_device_info(device_id, user_id)
        
        if not device_info:
            return jsonify({
                "error": "Device not found or does not belong to user",
                "device_id": device_id
            }), 404
        
        return jsonify({
            "success": True,
            "device": device_info
        }), 200
        
    except Exception as e:
        print(f"Error in get_device: {str(e)}")
        return jsonify({"error": "Internal server error", "details": str(e)}), 500


@bp.route('/devices/<device_id>/config', methods=['POST'])
@require_auth
def update_config(device_id):
    """
    Update configuration settings for a specific device.
    Verifies ownership before updating.
    
    Requires Authorization header: "Bearer <firebase_id_token>"
    
    Expected JSON payload:
    {
        "target_interval": 60  # Seconds
    }
    
    Returns:
        JSON confirmation
    """
    try:
        user_id = g.user['uid']
        data = request.get_json()
        
        if not data:
            return jsonify({"error": "Invalid JSON or empty body"}), 400
            
        # Verify device belongs to user
        device_info = get_device_info(device_id, user_id)
        if not device_info:
            return jsonify({
                "error": "Device not found or does not belong to user",
                "device_id": device_id
            }), 404
            
        # Update config
        success = update_device_config(user_id, device_id, data)
        
        if not success:
            return jsonify({"error": "Failed to update configuration"}), 500
            
        # Invalidate config cache so next upload picks it up
        if device_id in _device_config_cache:
            del _device_config_cache[device_id]
            
        return jsonify({
            "success": True,
            "message": "Configuration updated successfully",
            "device_id": device_id,
            "config": data
        }), 200
        
    except Exception as e:
        print(f"Error in update_config: {str(e)}")
        return jsonify({"error": "Internal server error", "details": str(e)}), 500


@bp.route('/devices/<device_id>/description', methods=['POST'])
@require_auth
def update_description(device_id):
    """
    Update the description for a specific device.
    Verifies ownership before updating.
    
    Requires Authorization header: "Bearer <firebase_id_token>"
    
    Expected JSON payload:
    {
        "description": "My tomato plant by the window..."
    }
    
    Returns:
        JSON confirmation
    """
    try:
        user_id = g.user['uid']
        data = request.get_json()
        
        if data is None:
            return jsonify({"error": "Invalid JSON or empty body"}), 400
        
        description = data.get('description', '')
        
        # Validate description length (250 words max, ~1250 chars, with buffer)
        if len(description) > 1500:
            return jsonify({
                "error": "Description too long",
                "max_length": 1500,
                "current_length": len(description)
            }), 400
        
        # Verify device belongs to user and update
        from app.firebase_client import update_device_description
        success = update_device_description(user_id, device_id, description)
        
        if not success:
            return jsonify({
                "error": "Device not found or does not belong to user",
                "device_id": device_id
            }), 404
        
        return jsonify({
            "success": True,
            "message": "Description updated successfully",
            "device_id": device_id,
            "description": description
        }), 200
        
    except Exception as e:
        print(f"Error in update_description: {str(e)}")
        return jsonify({"error": "Internal server error", "details": str(e)}), 500


@bp.route('/devices/<device_id>', methods=['DELETE'])
@require_auth
def delete_device(device_id):
    """
    Remove a device from the authenticated user's collection.
    Verifies ownership before deletion.
    
    Requires Authorization header: "Bearer <firebase_id_token>"
    
    Args:
        device_id: Device identifier (from URL path)
    
    Returns:
        JSON confirmation
    """
    try:
        user_id = g.user['uid']
        success = remove_device_from_user(user_id, device_id)
        
        if not success:
            return jsonify({
                "error": "Device not found or does not belong to user",
                "device_id": device_id
            }), 404
        
        return jsonify({
            "success": True,
            "message": "Device removed successfully",
            "device_id": device_id
        }), 200
        
    except Exception as e:
        print(f"Error in delete_device: {str(e)}")
        return jsonify({"error": "Internal server error", "details": str(e)}), 500


# ========================================
# User Data Endpoints
# ========================================

@bp.route('/user_data', methods=['GET'])
@require_auth
def get_user_data():
    """
    Get sensor readings from all devices belonging to the authenticated user.
    
    Two modes:
    1. Initial load (no query params): Returns both recent (120) and historic (120) data
    2. Incremental update (with since= param): Returns only NEW recent readings since timestamp
    
    Query params:
        since: ISO timestamp - if provided, only fetch NEW recent readings after this time
               and do NOT refetch historic data
    
    Requires Authorization header: "Bearer <firebase_id_token>"
    """
    try:
        user_id = g.user['uid']
        since_timestamp = request.args.get('since')
        
        # INCREMENTAL MODE: Client already has data, just fetch new readings
        if since_timestamp:
            print(f"[Incremental] Fetching new readings since {since_timestamp}")
            new_readings = get_incremental_recent_readings(user_id, since_timestamp)
            
            return jsonify({
                "success": True,
                "user_id": user_id,
                "mode": "incremental",
                "data": {
                    "recent": new_readings,
                    "historic": []  # Never refetch historic
                }
            }), 200
        
        # INITIAL LOAD MODE: Fetch both recent and historic
        print(f"[Initial Load] Fetching full recent + historic data")
        data_modes = get_recent_and_historic_readings(user_id, recent_limit=120, historic_limit=120)
        
        return jsonify({
            "success": True,
            "user_id": user_id,
            "mode": "initial",
            "data": data_modes
        }), 200
        
    except Exception as e:
        print(f"Error in get_user_data: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": "Internal server error", "details": str(e)}), 500


def flatten_cached_readings(readings_by_device, limit=100):
    """
    [DEPRECATED] Flatten readings_by_device dictionary into a single sorted list.
    Kept for backward compatibility if needed internally.
    """
    all_readings = []
    for device_id, data in readings_by_device.items():
        if isinstance(data, dict):
            all_readings.extend(data.get('recent', []))
        else:
            all_readings.extend(data)
    
    all_readings.sort(key=lambda r: r.get('server_timestamp', ''), reverse=True)
    return all_readings[:limit]


def organize_readings_by_device(readings):
    """
    Organize a flat list of readings into a dictionary keyed by device_id.
    
    Args:
        readings: List of reading dictionaries (each with device_id field)
        
    Returns:
        Dict mapping device_id to list of readings
    """
    readings_by_device = {}
    for reading in readings:
        device_id = reading.get('device_id')
        if device_id:
            if device_id not in readings_by_device:
                readings_by_device[device_id] = []
            readings_by_device[device_id].append(reading)
    
    return readings_by_device


def prepare_data_for_gemini_from_cache(cached_data, user_id, time_range_hours=24, limit_per_device=50):
    """
    Prepare user's device data for Gemini analysis FROM CACHE (not database).
    This function uses cached data from local storage instead of querying Firestore.
    
    IMPORTANT: Only uses recent readings (not historic). Samples 30 readings per device
    from recent data (every 4th reading if ~120 available, with fallback logic).
    Also extracts analysis history from cache if available.
    
    Args:
        cached_data: Cached data dictionary from readings_cache.get()
        user_id: Firebase user ID
        time_range_hours: Number of hours of data to include (default: 24, for summary only)
        limit_per_device: Maximum readings per device to include (default: 50, ignored - uses 30)
        
    Returns:
        dict: Formatted data structure ready for Gemini analysis with raw recent readings and analysis_history
    """
    from datetime import datetime, timedelta
    
    devices = cached_data.get('devices', [])
    readings_by_device = cached_data.get('readings_by_device', {})
    analysis_history = cached_data.get('analysis_history', [])  # Extract from cache
    
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
    
    # Target: 30 readings per device (sampled from recent only)
    TARGET_READINGS_PER_DEVICE = 30
    
    # Build formatted data structure with raw recent readings
    formatted_devices = []
    all_temperatures = []
    all_humidities = []
    all_soil_moistures = []
    all_lights = []
    all_uv_lights = []
    
    for device in devices:
        device_id = device['device_id']
        device_readings_raw = readings_by_device.get(device_id, [])
        
        # Handle new cache structure (dict with recent/historic)
        # IMPORTANT: Only use recent readings, ignore historic
        if isinstance(device_readings_raw, dict):
            recent_readings = device_readings_raw.get('recent', [])
        else:
            # Legacy list structure - assume all are recent
            recent_readings = device_readings_raw if isinstance(device_readings_raw, list) else []
        
        if len(recent_readings) == 0:
            continue
        
        # Sample readings: target 30 readings per device
        # If we have ~120 readings, sample every 4th (120/30 = 4)
        # Build in checks for different reading counts
        if len(recent_readings) > TARGET_READINGS_PER_DEVICE:
            # Calculate step size to get approximately TARGET_READINGS_PER_DEVICE readings
            step = max(1, len(recent_readings) // TARGET_READINGS_PER_DEVICE)
            sampled_readings = recent_readings[::step][:TARGET_READINGS_PER_DEVICE]
            
            # Ensure we include the most recent reading (index 0) and try to include the oldest
            if sampled_readings and sampled_readings[0] != recent_readings[0]:
                sampled_readings.insert(0, recent_readings[0])
            if len(recent_readings) > 1 and sampled_readings[-1] != recent_readings[-1]:
                sampled_readings.append(recent_readings[-1])
            
            # Limit to TARGET_READINGS_PER_DEVICE
            sampled_readings = sampled_readings[:TARGET_READINGS_PER_DEVICE]
        else:
            # Use all readings if we have <= 30
            sampled_readings = recent_readings
        
        # Prepare clean readings with timestamps preserved
        clean_readings = []
        for reading in sampled_readings:
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
            # Remove None values but keep all fields that have values
            clean_reading = {k: v for k, v in clean_reading.items() if v is not None}
            clean_readings.append(clean_reading)
        
        # Calculate summary statistics for internal use (not emphasized in prompt)
        temperatures = [r.get('temperature') for r in clean_readings if r.get('temperature') is not None]
        humidities = [r.get('humidity') for r in clean_readings if r.get('humidity') is not None]
        soil_moistures = [r.get('soil_moisture') for r in clean_readings if r.get('soil_moisture') is not None]
        lights = [r.get('light') for r in clean_readings if r.get('light') is not None]
        uv_lights = [r.get('uv_light') for r in clean_readings if r.get('uv_light') is not None]
        
        # Collect for overall summary
        all_temperatures.extend(temperatures)
        all_humidities.extend(humidities)
        all_soil_moistures.extend(soil_moistures)
        all_lights.extend(lights)
        all_uv_lights.extend(uv_lights)
        
        device_data = {
            'device_id': device_id,
            'name': device.get('name', device_id),
            'description': device.get('description'),  # Include description for prompt
            'last_seen': device.get('last_seen'),
            'recent_readings': clean_readings,  # Full array of 30 sampled readings with timestamps
            'summary': {
                'reading_count': len(clean_readings),
                'avg_temperature': round(sum(temperatures) / len(temperatures), 2) if temperatures else None,
                'avg_humidity': round(sum(humidities) / len(humidities), 2) if humidities else None,
                'avg_light': round(sum(lights) / len(lights), 0) if lights else None,
                'avg_soil_moisture': round(sum(soil_moistures) / len(soil_moistures), 2) if soil_moistures else None,
                'avg_uv_light': round(sum(uv_lights) / len(uv_lights), 2) if uv_lights else None,
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
    
    # Overall summary (for metadata, not emphasized in prompt)
    overall_summary = {
        'total_readings': sum(len(d.get('recent_readings', [])) for d in formatted_devices),
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
        'overall_summary': overall_summary,
        'analysis_history': analysis_history  # Include analysis history from cache
    }


def extract_devices_from_readings(readings):
    """
    Extract minimal device info from readings to avoid extra DB call.
    Each reading already contains device_id and device_name.
    
    Args:
        readings: List of reading dictionaries
        
    Returns:
        List of device dictionaries with device_id and name
    """
    devices_seen = {}
    for reading in readings:
        device_id = reading.get('device_id')
        if device_id and device_id not in devices_seen:
            devices_seen[device_id] = {
                'device_id': device_id,
                'name': reading.get('device_name', device_id)
            }
    return list(devices_seen.values())


@bp.route('/user_data/historical', methods=['GET'])
@require_auth
def get_historical_data():
    """
    Get sparse historical readings (one per hour) for trend visualization.
    Used by frontend to populate localStorage cache for week/all-time views.
    
    Requires Authorization header: "Bearer <firebase_id_token>"
    
    Query parameters:
        hours: Number of hours of history to fetch (default: 168 = 1 week, max: 336 = 2 weeks)
        since: ISO timestamp - only fetch readings after this time (for partial/gap-fill fetches)
    
    Returns:
        JSON with one reading per hour per device (first reading of each hour)
    """
    try:
        user_id = g.user['uid']
        
        # Parse hours parameter
        try:
            hours = int(request.args.get('hours', 168))
            hours = min(hours, 336)  # Cap at 2 weeks
        except ValueError:
            hours = 168
        
        # Parse since parameter (for partial fetches to fill gaps)
        since_timestamp = request.args.get('since')
        
        # Get sparse historical readings
        from app.firebase_client import get_sparse_historical_readings
        readings = get_sparse_historical_readings(user_id, hours, since_timestamp=since_timestamp)
        
        return jsonify({
            "success": True,
            "user_id": user_id,
            "hours_requested": hours,
            "since": since_timestamp,
            "total_readings": len(readings),
            "readings": readings
        }), 200
        
    except Exception as e:
        print(f"Error in get_historical_data: {str(e)}")
        return jsonify({"error": "Internal server error", "details": str(e)}), 500


@bp.route('/user_data/<device_id>', methods=['GET'])
@require_auth
def get_user_device_data(device_id):
    """
    Get sensor readings from a specific device belonging to the authenticated user.
    Verifies ownership before returning data.
    
    Requires Authorization header: "Bearer <firebase_id_token>"
    
    Query parameters:
        limit: Number of readings to return (default: 100, max: 1000)
    
    Args:
        device_id: Device identifier (from URL path)
    
    Returns:
        JSON with readings from the specified device
    """
    try:
        user_id = g.user['uid']
        
        # Verify device belongs to user
        device_info = get_device_info(device_id, user_id)
        if not device_info:
            return jsonify({
                "error": "Device not found or does not belong to user",
                "device_id": device_id
            }), 404
        
        # Parse query parameters
        try:
            limit = int(request.args.get('limit', 100))
            limit = min(limit, 1000)  # Cap at 1000
        except ValueError:
            limit = 100
        
        # Get readings for this specific device
        readings, device_count = get_user_device_readings(
            user_id,
            device_ids=[device_id],
            limit=limit
        )
        
        return jsonify({
            "success": True,
            "user_id": user_id,
            "device_id": device_id,
            "device_name": device_info.get('name', device_id),
            "total_readings": len(readings),
            "readings": readings
        }), 200
        
    except Exception as e:
        print(f"Error in get_user_device_data: {str(e)}")
        return jsonify({"error": "Internal server error", "details": str(e)}), 500


# ========================================
# Gemini Advice Endpoints
# ========================================

@bp.route('/user_advice', methods=['GET'])
@require_auth
def get_user_advice():
    """
    Get plant care advice from Gemini AI based on user's sensor data.
    
    IMPORTANT: This endpoint requires cached data to be available. Cache must be populated
    by loading user data first (via /user_data endpoint). This ensures no database
    queries are made during advice generation.
    
    Requires Authorization header: "Bearer <firebase_id_token>"
    
    Query parameters:
        time_range_hours: Number of hours of data to analyze (default: 24, max: 168)
        limit_per_device: Maximum readings per device to include (default: 50, max: 200)
    
    Returns:
        JSON with structured advice including:
        - overall_advice: General assessment
        - device_advice: Device-specific recommendations
        - insights: Key observations
    
    Errors:
        - 400: No cached data available (user must refresh dashboard first)
    """
    try:
        user_id = g.user['uid']
        
        # Parse query parameters
        try:
            time_range_hours = int(request.args.get('time_range_hours', 24))
            time_range_hours = min(time_range_hours, 168)  # Cap at 7 days
        except ValueError:
            time_range_hours = 24
        
        try:
            limit_per_device = int(request.args.get('limit_per_device', 50))
            limit_per_device = min(limit_per_device, 200)  # Cap at 200
        except ValueError:
            limit_per_device = 50
        
        # IMPORTANT: Cache-only operation - no database fallback
        cached_data = readings_cache.get(user_id)
        
        if not cached_data:
            # Cache is empty - user must load data first
            print(f"[Cache] Cache miss for Gemini advice (user: {user_id}) - returning error")
            return jsonify({
                "error": "No cached data available. Please refresh your dashboard to load data first."
            }), 400
        
        # Ensure analysis history is in cache (fetch if missing, but not if empty list already cached)
        if 'analysis_history' not in cached_data:
            # Key is missing - fetch from Firestore and update cache (even if empty)
            from app.gemini_client import load_user_analysis_history
            analysis_history = load_user_analysis_history(user_id, limit=3)
            # Cache the result (even if empty list) to avoid repeated queries
            readings_cache.update_analysis_history(user_id, analysis_history)
            cached_data['analysis_history'] = analysis_history
            if analysis_history:
                print(f"[Cache] Fetched and cached {len(analysis_history)} analysis history entries for user {user_id}")
            else:
                print(f"[Cache] Fetched analysis history for user {user_id} - no history found (cached empty list)")
        
        # Use cached data (cache-only, no database queries after initial fetch)
        print(f"[Cache] Using cached data for Gemini advice (user: {user_id})")
        formatted_data = prepare_data_for_gemini_from_cache(
            cached_data,
            user_id,
            time_range_hours=time_range_hours,
            limit_per_device=limit_per_device
        )
        
        # Validate that we have data to analyze
        if not formatted_data or formatted_data.get('device_count', 0) == 0:
            return jsonify({
                "error": "No device data available in cache. Please refresh your dashboard to load data first."
            }), 400
        
        # Get advice from Gemini
        advice = get_gemini_advice(formatted_data)
        
        # Save new analysis result to Firestore and update cache
        try:
            from app.gemini_client import save_analysis_result
            save_analysis_result(advice, user_id)
            
            # Update cache with new analysis (keep only last 3)
            current_history = cached_data.get('analysis_history', [])
            # Add timestamp to advice for cache (matches Firestore format)
            advice_with_timestamp = advice.copy()
            advice_with_timestamp['analysis_timestamp'] = datetime.utcnow().isoformat() + 'Z'
            # Add new advice to history (most recent at end, oldest to newest order)
            updated_history = current_history + [advice_with_timestamp]
            # Keep only last 3 (drops oldest if we had 3 already)
            updated_history = updated_history[-3:]
            readings_cache.update_analysis_history(user_id, updated_history)
            print(f"[Cache] Updated analysis history in cache for user {user_id} (now {len(updated_history)} entries)")
        except Exception as e:
            # Non-critical: saving history shouldn't fail the request
            print(f"Warning: Failed to save/update analysis history: {str(e)}")
        
        return jsonify({
            "success": True,
            "user_id": user_id,
            "timestamp": datetime.utcnow().isoformat() + 'Z',
            "data_summary": {
                "device_count": formatted_data.get('device_count', 0),
                "readings_analyzed": formatted_data.get('overall_summary', {}).get('total_readings', 0),
                "time_range": formatted_data.get('overall_summary', {}).get('time_range', 'unknown')
            },
            "advice": advice
        }), 200
        
    except Exception as e:
        print(f"Error in get_user_advice: {str(e)}")
        return jsonify({"error": "Internal server error", "details": str(e)}), 500

