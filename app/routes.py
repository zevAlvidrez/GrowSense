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
    get_device_info
)
from google.cloud.firestore_v1 import SERVER_TIMESTAMP

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
    Checks Firestore first, then falls back to device_keys.json.
    
    Args:
        device_id: Device identifier
        api_key: API key provided in request
        
    Returns:
        tuple: (is_valid: bool, user_id: str or None)
               user_id is None for legacy devices from JSON file
    """
    db = get_firestore()
    
    # First, check Firestore (reverse lookup: /devices/{deviceId})
    device_ref = db.collection('devices').document(device_id)
    device_doc = device_ref.get()
    
    if device_doc.exists:
        device_data = device_doc.to_dict()
        stored_key = device_data.get('api_key')
        if stored_key == api_key:
            return (True, device_data.get('user_id'))
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
    return render_template('index.html')


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
            'raw_json': data,  # Store full payload for debugging
            'server_timestamp': SERVER_TIMESTAMP  # Firestore server timestamp
        }
        
        # Remove None values
        reading_doc = {k: v for k, v in reading_doc.items() if v is not None}
        
        # Write to Firestore: /devices/{device_id}/readings/{auto-id}
        db = get_firestore()
        doc_ref = db.collection('devices').document(device_id).collection('readings').document()
        doc_ref.set(reading_doc)
        
        return jsonify({
            "success": True,
            "message": "Data uploaded successfully",
            "device_id": device_id,
            "reading_id": doc_ref.id,
            "timestamp": timestamp
        }), 201
        
    except Exception as e:
        print(f"Error in upload_data: {str(e)}")
        return jsonify({"error": "Internal server error", "details": str(e)}), 500


@bp.route('/get_data', methods=['GET'])
def get_data():
    """
    Retrieve sensor readings for a specific device.
    
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

