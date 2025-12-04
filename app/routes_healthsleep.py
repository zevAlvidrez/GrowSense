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
    prepare_data_for_gemini
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


# ========================================
# Adaptive Sleep Duration Functions
# ========================================

def calculate_adaptive_sleep_duration(health_score):
    """
    Calculate sleep duration in seconds based on plant health score.
    
    Lower health = more frequent monitoring
    Higher health = less frequent monitoring (saves battery)
    
    Health Score Mapping:
    - 0-2 (Critical): 30 seconds - very frequent monitoring needed
    - 3-4 (Poor): 45-60 seconds - frequent monitoring
    - 5-6 (Fair): 120-180 seconds (2-3 minutes) - regular monitoring
    - 7-8 (Good): 300-600 seconds (5-10 minutes) - less urgent
    - 9-10 (Excellent): 900-1800 seconds (15-30 minutes) - plant thriving
    
    Args:
        health_score: Plant health score (0-10)
    
    Returns:
        int: Sleep duration in seconds
    """
    if health_score is None:
        return 60  # Default 1 minute if no score
    
    # Clamp score to valid range
    score = max(0, min(10, health_score))
    
    if score <= 2:
        # Critical health: 30 seconds (very frequent monitoring)
        return 30
    elif score <= 4:
        # Poor health: 45-60 seconds
        return int(45 + (score - 2) * 7.5)
    elif score <= 6:
        # Fair health: 60-180 seconds (1-3 minutes)
        return int(60 + (score - 4) * 60)
    elif score <= 8:
        # Good health: 180-600 seconds (3-10 minutes)
        return int(180 + (score - 6) * 210)
    else:
        # Excellent health: 600-1800 seconds (10-30 minutes)
        return int(600 + (score - 8) * 600)


def get_device_sleep_duration(device_id, user_id):
    """
    Get the appropriate sleep duration for a device.
    Uses adaptive health-based duration if enabled, otherwise uses manual setting.
    
    Args:
        device_id: Device identifier
        user_id: User ID who owns the device
    
    Returns:
        tuple: (sleep_duration_seconds, source_string, health_score_or_none)
    """
    try:
        db = get_firestore()
        
        # Get device config from user's device collection
        device_ref = db.collection('users').document(user_id).collection('devices').document(device_id)
        device_doc = device_ref.get()
        
        if not device_doc.exists:
            return (60, 'default', None)  # Default 1 minute
        
        device_data = device_doc.to_dict()
        
        # Check if adaptive mode is enabled
        adaptive_enabled = device_data.get('adaptive_sleep_enabled', False)
        
        if adaptive_enabled:
            # Use health-based calculation
            health_score = device_data.get('plant_health_score')
            
            if health_score is not None:
                sleep_duration = calculate_adaptive_sleep_duration(health_score)
                print(f"Device {device_id}: Adaptive mode - Health score {health_score} → Sleep {sleep_duration}s")
                return (sleep_duration, 'adaptive', health_score)
            else:
                # No health score yet, use default but indicate adaptive mode
                print(f"Device {device_id}: Adaptive mode enabled but no health score yet")
                return (60, 'adaptive_no_score', None)
        
        # Fall back to manual setting
        manual_interval = device_data.get('target_interval')
        if manual_interval:
            print(f"Device {device_id}: Manual mode - Sleep {manual_interval}s")
            return (int(manual_interval), 'manual', device_data.get('plant_health_score'))
        
        return (60, 'default', device_data.get('plant_health_score'))  # Default 1 minute
        
    except Exception as e:
        print(f"Error getting sleep duration for {device_id}: {e}")
        return (60, 'error', None)


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
    
    Returns adaptive or manual sleep_duration based on device configuration.
    
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
    
    Response includes:
    {
        "success": true,
        "sleep_duration": 60,  // seconds - adaptive or manual
        "sleep_source": "adaptive",  // "adaptive", "manual", or "default"
        "plant_health_score": 7.5  // if available
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
        
        # Update device's last_seen timestamp
        try:
            db = get_firestore()
            user_device_ref = db.collection('users').document(user_id).collection('devices').document(device_id)
            
            current_time = datetime.utcnow().timestamp()
            should_update_last_seen = True
            
            # Check config cache to reduce reads and writes
            if device_id in _device_config_cache:
                cached = _device_config_cache[device_id]
                # If we cached it less than 60s ago, skip write
                if current_time - cached['timestamp'] < 60:
                    should_update_last_seen = False
            
            # Update last_seen if needed (throttled to once per minute)
            if should_update_last_seen:
                user_device_ref.update({'last_seen': SERVER_TIMESTAMP})
                # Update cache timestamp
                if device_id not in _device_config_cache:
                    _device_config_cache[device_id] = {'config': {}, 'timestamp': current_time}
                else:
                    _device_config_cache[device_id]['timestamp'] = current_time
            
            # Get adaptive or manual sleep duration
            sleep_duration, sleep_source, health_score = get_device_sleep_duration(device_id, user_id)
            
            response_data = {
                "success": True,
                "message": "Data uploaded successfully",
                "device_id": device_id,
                "reading_id": reading_ref.id,
                "timestamp": timestamp,
                "sleep_duration": sleep_duration,
                "sleep_source": sleep_source  # 'adaptive', 'manual', 'adaptive_no_score', or 'default'
            }
            
            # Include health score if available (for debugging/display)
            if health_score is not None:
                response_data['plant_health_score'] = health_score
            
            return jsonify(response_data), 201
            
        except Exception as e:
            # Non-critical: last_seen update failure shouldn't fail the upload
            print(f"Warning: Failed to update last_seen or fetch config for device {device_id}: {str(e)}")
            # Fallback response with default sleep
            return jsonify({
                "success": True,
                "message": "Data uploaded successfully (with warnings)",
                "device_id": device_id,
                "reading_id": reading_ref.id,
                "timestamp": timestamp,
                "sleep_duration": 60,
                "sleep_source": "default"
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
        "target_interval": 60,           # Manual sleep interval in seconds
        "adaptive_sleep_enabled": true   # Enable health-based adaptive sleep
    }
    
    Returns:
        JSON confirmation with calculated sleep duration if adaptive mode
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
        
        # Validate and filter allowed fields
        allowed_fields = ['target_interval', 'adaptive_sleep_enabled', 'name']
        config_update = {}
        
        for key in allowed_fields:
            if key in data:
                config_update[key] = data[key]
        
        # Validate target_interval range if provided
        if 'target_interval' in config_update:
            interval = config_update['target_interval']
            if not isinstance(interval, (int, float)) or interval < 15 or interval > 3600:
                return jsonify({"error": "target_interval must be between 15 and 3600 seconds"}), 400
            config_update['target_interval'] = int(interval)
        
        # Validate adaptive_sleep_enabled if provided
        if 'adaptive_sleep_enabled' in config_update:
            config_update['adaptive_sleep_enabled'] = bool(config_update['adaptive_sleep_enabled'])
            
        # Update config
        success = update_device_config(user_id, device_id, config_update)
        
        if not success:
            return jsonify({"error": "Failed to update configuration"}), 500
            
        # Invalidate config cache so next upload picks it up
        if device_id in _device_config_cache:
            del _device_config_cache[device_id]
        
        # Prepare response
        response_data = {
            "success": True,
            "message": "Configuration updated successfully",
            "device_id": device_id,
            "config": config_update
        }
        
        # If adaptive mode was enabled/changed, calculate what sleep would be
        if config_update.get('adaptive_sleep_enabled'):
            health_score = device_info.get('plant_health_score')
            if health_score is not None:
                calculated_sleep = calculate_adaptive_sleep_duration(health_score)
                response_data['calculated_adaptive_sleep'] = calculated_sleep
                response_data['current_health_score'] = health_score
            else:
                response_data['note'] = "Adaptive mode enabled. Sleep duration will be calculated after next health analysis."
            
        return jsonify(response_data), 200
        
    except Exception as e:
        print(f"Error in update_config: {str(e)}")
        return jsonify({"error": "Internal server error", "details": str(e)}), 500


@bp.route('/devices/<device_id>/health_score', methods=['POST'])
@require_auth
def update_health_score(device_id):
    """
    Manually update the plant health score for a device.
    This score is used for adaptive sleep calculation.
    
    Requires Authorization header: "Bearer <firebase_id_token>"
    
    Expected JSON payload:
    {
        "health_score": 7.5  # Score from 0-10
    }
    
    Returns:
        JSON with updated score and calculated sleep duration
    """
    try:
        user_id = g.user['uid']
        data = request.get_json()
        
        if not data:
            return jsonify({"error": "Invalid JSON or empty body"}), 400
        
        health_score = data.get('health_score')
        
        if health_score is None:
            return jsonify({"error": "Missing health_score"}), 400
        
        # Validate score range
        try:
            health_score = float(health_score)
            if health_score < 0 or health_score > 10:
                return jsonify({"error": "health_score must be between 0 and 10"}), 400
        except (TypeError, ValueError):
            return jsonify({"error": "health_score must be a number"}), 400
        
        # Verify device belongs to user
        device_info = get_device_info(device_id, user_id)
        if not device_info:
            return jsonify({
                "error": "Device not found or does not belong to user",
                "device_id": device_id
            }), 404
        
        # Update device with health score
        db = get_firestore()
        device_ref = db.collection('users').document(user_id).collection('devices').document(device_id)
        device_ref.update({
            'plant_health_score': health_score,
            'health_score_updated_at': SERVER_TIMESTAMP
        })
        
        # Also update the global devices collection for cross-reference
        global_device_ref = db.collection('devices').document(device_id)
        if global_device_ref.get().exists:
            global_device_ref.update({
                'plant_health_score': health_score,
                'health_score_updated_at': SERVER_TIMESTAMP
            })
        
        # Invalidate config cache
        if device_id in _device_config_cache:
            del _device_config_cache[device_id]
        
        # Calculate what sleep duration this would result in
        calculated_sleep = calculate_adaptive_sleep_duration(health_score)
        
        return jsonify({
            "success": True,
            "device_id": device_id,
            "health_score": health_score,
            "calculated_sleep_duration": calculated_sleep,
            "message": f"Health score updated. If adaptive mode is enabled, device will sleep for {calculated_sleep}s"
        }), 200
        
    except Exception as e:
        print(f"Error in update_health_score: {str(e)}")
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
    
    Supports incremental fetching via 'since' parameter to reduce Firestore reads.
    Uses server-side caching to further reduce database load.
    
    Requires Authorization header: "Bearer <firebase_id_token>"
    
    Query parameters:
        limit: Total number of readings to return (default: 100, max: 1000)
        since: ISO timestamp - only return readings newer than this (for incremental fetch)
        device_id: Optional filter to get data from specific device (must belong to user)
        per_device_limit: Optional limit per device (useful when user has many devices)
        offset: Offset for pagination (used with Load More button)
    
    Returns:
        JSON with readings from all user's devices, sorted by timestamp (newest first)
    """
    try:
        user_id = g.user['uid']
        
        # Parse query parameters
        try:
            limit = int(request.args.get('limit', 100))
            limit = min(limit, 1000)  # Cap at 1000
        except ValueError:
            limit = 100
        
        since_timestamp = request.args.get('since')
        
        # Offset for pagination (Load More functionality)
        try:
            offset = int(request.args.get('offset', 0))
        except ValueError:
            offset = 0
        
        per_device_limit = request.args.get('per_device_limit')
        if per_device_limit:
            try:
                per_device_limit = int(per_device_limit)
            except ValueError:
                per_device_limit = None
        
        # Optional device filter
        device_id_filter = request.args.get('device_id')
        device_ids = [device_id_filter] if device_id_filter else None
        
        # Handle incremental fetch (since parameter)
        if since_timestamp:
            # Incremental fetch - only new readings
            readings, device_count = get_user_device_readings_since(
                user_id,
                since_timestamp=since_timestamp,
                limit=limit
            )
            
            return jsonify({
                "success": True,
                "user_id": user_id,
                "device_count": device_count,
                "total_readings": len(readings),
                "readings": readings,
                "incremental": True
            }), 200
        
        # Check server-side cache first (only for full fetches, not incremental)
        if not offset and not device_id_filter:
            cached_data = readings_cache.get(user_id)
            
            if cached_data:
                # Cache hit - format and return
                readings = flatten_cached_readings(
                    cached_data['readings_by_device'],
                    limit=limit
                )
                
                return jsonify({
                    "success": True,
                    "user_id": user_id,
                    "device_count": len(cached_data['devices']),
                    "total_readings": len(readings),
                    "readings": readings,
                    "cached": True
                }), 200
        
        # Cache miss or special request - fetch from Firestore
        readings, device_count = get_user_device_readings(
            user_id, 
            device_ids=device_ids,
            limit=limit + offset,  # Add offset for pagination
            per_device_limit=per_device_limit
        )
        
        # Apply offset for pagination
        if offset > 0:
            readings = readings[offset:]
        
        # Populate cache for next request (only for full fetches without filters)
        if not device_id_filter and not offset:
            try:
                devices = get_user_devices(user_id)
                readings_by_device = organize_readings_by_device(readings)
                readings_cache.set(user_id, devices, readings_by_device)
            except Exception as e:
                print(f"Warning: Failed to populate cache: {str(e)}")
        
        return jsonify({
            "success": True,
            "user_id": user_id,
            "device_count": device_count,
            "total_readings": len(readings),
            "readings": readings,
            "cached": False
        }), 200
        
    except Exception as e:
        print(f"Error in get_user_data: {str(e)}")
        return jsonify({"error": "Internal server error", "details": str(e)}), 500


def flatten_cached_readings(readings_by_device, limit=100):
    """
    Flatten readings_by_device dictionary into a single sorted list.
    
    Args:
        readings_by_device: Dict mapping device_id to list of readings
        limit: Maximum number of readings to return
        
    Returns:
        List of readings sorted by timestamp (newest first)
    """
    all_readings = []
    for device_id, readings in readings_by_device.items():
        all_readings.extend(readings)
    
    # Sort by server_timestamp (newest first)
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


@bp.route('/user_data/historical', methods=['GET'])
@require_auth
def get_historical_data():
    """
    Get sparse historical readings (one per hour) for trend visualization.
    Used by frontend to populate localStorage cache for week/all-time views.
    
    Requires Authorization header: "Bearer <firebase_id_token>"
    
    Query parameters:
        hours: Number of hours of history to fetch (default: 168 = 1 week, max: 336 = 2 weeks)
    
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
        
        # Get sparse historical readings
        from app.firebase_client import get_sparse_historical_readings
        readings = get_sparse_historical_readings(user_id, hours)
        
        return jsonify({
            "success": True,
            "user_id": user_id,
            "hours_requested": hours,
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
    Also updates device health scores for adaptive sleep calculation.
    
    Requires Authorization header: "Bearer <firebase_id_token>"
    
    Query parameters:
        time_range_hours: Number of hours of data to analyze (default: 24, max: 168)
        limit_per_device: Maximum readings per device to include (default: 50, max: 200)
    
    Returns:
        JSON with structured advice including:
        - overall_advice: General assessment
        - device_advice: Device-specific recommendations
        - insights: Key observations
        - health_scores_updated: List of devices with updated health scores
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
        
        # Prepare data for Gemini
        formatted_data = prepare_data_for_gemini(
            user_id,
            time_range_hours=time_range_hours,
            limit_per_device=limit_per_device
        )
        
        # Get advice from Gemini
        advice = get_gemini_advice(formatted_data)
        
        # ========================================
        # Update health scores for each device based on advice priority
        # ========================================
        health_scores_updated = []
        
        if advice and 'device_advice' in advice:
            db = get_firestore()
            
            for device_advice in advice['device_advice']:
                device_id = device_advice.get('device_id')
                priority = device_advice.get('priority', 'low')
                
                # Convert priority to health score
                # priority: urgent=2, high=4, medium=6, low=8
                priority_to_score = {
                    'urgent': 2,
                    'high': 4,
                    'medium': 6,
                    'low': 8
                }
                health_score = priority_to_score.get(priority, 7)
                
                if device_id:
                    try:
                        # Update health score in user's device document
                        device_ref = db.collection('users').document(user_id).collection('devices').document(device_id)
                        device_ref.update({
                            'plant_health_score': health_score,
                            'health_score_updated_at': SERVER_TIMESTAMP,
                            'last_advice_priority': priority
                        })
                        
                        # Also update global devices collection
                        global_device_ref = db.collection('devices').document(device_id)
                        if global_device_ref.get().exists:
                            global_device_ref.update({
                                'plant_health_score': health_score,
                                'health_score_updated_at': SERVER_TIMESTAMP
                            })
                        
                        # Invalidate cache
                        if device_id in _device_config_cache:
                            del _device_config_cache[device_id]
                        
                        # Calculate what adaptive sleep would be
                        calculated_sleep = calculate_adaptive_sleep_duration(health_score)
                        
                        health_scores_updated.append({
                            'device_id': device_id,
                            'health_score': health_score,
                            'priority': priority,
                            'calculated_adaptive_sleep': calculated_sleep
                        })
                        
                        print(f"Updated health score for {device_id}: priority={priority} → score={health_score} → sleep={calculated_sleep}s")
                        
                    except Exception as e:
                        print(f"Warning: Failed to update health score for {device_id}: {e}")
        
        return jsonify({
            "success": True,
            "user_id": user_id,
            "timestamp": datetime.utcnow().isoformat() + 'Z',
            "data_summary": {
                "device_count": formatted_data.get('device_count', 0),
                "readings_analyzed": formatted_data.get('overall_summary', {}).get('total_readings', 0),
                "time_range": formatted_data.get('overall_summary', {}).get('time_range', 'unknown')
            },
            "advice": advice,
            "health_scores_updated": health_scores_updated
        }), 200
        
    except Exception as e:
        print(f"Error in get_user_advice: {str(e)}")
        return jsonify({"error": "Internal server error", "details": str(e)}), 500
