#!/usr/bin/env python3
"""
Analyze sensor data dropouts for garden devices.

This script examines sensor readings to identify when certain sensors
fail to report data (not zero readings, but missing data entirely).
"""

import os
import sys
from datetime import datetime
from collections import defaultdict

# Add app directory to path to import firebase_client
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

from app.firebase_client import get_firestore, initialize_firebase

# Configuration
USER_ID = "us2HiruWUkNZ51EaSxHr69Hdps73"
DEVICE_IDS = ["garden_device_1", "garden_device_2", "garden_device_3"]

# Sensors we expect to see
EXPECTED_SENSORS = ["temperature", "humidity", "light", "soil_moisture", "uv_light"]


def analyze_dropouts():
    """Analyze sensor dropouts for the specified devices."""
    
    print("=" * 80)
    print("SENSOR DROPOUT ANALYSIS")
    print("=" * 80)
    print(f"User ID: {USER_ID}")
    print(f"Devices: {', '.join(DEVICE_IDS)}")
    print(f"Expected sensors: {', '.join(EXPECTED_SENSORS)}")
    print("=" * 80)
    print()
    
    # Initialize Firebase
    initialize_firebase()
    db = get_firestore()
    
    # Storage for analysis
    device_stats = {}
    sensor_dropout_stats = defaultdict(int)  # Count by sensor type
    device_dropout_stats = defaultdict(int)  # Count by device
    combined_dropout_stats = defaultdict(lambda: defaultdict(int))  # device -> sensor -> count
    
    # Analyze each device
    for device_id in DEVICE_IDS:
        print(f"\n{'=' * 80}")
        print(f"ANALYZING: {device_id}")
        print('=' * 80)
        
        # Query readings for this device
        readings_ref = db.collection('users').document(USER_ID)\
                        .collection('devices').document(device_id)\
                        .collection('readings')
        
        # Get all readings ordered by timestamp
        query = readings_ref.order_by('server_timestamp', direction='DESCENDING')
        docs = list(query.stream())
        
        total_readings = len(docs)
        print(f"Total readings: {total_readings}")
        
        if total_readings == 0:
            print(f"⚠ No readings found for {device_id}")
            continue
        
        # Analyze each reading
        readings_with_dropouts = []
        complete_readings = 0
        
        for doc in docs:
            reading = doc.to_dict()
            reading_id = doc.id
            
            # Check which sensors are missing
            missing_sensors = []
            present_sensors = []
            
            for sensor in EXPECTED_SENSORS:
                # Check if sensor exists and has a non-None value
                sensor_value = reading.get(sensor)
                
                # Also check in raw_json if sensor not found at top level
                if sensor_value is None and 'raw_json' in reading:
                    sensor_value = reading.get('raw_json', {}).get(sensor)
                
                if sensor_value is None:
                    missing_sensors.append(sensor)
                    sensor_dropout_stats[sensor] += 1
                    device_dropout_stats[device_id] += 1
                    combined_dropout_stats[device_id][sensor] += 1
                else:
                    present_sensors.append(sensor)
            
            # Record readings with dropouts
            if missing_sensors:
                timestamp = reading.get('server_timestamp', reading.get('timestamp'))
                if hasattr(timestamp, 'isoformat'):
                    timestamp_str = timestamp.isoformat()
                else:
                    timestamp_str = str(timestamp)
                
                readings_with_dropouts.append({
                    'id': reading_id,
                    'timestamp': timestamp_str,
                    'missing': missing_sensors,
                    'present': present_sensors
                })
            else:
                complete_readings += 1
        
        # Device summary
        dropout_count = len(readings_with_dropouts)
        dropout_percentage = (dropout_count / total_readings * 100) if total_readings > 0 else 0
        
        device_stats[device_id] = {
            'total_readings': total_readings,
            'complete_readings': complete_readings,
            'readings_with_dropouts': dropout_count,
            'dropout_percentage': dropout_percentage,
            'dropout_details': readings_with_dropouts
        }
        
        print(f"\nSummary:")
        print(f"  Complete readings: {complete_readings} ({100 - dropout_percentage:.1f}%)")
        print(f"  Readings with dropouts: {dropout_count} ({dropout_percentage:.1f}%)")
        
        # Show sample dropouts
        if dropout_count > 0:
            print(f"\n  Sample dropouts (showing first 10):")
            for i, dropout in enumerate(readings_with_dropouts[:10]):
                print(f"    [{i+1}] {dropout['timestamp'][:19]}")
                print(f"        Missing: {', '.join(dropout['missing'])}")
                print(f"        Present: {', '.join(dropout['present'])}")
    
    # Overall analysis
    print("\n\n" + "=" * 80)
    print("OVERALL ANALYSIS")
    print("=" * 80)
    
    # Dropout by device
    print("\n1. DROPOUTS BY DEVICE:")
    print("-" * 40)
    total_dropout_events = sum(device_dropout_stats.values())
    
    for device_id in DEVICE_IDS:
        count = device_dropout_stats[device_id]
        percentage = (count / total_dropout_events * 100) if total_dropout_events > 0 else 0
        total = device_stats.get(device_id, {}).get('total_readings', 0)
        device_percentage = (device_stats.get(device_id, {}).get('readings_with_dropouts', 0) / total * 100) if total > 0 else 0
        print(f"  {device_id}:")
        print(f"    Total readings: {total}")
        print(f"    Readings with dropouts: {device_stats.get(device_id, {}).get('readings_with_dropouts', 0)} ({device_percentage:.1f}%)")
        print(f"    Total sensor dropouts: {count} ({percentage:.1f}% of all dropouts)")
    
    # Dropout by sensor type
    print("\n2. DROPOUTS BY SENSOR TYPE:")
    print("-" * 40)
    for sensor in EXPECTED_SENSORS:
        count = sensor_dropout_stats[sensor]
        percentage = (count / total_dropout_events * 100) if total_dropout_events > 0 else 0
        print(f"  {sensor}: {count} times ({percentage:.1f}% of all dropouts)")
    
    # Combined analysis (device + sensor)
    print("\n3. DROPOUTS BY DEVICE AND SENSOR:")
    print("-" * 40)
    for device_id in DEVICE_IDS:
        if device_id in combined_dropout_stats:
            print(f"\n  {device_id}:")
            device_dropouts = combined_dropout_stats[device_id]
            for sensor in EXPECTED_SENSORS:
                count = device_dropouts[sensor]
                if count > 0:
                    total = device_stats[device_id]['total_readings']
                    percentage = (count / total * 100) if total > 0 else 0
                    print(f"    {sensor}: {count} times ({percentage:.1f}% of readings)")
    
    # Pattern analysis
    print("\n4. PATTERN ANALYSIS:")
    print("-" * 40)
    
    # Check if dropouts tend to occur together
    sensor_combination_counts = defaultdict(int)
    for device_id in DEVICE_IDS:
        if device_id in device_stats:
            for dropout in device_stats[device_id]['dropout_details']:
                missing_combo = tuple(sorted(dropout['missing']))
                sensor_combination_counts[missing_combo] += 1
    
    print("  Common sensor dropout combinations:")
    for combo, count in sorted(sensor_combination_counts.items(), key=lambda x: x[1], reverse=True):
        if count > 1:  # Only show combinations that occur more than once
            print(f"    {', '.join(combo)}: {count} times")
    
    # Hypothesis testing
    print("\n5. HYPOTHESIS TESTING:")
    print("-" * 40)
    print("  Testing if I2C sensors (temperature, humidity, light) dropout together...")
    
    i2c_sensors = {"temperature", "humidity", "light"}
    analog_sensors = {"soil_moisture", "uv_light"}
    
    i2c_together_count = 0
    i2c_partial_count = 0
    analog_only_count = 0
    
    for combo in sensor_combination_counts:
        combo_set = set(combo)
        i2c_in_combo = combo_set & i2c_sensors
        analog_in_combo = combo_set & analog_sensors
        
        if len(i2c_in_combo) == len(i2c_sensors):
            # All I2C sensors missing
            i2c_together_count += sensor_combination_counts[combo]
        elif len(i2c_in_combo) > 0:
            # Some I2C sensors missing
            i2c_partial_count += sensor_combination_counts[combo]
        elif len(analog_in_combo) > 0 and len(i2c_in_combo) == 0:
            # Only analog sensors missing
            analog_only_count += sensor_combination_counts[combo]
    
    print(f"    All I2C sensors dropout together: {i2c_together_count} times")
    print(f"    Partial I2C sensor dropouts: {i2c_partial_count} times")
    print(f"    Only analog sensor dropouts: {analog_only_count} times")
    
    # Temperature & Humidity together (AM2320 sensor)
    am2320_together = sum(count for combo, count in sensor_combination_counts.items() 
                          if 'temperature' in combo and 'humidity' in combo)
    print(f"\n  Temperature & Humidity dropout together (AM2320): {am2320_together} times")
    
    print("\n" + "=" * 80)
    print("ANALYSIS COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    try:
        analyze_dropouts()
    except Exception as e:
        print(f"\n❌ ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

