# ESP32 Module Setup Guide - User-Based System

This guide walks you through setting up ESP32 modules to work with the new user-based GrowSense system.

## Overview

With the user-based system, each ESP32 module must be:
1. **Configured** with unique credentials (device_id and api_key)
2. **Registered** to a user account via the dashboard
3. **Added** to the server's `device_keys.json` file

## Step-by-Step Setup

### Step 1: Prepare Device Credentials

For each ESP32 module, you need:
- A unique `DEVICE_ID` (e.g., `esp32_living_room`, `esp32_kitchen_01`)
- A secure `API_KEY` (random string, at least 16 characters)

**Generate a secure API key:**
```bash
# On Mac/Linux:
openssl rand -hex 32

# Or use an online UUID generator
# https://www.uuidgenerator.net/
```

**Example credentials:**
- Device 1: `esp32_living_room` / `a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6`
- Device 2: `esp32_kitchen_01` / `z9y8x7w6v5u4t3s2r1q0p9o8n7m6l5k4`
- Device 3: `esp32_bedroom_01` / `m5n6o7p8q9r0s1t2u3v4w5x6y7z8a9`
- Device 4: `esp32_greenhouse_01` / `k4l5m6n7o8p9q0r1s2t3u4v5w6x7y8`

### Step 2: Configure ESP32 Firmware

1. **Copy the secrets template:**
   ```bash
   cd firmware/GrowSenseModule
   cp secrets.h.example secrets.h
   ```

2. **Edit `secrets.h` with your credentials:**
   ```cpp
   #define WIFI_SSID       "YourWiFiNetworkName"
   #define WIFI_PASSWORD   "YourWiFiPassword"
   #define DEVICE_ID       "esp32_living_room"        // Unique for each module
   #define API_KEY         "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6"  // Unique for each module
   ```

3. **Update server URL (if different from default):**
   Edit `GrowSenseModule.ino` and update:
   ```cpp
   const char* SERVER_URL = "https://your-app-name.onrender.com/upload_data";
   ```

4. **Upload firmware to ESP32:**
   - Open `GrowSenseModule.ino` in Arduino IDE
   - Select your ESP32 board
   - Click Upload
   - Monitor Serial output (115200 baud) to verify connection

### Step 3: Add Device to Server's device_keys.json

On your server (local or Render), add the device credentials to `device_keys.json`:

```json
{
  "esp32_living_room": { "api_key": "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6" },
  "esp32_kitchen_01": { "api_key": "z9y8x7w6v5u4t3s2r1q0p9o8n7m6l5k4" },
  "esp32_bedroom_01": { "api_key": "m5n6o7p8q9r0s1t2u3v4w5x6y7z8a9" },
  "esp32_greenhouse_01": { "api_key": "k4l5m6n7o8p9q0r1s2t3u4v5w6x7y8" }
}
```

**For Render deployment:**
- You'll need to update `device_keys.json` in your repository
- Or use Render's environment variable system (see DEPLOYMENT.md)

### Step 4: Register Device to Your User Account

**Option A: Via Dashboard (Recommended)**

1. Sign in to your GrowSense dashboard
2. Use the browser console (F12) to get your Firebase ID token:
   ```javascript
   firebase.auth().currentUser.getIdToken().then(console.log)
   ```
3. Copy the token

4. Register the device via API:
   ```bash
   curl -X POST https://your-app-name.onrender.com/devices/register \
     -H "Authorization: Bearer YOUR_FIREBASE_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{
       "device_id": "esp32_living_room",
       "api_key": "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6",
       "name": "Living Room Sensor"
     }'
   ```

**Option B: Via Dashboard UI (Future)**

A device registration UI will be added to the dashboard in a future update.

### Step 5: Verify Setup

1. **Check device appears in dashboard:**
   - Refresh your dashboard
   - You should see the device in the device grid

2. **Verify data upload:**
   - Check ESP32 Serial Monitor
   - Look for: `✓ Upload successful!`
   - Check dashboard - data should appear within 60 seconds

3. **Test with curl (optional):**
   ```bash
   curl -X POST https://your-app-name.onrender.com/upload_data \
     -H "Content-Type: application/json" \
     -d '{
       "device_id": "esp32_living_room",
       "api_key": "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6",
       "temperature": 23.5,
       "humidity": 65.0,
       "light": 450,
       "soil_moisture": 42.1
     }'
   ```
   Should return: `{"success": true, ...}`

## Troubleshooting

### Device Not Appearing in Dashboard

**Problem:** Device registered but not showing up

**Solutions:**
- Make sure you registered it to the correct user account
- Check that `device_id` matches exactly (case-sensitive)
- Verify the device has uploaded at least one reading

### Upload Returns 400 Error: "Device not registered to a user"

**Problem:** Device credentials are in `device_keys.json` but device isn't registered to a user

**Solution:**
- Register the device via `/devices/register` endpoint (Step 4)
- Make sure you're using the correct Firebase ID token

### Upload Returns 401 Error: "Invalid device_id or api_key"

**Problem:** Credentials don't match

**Solutions:**
- Verify `DEVICE_ID` and `API_KEY` in `secrets.h` match `device_keys.json`
- Check for typos (case-sensitive)
- Make sure `device_keys.json` uses the new format: `{"device_id": {"api_key": "..."}}`

### Device Shows "Offline" in Dashboard

**Problem:** Device hasn't uploaded data recently

**Solutions:**
- Check ESP32 Serial Monitor for errors
- Verify WiFi connection
- Check server URL is correct
- Verify device is powered on

## Multiple Users / Multiple Devices

### Scenario: One User, Multiple Devices

1. Configure each ESP32 with unique `DEVICE_ID` and `API_KEY`
2. Add all devices to `device_keys.json`
3. Register all devices to the same user account (same Firebase token)
4. All devices will appear in that user's dashboard

### Scenario: Multiple Users, Each with Their Own Devices

1. Each user signs in with their own Google account
2. Each user registers their devices using their own Firebase token
3. Devices are automatically associated with the registering user
4. Users only see their own devices in the dashboard

**Important:** A device can only be registered to ONE user. If you need to transfer a device:
1. Delete it from the original user: `DELETE /devices/<device_id>`
2. Register it to the new user: `POST /devices/register`

## Security Best Practices

1. **Use strong API keys:**
   - At least 32 characters
   - Random, not predictable
   - Different for each device

2. **Never commit secrets:**
   - `secrets.h` is in `.gitignore`
   - `device_keys.json` is in `.gitignore`
   - Never share API keys publicly

3. **Rotate keys if compromised:**
   - Generate new API key
   - Update `secrets.h` on ESP32
   - Update `device_keys.json` on server
   - Re-upload firmware

## Quick Reference

**Device Registration Flow:**
```
ESP32 (secrets.h) → device_keys.json → /devices/register → User Dashboard
```

**Data Upload Flow:**
```
ESP32 → /upload_data (with api_key) → Firestore → User Dashboard
```

**Key Files:**
- `firmware/GrowSenseModule/secrets.h` - ESP32 credentials
- `device_keys.json` - Server-side device authentication
- Firestore `/users/{userId}/devices/{deviceId}` - User-device association

## Next Steps

Once your modules are set up:
- Monitor data in the dashboard
- Get AI advice for your plants
- Configure sensor-specific settings
- Set up alerts (future feature)

