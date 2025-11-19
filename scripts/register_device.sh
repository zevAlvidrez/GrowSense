#!/bin/bash
# Helper script to register an ESP32 device to a user account
# Usage: ./register_device.sh [BASE_URL] [DEVICE_ID] [API_KEY] [DEVICE_NAME] [FIREBASE_TOKEN]

BASE_URL="${1:-https://growsense-wer0.onrender.com}"
DEVICE_ID="${2:-}"
API_KEY="${3:-}"
DEVICE_NAME="${4:-$DEVICE_ID}"
TOKEN="${5:-}"

if [ -z "$DEVICE_ID" ] || [ -z "$API_KEY" ]; then
    echo "❌ Error: Missing required parameters"
    echo ""
    echo "Usage:"
    echo "  ./register_device.sh [BASE_URL] [DEVICE_ID] [API_KEY] [DEVICE_NAME] [FIREBASE_TOKEN]"
    echo ""
    echo "Example:"
    echo "  ./register_device.sh https://growsense-wer0.onrender.com esp32_living_room my-api-key-123 'Living Room Sensor' YOUR_FIREBASE_TOKEN"
    echo ""
    echo "To get your Firebase token:"
    echo "  1. Sign in to the dashboard"
    echo "  2. Open browser console (F12)"
    echo "  3. Run: firebase.auth().currentUser.getIdToken().then(console.log)"
    echo ""
    exit 1
fi

if [ -z "$TOKEN" ]; then
    echo "⚠️  Warning: No Firebase token provided"
    echo "The device will be added to device_keys.json but won't be registered to a user."
    echo "You'll need to register it manually via the API."
    echo ""
    read -p "Continue anyway? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

echo "🌱 Registering device to GrowSense..."
echo "======================================"
echo "Base URL: $BASE_URL"
echo "Device ID: $DEVICE_ID"
echo "Device Name: $DEVICE_NAME"
echo ""

if [ -n "$TOKEN" ]; then
    echo "Registering device to user account..."
    RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$BASE_URL/devices/register" \
      -H "Authorization: Bearer $TOKEN" \
      -H "Content-Type: application/json" \
      -d "{
        \"device_id\": \"$DEVICE_ID\",
        \"api_key\": \"$API_KEY\",
        \"name\": \"$DEVICE_NAME\"
      }")
    
    HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
    BODY=$(echo "$RESPONSE" | sed '$d')
    
    if [ "$HTTP_CODE" -eq 201 ]; then
        echo "✅ Device registered successfully!"
        echo "$BODY" | python3 -m json.tool 2>/dev/null || echo "$BODY"
    else
        echo "❌ Registration failed (HTTP $HTTP_CODE)"
        echo "$BODY" | python3 -m json.tool 2>/dev/null || echo "$BODY"
        exit 1
    fi
else
    echo "⚠️  Skipping user registration (no token provided)"
    echo "   Add device to device_keys.json manually"
    echo "   Then register via: curl -X POST $BASE_URL/devices/register ..."
fi

echo ""
echo "📝 Next steps:"
echo "   1. Make sure device is in device_keys.json:"
echo "      {\"$DEVICE_ID\": {\"api_key\": \"$API_KEY\"}}"
echo ""
echo "   2. Configure ESP32 with:"
echo "      #define DEVICE_ID \"$DEVICE_ID\""
echo "      #define API_KEY \"$API_KEY\""
echo ""
echo "   3. Upload firmware to ESP32"
echo ""
echo "   4. Verify data appears in dashboard"

