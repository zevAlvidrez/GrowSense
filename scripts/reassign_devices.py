"""
Script to reassign devices to a new user account without moving historical data.
This is a lightweight operation that minimizes Firestore usage.

Usage:
    python scripts/reassign_devices.py [source_user_id] [target_user_id] [device_ids...]

Example:
    # Reassign specific garden devices
    python scripts/reassign_devices.py OLD_USER_ID NEW_USER_ID garden_device_1 garden_device_2
"""

import os
import sys
import argparse
from pathlib import Path

# Add parent directory to path
script_dir = Path(__file__).parent
project_root = script_dir.parent
sys.path.insert(0, str(project_root))

# Set environment variable for service account
service_account_path = project_root / 'serviceAccountKey.json'
if not service_account_path.exists():
    print(f"❌ ERROR: Service account key not found at {service_account_path}")
    sys.exit(1)

os.environ['FIREBASE_SERVICE_ACCOUNT_PATH'] = str(service_account_path)

from app.firebase_client import get_firestore
from google.cloud.firestore_v1 import SERVER_TIMESTAMP

def reassign_device(db, source_uid, target_uid, device_id):
    print(f"\nReassigning device '{device_id}'...")
    
    # 1. Get source device metadata (Cheap read)
    source_device_ref = db.collection('users').document(source_uid).collection('devices').document(device_id)
    source_device_doc = source_device_ref.get()
    
    if not source_device_doc.exists:
        print(f"  ⚠️  Device '{device_id}' not found in source account. Checking registry...")
        # Fallback: check registry if source doesn't have it
        registry_ref = db.collection('devices').document(device_id)
        reg_doc = registry_ref.get()
        if reg_doc.exists:
            device_data = {
                'api_key': reg_doc.to_dict().get('api_key'),
                'name': device_id,
                'created_at': SERVER_TIMESTAMP
            }
            print("  ✓ Found in registry")
        else:
            print(f"  ❌ Device '{device_id}' does not exist anywhere")
            return False
    else:
        device_data = source_device_doc.to_dict()
        print(f"  ✓ Found device: {device_data.get('name', device_id)}")
    
    # 2. Create device in target user (Write)
    target_device_ref = db.collection('users').document(target_uid).collection('devices').document(device_id)
    target_device_ref.set(device_data)
    print("  ✓ Created device in target account")
    
    # 3. Update Registry Ownership (Write)
    # This ensures new uploads go to the new user
    device_registry_ref = db.collection('devices').document(device_id)
    device_registry_ref.update({
        'user_id': target_uid, 
        'updated_at': SERVER_TIMESTAMP
    })
    print("  ✓ Updated ownership registry")
    
    # 4. Remove from Source (Write)
    # We only remove the device document, leaving readings as "orphaned" backup
    if source_device_doc.exists:
        source_device_ref.delete()
        print("  ✓ Removed device from source account")
    
    print(f"✅ Device '{device_id}' reassigned successfully!")
    return True

def main():
    parser = argparse.ArgumentParser(description='Reassign devices to new user')
    parser.add_argument('source_uid', help='Source User ID')
    parser.add_argument('target_uid', help='Target User ID')
    parser.add_argument('devices', nargs='+', help='List of device IDs to move')
    
    args = parser.parse_args()
    
    db = get_firestore()
    
    print(f"Reassigning {len(args.devices)} devices from {args.source_uid} to {args.target_uid}")
    print("Note: Historical data will remain in the old account but will not be visible in the new one.")
    
    confirm = input("Proceed? (y/n): ")
    if confirm.lower() != 'y':
        print("Cancelled.")
        return
        
    for device_id in args.devices:
        try:
            reassign_device(db, args.source_uid, args.target_uid, device_id)
        except Exception as e:
            print(f"❌ Failed to reassign {device_id}: {e}")

if __name__ == '__main__':
    main()

