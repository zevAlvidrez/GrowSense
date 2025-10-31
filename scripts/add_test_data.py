"""
Script to add test data to Firestore for testing the dashboard.

Usage:
    python scripts/add_test_data.py [device_id] [num_readings]

Examples:
    python scripts/add_test_data.py                          # Adds 50 readings to 'test_device'
    python scripts/add_test_data.py my_device 100            # Adds 100 readings to 'my_device'
    
Or from the scripts directory:
    cd scripts && python add_test_data.py
"""

import os
import sys
from datetime import datetime, timedelta
import random
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
from google.cloud.firestore_v1 import SERVER_TIMESTAMP

def add_test_data(device_id='test_device', num_readings=50):
    """Add test sensor readings to Firestore."""
    try:
        db = get_firestore()
        print(f"Adding {num_readings} test readings for device: {device_id}")
        
        # Current time (using timezone-aware datetime)
        now = datetime.now(datetime.UTC) if hasattr(datetime, 'UTC') else datetime.utcnow()
        
        # Generate readings going back in time
        for i in range(num_readings):
            # Go back in time by 5 minutes for each reading
            timestamp_dt = now - timedelta(minutes=i * 5)
            timestamp_str = timestamp_dt.isoformat().replace('+00:00', 'Z')
            
            # Generate realistic sensor values with some variation
            temperature = 20 + random.uniform(-3, 7)  # 17-27°C
            humidity = 60 + random.uniform(-15, 15)   # 45-75%
            light = 500 + random.uniform(-200, 300)   # 300-800 lux
            soil_moisture = 50 + random.uniform(-20, 20)  # 30-70%
            
            # Create reading document
            reading_doc = {
                'timestamp': timestamp_str,
                'temperature': round(temperature, 1),
                'humidity': round(humidity, 1),
                'light': round(light),
                'soil_moisture': round(soil_moisture, 1),
                'server_timestamp': SERVER_TIMESTAMP
            }
            
            # Add to Firestore
            doc_ref = db.collection('devices').document(device_id).collection('readings').document()
            doc_ref.set(reading_doc)
            
            if (i + 1) % 10 == 0:
                print(f"  Added {i + 1}/{num_readings} readings...")
        
        print(f"✓ Successfully added {num_readings} readings to device '{device_id}'")
        print(f"\nYou can now view this data at:")
        print(f"  - Device ID: {device_id}")
        print(f"  - Time range: {num_readings * 5} minutes of data")
        
    except Exception as e:
        print(f"❌ ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == '__main__':
    # You can customize these parameters
    device_id = 'test_device'
    num_readings = 50
    
    # If command line arguments provided, use those
    if len(sys.argv) > 1:
        device_id = sys.argv[1]
    if len(sys.argv) > 2:
        num_readings = int(sys.argv[2])
    
    print("=" * 80)
    print("ADDING TEST DATA TO FIRESTORE")
    print("=" * 80)
    add_test_data(device_id, num_readings)

