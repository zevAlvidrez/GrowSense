"""
Flask routes for GrowSense API endpoints.
"""

import os
import json
from datetime import datetime
from flask import Blueprint, request, jsonify, render_template
from app.firebase_client import get_firestore
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
    
    Args:
        device_id: Device identifier
        api_key: API key provided in request
        
    Returns:
        bool: True if valid, False otherwise
    """
    device_keys = load_device_keys()
    expected_key = device_keys.get(device_id)
    
    if not expected_key:
        return False
    
    return api_key == expected_key


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
        
        # Validate API key
        if not validate_api_key(device_id, api_key):
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

