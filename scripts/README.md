# GrowSense Scripts

Utility scripts for managing and diagnosing the GrowSense Firestore database.

## Prerequisites

1. Make sure you have activated the Python virtual environment:
   ```bash
   cd /path/to/GrowSense
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

2. Ensure `serviceAccountKey.json` exists in the project root directory

## Scripts

### 🔍 check_firestore_data.py

Check what data is currently stored in your Firestore database.

**Usage:**
```bash
# From project root
python scripts/check_firestore_data.py

# Or from scripts directory
cd scripts
python check_firestore_data.py
```

**Output:**
- Lists all devices in the database
- Shows count of readings for each device
- Displays the 5 most recent readings for each device

**Example:**
```
================================================================================
FIRESTORE DATABASE CONTENTS
================================================================================

✓ Found 2 device(s) in database:

================================================================================
📱 DEVICE: esp32_greenhouse_01
================================================================================

  ✓ Found 2236 reading(s)

  Most recent readings (up to 5):
  ...
```

### ➕ add_test_data.py

Add test sensor data to Firestore for testing the dashboard.

**Usage:**
```bash
# Add 50 readings to 'test_device' (default)
python scripts/add_test_data.py

# Add 100 readings to a specific device
python scripts/add_test_data.py my_device_id 100

# Or from scripts directory
cd scripts
python add_test_data.py
```

**Parameters:**
- `device_id` (optional): The device ID to add data to (default: `test_device`)
- `num_readings` (optional): Number of readings to generate (default: 50)

**What it does:**
- Generates realistic sensor data with random variations
- Creates readings going back in time (5 minutes apart)
- Temperature: 17-27°C
- Humidity: 45-75%
- Light: 300-800 lux
- Soil Moisture: 30-70%

## Troubleshooting

### "Service account key not found"
Make sure `serviceAccountKey.json` exists in the project root (not in the scripts directory).

### "No module named 'app'"
Make sure you're running the script from the project root or that the Python path is set correctly. The scripts automatically add the parent directory to the Python path.

### "No data found in database"
If you just added data, wait a few seconds for Firestore to process it. Firestore operations can have slight delays.

If you're checking a different Firebase project than expected:
1. Verify your `serviceAccountKey.json` has the correct `project_id`
2. Check that the `project_id` matches your Firebase console project

### Firestore shows empty but script shows data
This is normal! Device documents that only contain subcollections (like our `readings` subcollection) may not appear in some Firestore console views. The data is still there - you need to:
1. Click on the `devices` collection
2. Click on a device ID (e.g., `esp32_greenhouse_01`)
3. Click on the `readings` subcollection to see the data

## Adding Your Own Scripts

Feel free to add more utility scripts to this directory! When creating new scripts:
1. Add helpful docstrings and usage examples
2. Use the same path setup pattern to find the project root
3. Update this README with documentation

