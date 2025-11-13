#!/bin/bash
# Test script for device management endpoints
# Note: You'll need a valid Firebase ID token to test these endpoints

BASE_URL="${1:-http://localhost:5002}"
TOKEN="${2:-}"

if [ -z "$TOKEN" ]; then
    echo "⚠️  Warning: No Firebase token provided"
    echo "Usage: ./test_devices.sh [BASE_URL] [FIREBASE_TOKEN]"
    echo ""
    echo "To get a token, use Firebase Auth in your frontend or:"
    echo "  firebase login:ci  # for CI/testing"
    echo ""
    exit 1
fi

echo "🧪 Testing GrowSense Device Management Endpoints"
echo "=============================================="
echo "Base URL: $BASE_URL"
echo ""

# Test 1: List devices (should work if user has devices)
echo "1. Testing GET /devices (list user's devices)..."
curl -s -X GET "$BASE_URL/devices" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
echo ""
echo ""

# Test 2: Register a new device
echo "2. Testing POST /devices/register (register new device)..."
curl -s -X POST "$BASE_URL/devices/register" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "device_id": "test_esp32_001",
    "api_key": "test-api-key-12345",
    "name": "Test ESP32 Device"
  }' | python3 -m json.tool
echo ""
echo ""

# Test 3: Get specific device
echo "3. Testing GET /devices/test_esp32_001 (get device info)..."
curl -s -X GET "$BASE_URL/devices/test_esp32_001" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
echo ""
echo ""

# Test 4: List devices again (should now show the new device)
echo "4. Testing GET /devices again (should show registered device)..."
curl -s -X GET "$BASE_URL/devices" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
echo ""
echo ""

# Test 5: Test device upload with registered device
echo "5. Testing POST /upload_data with registered device..."
curl -s -X POST "$BASE_URL/upload_data" \
  -H "Content-Type: application/json" \
  -d '{
    "device_id": "test_esp32_001",
    "api_key": "test-api-key-12345",
    "temperature": 23.5,
    "humidity": 65.0,
    "light": 450,
    "soil_moisture": 42.1
  }' | python3 -m json.tool
echo ""
echo ""

# Test 6: Delete device
echo "6. Testing DELETE /devices/test_esp32_001 (remove device)..."
curl -s -X DELETE "$BASE_URL/devices/test_esp32_001" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
echo ""
echo ""

# Test 7: Verify device is gone
echo "7. Testing GET /devices/test_esp32_001 (should fail after deletion)..."
curl -s -X GET "$BASE_URL/devices/test_esp32_001" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
echo ""
echo ""

echo "=============================================="
echo "✅ Device management tests complete!"
echo ""

