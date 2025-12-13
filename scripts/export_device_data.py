"""
Script to export all device readings for a specific user within a time range.

This script queries Firestore for all readings from specified devices within a
date range and exports them to a CSV file for analysis.

Usage:
    python scripts/export_device_data.py

The script is configured with:
- User ID: us2HiruWUkNZ51EaSxHr69Hdps73
- Time range: Dec 2, 2025 00:01:00 to Dec 4, 2025 14:30:00
- Output: growsense_export_2025-12-02_to_2025-12-04.csv (in project root)
"""

import os
import sys
import csv
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any

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
from app.firebase_client import get_firestore, initialize_firebase


# Configuration
USER_ID = "us2HiruWUkNZ51EaSxHr69Hdps73"
START_TIME = datetime(2025, 12, 2, 0, 1, 0)  # Dec 2, 2025 00:01:00
END_TIME = datetime(2025, 12, 4, 14, 30, 0)   # Dec 4, 2025 14:30:00
OUTPUT_FILENAME = "growsense_export_2025-12-02_to_2025-12-04.csv"
OUTPUT_PATH = project_root / OUTPUT_FILENAME


def format_timestamp(ts) -> str:
    """Format a timestamp to ISO 8601 string with Z suffix."""
    if not ts:
        return ""
    
    # Handle Firestore timestamp objects
    try:
        from google.cloud.firestore_v1 import Timestamp
        if isinstance(ts, Timestamp):
            # Convert Firestore timestamp to datetime
            dt = ts.to_datetime()
            iso_str = dt.isoformat()
            if iso_str.endswith('+00:00'):
                return iso_str.replace('+00:00', 'Z')
            if not iso_str.endswith('Z'):
                return iso_str + 'Z'
            return iso_str
    except ImportError:
        pass
    
    # Handle datetime objects or objects with isoformat method
    if hasattr(ts, 'isoformat'):
        iso_str = ts.isoformat()
        # Ensure Z suffix for UTC
        if iso_str.endswith('+00:00'):
            iso_str = iso_str.replace('+00:00', 'Z')
        elif not iso_str.endswith('Z') and '+' not in iso_str:
            iso_str += 'Z'
        return iso_str
    
    # Handle string timestamps
    if isinstance(ts, str):
        # Already a string, ensure Z suffix
        if ts.endswith('+00:00'):
            return ts.replace('+00:00', 'Z')
        if not ts.endswith('Z') and '+' not in ts:
            return ts + 'Z'
        return ts
    
    return str(ts)


def get_device_metadata(db, user_id: str) -> Dict[str, Dict[str, str]]:
    """
    Get metadata (name, description) for all devices belonging to a user.
    
    Returns:
        Dict mapping device_id to {name, description}
    """
    devices_metadata = {}
    
    try:
        devices_ref = db.collection('users').document(user_id).collection('devices')
        devices = list(devices_ref.stream())
        
        for device_doc in devices:
            device_id = device_doc.id
            device_data = device_doc.to_dict()
            
            devices_metadata[device_id] = {
                'name': device_data.get('name', device_id),
                'description': device_data.get('description', '')
            }
        
        print(f"✓ Found {len(devices_metadata)} device(s)")
        for device_id, meta in devices_metadata.items():
            print(f"  - {device_id}: {meta['name']}")
        
    except Exception as e:
        print(f"⚠️  Warning: Could not fetch device metadata: {e}")
    
    return devices_metadata


def query_device_readings(
    db, 
    user_id: str, 
    device_id: str, 
    start_time: datetime, 
    end_time: datetime
) -> List[Dict[str, Any]]:
    """
    Query all readings for a device within the time range.
    Handles pagination automatically.
    
    Returns:
        List of reading dictionaries
    """
    readings = []
    
    try:
        readings_ref = db.collection('users').document(user_id)\
                        .collection('devices').document(device_id)\
                        .collection('readings')
        
        # Build query with time range filter
        query = readings_ref.where('server_timestamp', '>=', start_time)\
                           .where('server_timestamp', '<=', end_time)\
                           .order_by('server_timestamp', direction='ASCENDING')
        
        # Firestore limit is 1000 per query, so we need pagination
        last_doc = None
        batch_count = 0
        
        while True:
            # Apply pagination cursor if we have one
            if last_doc:
                current_query = query.start_after(last_doc).limit(1000)
            else:
                current_query = query.limit(1000)
            
            # Execute query
            docs = list(current_query.stream())
            
            if not docs:
                break
            
            batch_count += 1
            print(f"    Batch {batch_count}: {len(docs)} readings")
            
            # Process documents
            for doc in docs:
                reading_data = doc.to_dict()
                reading_data['reading_id'] = doc.id
                reading_data['device_id'] = device_id
                readings.append(reading_data)
            
            # Check if we got fewer than 1000 (last batch)
            if len(docs) < 1000:
                break
            
            # Set cursor for next batch
            last_doc = docs[-1]
        
        return readings
        
    except Exception as e:
        print(f"    ❌ Error querying device {device_id}: {e}")
        import traceback
        traceback.print_exc()
        return []


def export_readings_to_csv(
    readings: List[Dict[str, Any]], 
    device_metadata: Dict[str, Dict[str, str]],
    output_path: Path
) -> None:
    """
    Export readings to CSV file.
    
    CSV columns:
    device_id, device_name, device_description, reading_id, timestamp, 
    server_timestamp, temperature, humidity, light, soil_moisture, uv_light
    """
    if not readings:
        print("⚠️  No readings to export. Creating empty CSV file.")
        # Create empty file with headers
        with open(output_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([
                'device_id', 'device_name', 'device_description', 'reading_id',
                'timestamp', 'server_timestamp', 'temperature', 'humidity',
                'light', 'soil_moisture', 'uv_light'
            ])
        return
    
    # Sort readings by server_timestamp, then by reading_id as tiebreaker
    def sort_key(r):
        ts = r.get('server_timestamp')
        ts_val = 0
        
        if ts:
            # Handle Firestore timestamp objects
            try:
                from google.cloud.firestore_v1 import Timestamp
                if isinstance(ts, Timestamp):
                    ts_val = ts.timestamp()
                elif hasattr(ts, 'timestamp'):
                    # datetime object
                    ts_val = ts.timestamp()
                elif isinstance(ts, str):
                    # String timestamp
                    try:
                        ts_val = datetime.fromisoformat(ts.replace('Z', '+00:00')).timestamp()
                    except:
                        ts_val = 0
            except ImportError:
                # Fallback if Timestamp import fails
                if hasattr(ts, 'timestamp'):
                    ts_val = ts.timestamp()
                elif isinstance(ts, str):
                    try:
                        ts_val = datetime.fromisoformat(ts.replace('Z', '+00:00')).timestamp()
                    except:
                        ts_val = 0
        
        return (ts_val, r.get('reading_id', ''))
    
    readings_sorted = sorted(readings, key=sort_key)
    
    # Write to CSV
    print(f"\nWriting {len(readings_sorted)} readings to CSV...")
    
    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        
        # Write header
        writer.writerow([
            'device_id', 'device_name', 'device_description', 'reading_id',
            'timestamp', 'server_timestamp', 'temperature', 'humidity',
            'light', 'soil_moisture', 'uv_light'
        ])
        
        # Write data rows
        for reading in readings_sorted:
            device_id = reading.get('device_id', '')
            device_info = device_metadata.get(device_id, {'name': device_id, 'description': ''})
            
            row = [
                device_id,
                device_info.get('name', device_id),
                device_info.get('description', ''),
                reading.get('reading_id', ''),
                format_timestamp(reading.get('timestamp')),
                format_timestamp(reading.get('server_timestamp')),
                reading.get('temperature', '') or '',
                reading.get('humidity', '') or '',
                reading.get('light', '') or '',
                reading.get('soil_moisture', '') or '',
                reading.get('uv_light', '') or ''
            ]
            
            writer.writerow(row)
    
    print(f"✓ CSV file written: {output_path}")


def main():
    """Main export function."""
    print("=" * 80)
    print("GROWSENSE DATA EXPORT")
    print("=" * 80)
    print(f"\nUser ID: {USER_ID}")
    print(f"Time Range: {START_TIME.isoformat()}Z to {END_TIME.isoformat()}Z")
    print(f"Output File: {OUTPUT_PATH}")
    print()
    
    # Initialize Firebase
    print("Initializing Firebase...")
    try:
        initialize_firebase()
        db = get_firestore()
        print("✓ Firebase initialized")
    except Exception as e:
        print(f"❌ ERROR: Failed to initialize Firebase: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    # Get device metadata
    print(f"\nFetching devices for user {USER_ID}...")
    device_metadata = get_device_metadata(db, USER_ID)
    
    if not device_metadata:
        print("❌ ERROR: No devices found for this user")
        sys.exit(1)
    
    # Query readings for each device
    print(f"\nQuerying readings from {START_TIME.isoformat()}Z to {END_TIME.isoformat()}Z...")
    print()
    
    all_readings = []
    device_stats = {}
    
    for device_id, meta in device_metadata.items():
        device_name = meta['name']
        print(f"Device: {device_name} ({device_id})")
        
        readings = query_device_readings(db, USER_ID, device_id, START_TIME, END_TIME)
        
        device_stats[device_id] = {
            'name': device_name,
            'count': len(readings)
        }
        
        if readings:
            print(f"  ✓ Found {len(readings)} readings")
            all_readings.extend(readings)
        else:
            print(f"  ⚠️  No readings found in time range")
    
    # Summary
    print("\n" + "=" * 80)
    print("EXPORT SUMMARY")
    print("=" * 80)
    print(f"\nTotal readings: {len(all_readings)}")
    print(f"Time range: {START_TIME.isoformat()}Z to {END_TIME.isoformat()}Z")
    print(f"Devices: {len(device_metadata)}")
    print("\nReadings per device:")
    for device_id, stats in device_stats.items():
        expected = int((END_TIME - START_TIME).total_seconds() / 60)  # ~1 per minute
        percentage = (stats['count'] / expected * 100) if expected > 0 else 0
        print(f"  - {stats['name']}: {stats['count']} readings ({percentage:.1f}% of expected)")
    
    # Export to CSV
    print(f"\nExporting to CSV...")
    export_readings_to_csv(all_readings, device_metadata, OUTPUT_PATH)
    
    # File size info
    if OUTPUT_PATH.exists():
        file_size = OUTPUT_PATH.stat().st_size
        file_size_kb = file_size / 1024
        file_size_mb = file_size_kb / 1024
        print(f"\nFile size: {file_size_kb:.1f} KB ({file_size_mb:.2f} MB)")
    
    print("\n" + "=" * 80)
    print("EXPORT COMPLETE")
    print("=" * 80)
    print(f"\n✓ Data exported to: {OUTPUT_PATH}")
    print(f"✓ Total readings: {len(all_readings)}")
    print()


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Export cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

