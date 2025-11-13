"""
Firebase client initialization and helper functions.
"""

import os
import json
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
    from datetime import datetime
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

