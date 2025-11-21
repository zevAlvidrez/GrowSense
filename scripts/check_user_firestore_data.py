"""
Script to check user-specific data in Firestore (user-centric structure).

This checks the new user-based structure:
  /users/{userId}/devices/{deviceId}/readings/

Usage:
    python scripts/check_user_firestore_data.py [user_id] [device_id]

Examples:
    # Check all users and devices
    python scripts/check_user_firestore_data.py
    
    # Check specific user
    python scripts/check_user_firestore_data.py YOUR_USER_ID
    
    # Check specific device for specific user
    python scripts/check_user_firestore_data.py YOUR_USER_ID mock_device_1
"""

import os
import sys
from pathlib import Path
from datetime import datetime

# Add parent directory to path so we can import app modules
script_dir = Path(__file__).parent
project_root = script_dir.parent
sys.path.insert(0, str(project_root))

# Set environment variable for service account
service_account_path = project_root / 'serviceAccountKey.json'
if not service_account_path.exists():
    print(f"❌ ERROR: Service account key not found at {service_account_path}")
    print("Please ensure serviceAccountKey.json exists in the project root directory.")
    sys.exit(1)

os.environ['FIREBASE_SERVICE_ACCOUNT_PATH'] = str(service_account_path)

# Import after setting environment variable
from app.firebase_client import get_firestore

def format_timestamp(ts):
    """Format a timestamp for display."""
    if not ts:
        return "N/A"
    if hasattr(ts, 'isoformat'):
        return ts.isoformat()
    if isinstance(ts, str):
        return ts
    return str(ts)

def check_user_firestore_data(user_id=None, device_id=None):
    """Check and display user-specific data in Firestore."""
    try:
        db = get_firestore()
        print("=" * 80)
        print("FIRESTORE USER-CENTRIC DATA CHECK")
        print("=" * 80)
        
        # Get all users
        users_ref = db.collection('users')
        users = list(users_ref.list_documents())
        
        if not users:
            print("\n⚠️  NO USERS FOUND IN DATABASE")
            print("The 'users' collection is empty.")
            return
        
        print(f"\n✓ Found {len(users)} user(s) in database\n")
        
        # Filter to specific user if provided
        if user_id:
            users = [u for u in users if u.id == user_id]
            if not users:
                print(f"❌ User '{user_id}' not found in database")
                return
        
        # Iterate through each user
        for user_ref in users:
            user_id_check = user_ref.id
            print(f"\n{'='*80}")
            print(f"👤 USER: {user_id_check}")
            print(f"{'='*80}")
            
            # Get user's devices
            devices_ref = user_ref.collection('devices')
            devices = list(devices_ref.list_documents())
            
            if not devices:
                print("\n  ⚠️  No devices registered to this user")
                continue
            
            print(f"\n  ✓ Found {len(devices)} device(s) registered to this user:\n")
            
            # Filter to specific device if provided
            if device_id:
                devices = [d for d in devices if d.id == device_id]
                if not devices:
                    print(f"  ❌ Device '{device_id}' not found for this user")
                    continue
            
            # Iterate through each device
            for device_ref in devices:
                device_id_check = device_ref.id
                print(f"\n  {'-'*76}")
                print(f"  📱 DEVICE: {device_id_check}")
                print(f"  {'-'*76}")
                
                # Get device metadata
                device_snapshot = device_ref.get()
                device_data = device_snapshot.to_dict() if device_snapshot.exists else None
                if device_data:
                    print("\n  Device metadata:")
                    for key, value in device_data.items():
                        if key == 'created_at' or key == 'last_seen':
                            value = format_timestamp(value)
                        print(f"    {key}: {value}")
                
                # Get readings for this device
                readings_ref = device_ref.collection('readings')
                
                try:
                    # Try to query with server_timestamp ordering
                    readings = list(readings_ref.order_by('server_timestamp', direction='DESCENDING').limit(10).stream())
                except Exception as e:
                    # If ordering fails (no index), try without ordering
                    print(f"  ⚠️  Note: Could not order by server_timestamp: {str(e)}")
                    readings = list(readings_ref.limit(10).stream())
                
                if not readings:
                    print("\n    ⚠️  No readings found for this device")
                    print(f"    Location: /users/{user_id_check}/devices/{device_id_check}/readings/")
                else:
                    # Get total count (approximate)
                    all_readings = list(readings_ref.stream())
                    total_count = len(all_readings)
                    
                    print(f"\n    ✓ Found {total_count} reading(s) total")
                    print(f"    Location: /users/{user_id_check}/devices/{device_id_check}/readings/")
                    print("\n    Most recent readings (up to 5):")
                    print("    " + "-" * 72)
                    
                    # Show up to 5 most recent readings
                    for i, reading_doc in enumerate(readings[:5], 1):
                        reading_data = reading_doc.to_dict()
                        print(f"\n    Reading #{i} (ID: {reading_doc.id}):")
                        
                        # Format the display
                        for key, value in reading_data.items():
                            if key == 'server_timestamp' or key == 'timestamp':
                                value = format_timestamp(value)
                            elif key == 'raw_json':
                                # Show raw_json summary
                                if isinstance(value, dict):
                                    print(f"      {key}: (contains {len(value)} fields)")
                                    # Show uv_light if present
                                    if 'uv_light' in value:
                                        print(f"        uv_light: {value['uv_light']}")
                                else:
                                    print(f"      {key}: {value}")
                                continue
                            print(f"      {key}: {value}")
                    
                    if total_count > 5:
                        print(f"\n    ... and {total_count - 5} more reading(s)")
        
        # Also check the reverse lookup /devices collection
        print(f"\n{'='*80}")
        print("DEVICE REGISTRY (Reverse Lookup)")
        print(f"{'='*80}")
        
        devices_registry = db.collection('devices')
        registry_docs = list(devices_registry.list_documents())
        
        if not registry_docs:
            print("\n⚠️  No devices in registry")
        else:
            print(f"\n✓ Found {len(registry_docs)} device(s) in registry:\n")
            for device_ref in registry_docs:
                device_data = device_ref.get().to_dict() if device_ref.get().exists else None
                if device_data:
                    print(f"  {device_ref.id}:")
                    print(f"    user_id: {device_data.get('user_id', 'N/A')}")
                    print(f"    registered_at: {format_timestamp(device_data.get('registered_at'))}")
        
        print("\n" + "=" * 80)
        print("END OF DATABASE CHECK")
        print("=" * 80)
        
    except Exception as e:
        print(f"\n❌ ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == '__main__':
    user_id = sys.argv[1] if len(sys.argv) > 1 else None
    device_id = sys.argv[2] if len(sys.argv) > 2 else None
    
    if user_id:
        print(f"Checking data for user: {user_id}")
        if device_id:
            print(f"Checking data for device: {device_id}")
        print()
    
    check_user_firestore_data(user_id, device_id)

