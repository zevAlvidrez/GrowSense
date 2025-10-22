#!/bin/bash
# Test script for GrowSense API endpoints

BASE_URL="http://localhost:5001"

echo "🌱 GrowSense API Test Script"
echo "=============================="
echo ""

# Test 1: Health check
echo "1️⃣  Testing health endpoint..."
curl -s "$BASE_URL/health" | python3 -m json.tool
echo ""
echo ""

# Test 2: Upload sensor data
echo "2️⃣  Testing data upload (POST /upload_data)..."
curl -s -X POST "$BASE_URL/upload_data" \
  -H "Content-Type: application/json" \
  -d '{
    "device_id": "test_device",
    "api_key": "test-key-12345",
    "timestamp": "2024-10-22T12:34:56Z",
    "temperature": 23.5,
    "humidity": 65.2,
    "light": 450,
    "soil_moisture": 42.1
  }' | python3 -m json.tool
echo ""
echo ""

# Test 3: Upload another reading with different values
echo "3️⃣  Uploading second reading..."
curl -s -X POST "$BASE_URL/upload_data" \
  -H "Content-Type: application/json" \
  -d '{
    "device_id": "test_device",
    "api_key": "test-key-12345",
    "temperature": 24.1,
    "humidity": 68.5,
    "light": 520,
    "soil_moisture": 45.3
  }' | python3 -m json.tool
echo ""
echo ""

# Test 4: Retrieve data
echo "4️⃣  Testing data retrieval (GET /get_data)..."
curl -s "$BASE_URL/get_data?device_id=test_device&limit=10" | python3 -m json.tool
echo ""
echo ""

# Test 5: Invalid API key (should fail)
echo "5️⃣  Testing invalid API key (should return 401)..."
curl -s -X POST "$BASE_URL/upload_data" \
  -H "Content-Type: application/json" \
  -d '{
    "device_id": "test_device",
    "api_key": "wrong-key",
    "temperature": 25.0
  }' | python3 -m json.tool
echo ""
echo ""

echo "✅ Test script complete!"

