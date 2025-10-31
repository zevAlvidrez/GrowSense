"""
Script to check what data is currently in Firestore.

Usage:
    python scripts/check_firestore_data.py

Or from the scripts directory:
    cd scripts && python check_firestore_data.py
"""

import os
import sys
from pathlib import Path

# Add parent directory to path so we can import app modules
script_dir = Path(__file__).parent
project_root = script_dir.parent
sys.path.insert(0, str(project_root))

# Set environment variable for service account
# Try to find serviceAccountKey.json in project root
service_account_path = project_root / 'serviceAccountKey.json'
if not service_account_path.exists():
    print(f"❌ ERROR: Service account key not found at {service_account_path}")
    print("Please ensure serviceAccountKey.json exists in the project root directory.")
    sys.exit(1)

os.environ['FIREBASE_SERVICE_ACCOUNT_PATH'] = str(service_account_path)

# Import after setting environment variable
from app.firebase_client import get_firestore

def check_firestore_data():
    """Check and display all data in Firestore."""
    try:
        db = get_firestore()
        print("=" * 80)
        print("FIRESTORE DATABASE CONTENTS")
        print("=" * 80)
        
        # Get all devices (use list_documents instead of stream)
        # stream() only returns documents with fields, not those with only subcollections
        devices_ref = db.collection('devices')
        devices = list(devices_ref.list_documents())
        
        if not devices:
            print("\n⚠️  NO DEVICES FOUND IN DATABASE")
            print("The 'devices' collection is empty.")
            return
        
        print(f"\n✓ Found {len(devices)} device(s) in database:\n")
        
        # Iterate through each device
        for device_ref in devices:
            device_id = device_ref.id
            print(f"\n{'='*80}")
            print(f"📱 DEVICE: {device_id}")
            print(f"{'='*80}")
            
            # Get device data (if any fields are stored at device level)
            device_snapshot = device_ref.get()
            device_data = device_snapshot.to_dict() if device_snapshot.exists else None
            if device_data:
                print("\nDevice metadata:")
                for key, value in device_data.items():
                    print(f"  {key}: {value}")
            
            # Get readings for this device
            readings_ref = device_ref.collection('readings')
            readings = list(readings_ref.order_by('server_timestamp', direction='DESCENDING').stream())
            
            if not readings:
                print("\n  ⚠️  No readings found for this device")
            else:
                print(f"\n  ✓ Found {len(readings)} reading(s)")
                print("\n  Most recent readings (up to 5):")
                print("  " + "-" * 76)
                
                # Show up to 5 most recent readings
                for i, reading_doc in enumerate(readings[:5], 1):
                    reading_data = reading_doc.to_dict()
                    print(f"\n  Reading #{i} (ID: {reading_doc.id}):")
                    
                    # Format the display
                    for key, value in reading_data.items():
                        if key == 'server_timestamp':
                            # Format timestamp nicely
                            if hasattr(value, 'isoformat'):
                                value = value.isoformat()
                        elif key == 'raw_json':
                            # Skip raw_json for cleaner display
                            continue
                        print(f"    {key}: {value}")
                
                if len(readings) > 5:
                    print(f"\n  ... and {len(readings) - 5} more reading(s)")
        
        print("\n" + "=" * 80)
        print("END OF DATABASE CONTENTS")
        print("=" * 80)
        
    except Exception as e:
        print(f"\n❌ ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == '__main__':
    check_firestore_data()

