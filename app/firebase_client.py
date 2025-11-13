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

