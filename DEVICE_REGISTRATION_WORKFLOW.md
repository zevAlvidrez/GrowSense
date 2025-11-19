# Device Registration Workflow

Quick reference for registering ESP32 modules to users in the GrowSense system.

## The Two-Step Process

Each ESP32 module needs to be registered in **two places**:

1. **Server Authentication** (`device_keys.json`) - Allows device to upload data
2. **User Association** (via `/devices/register` API) - Links device to a user account

## Quick Workflow

### For Each ESP32 Module:

#### 1. Generate Credentials
```bash
# Generate secure API key
openssl rand -hex 32
```

Example output: `a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6`

#### 2. Configure ESP32 Firmware

Edit `firmware/GrowSenseModule/secrets.h`:
```cpp
#define DEVICE_ID       "esp32_living_room"  // Unique name
#define API_KEY         "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6"
```

#### 3. Add to device_keys.json

On your server (local or Render), update `device_keys.json`:
```json
{
  "esp32_living_room": { "api_key": "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6" }
}
```

**For Render:** Update the file in your repository and redeploy, or use environment variables.

#### 4. Register to User Account

**Get your Firebase token:**
1. Sign in to dashboard: `https://your-app.onrender.com`
2. Open browser console (F12)
3. Run:
   ```javascript
   firebase.auth().currentUser.getIdToken().then(console.log)
   ```
4. Copy the token

**Register the device:**
```bash
curl -X POST https://your-app.onrender.com/devices/register \
  -H "Authorization: Bearer YOUR_FIREBASE_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "device_id": "esp32_living_room",
    "api_key": "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6",
    "name": "Living Room Sensor"
  }'
```

**Or use the helper script:**
```bash
./scripts/register_device.sh \
  https://your-app.onrender.com \
  esp32_living_room \
  a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6 \
  "Living Room Sensor" \
  YOUR_FIREBASE_TOKEN
```

#### 5. Verify

1. Refresh dashboard - device should appear
2. Upload firmware to ESP32
3. Check Serial Monitor - should see "✓ Upload successful!"
4. Check dashboard - data should appear within 60 seconds

## Why Two Steps?

- **device_keys.json**: Authenticates the device when it uploads data (API key validation)
- **User Registration**: Associates the device with a user account (for dashboard display)

**Without device_keys.json:** Uploads will fail with 401 error  
**Without user registration:** Device can upload but won't appear in dashboard

## Multiple Devices

For each additional device:
1. Use a **unique** `DEVICE_ID` (e.g., `esp32_kitchen`, `esp32_bedroom`)
2. Generate a **unique** `API_KEY` for each
3. Add to `device_keys.json`
4. Register to the same user (or different users)

## Troubleshooting

### "Device not registered to a user" (400 error)
- Device is in `device_keys.json` but not registered to a user
- **Fix:** Run `/devices/register` API call

### "Invalid device_id or api_key" (401 error)
- Credentials don't match between ESP32 and `device_keys.json`
- **Fix:** Verify `DEVICE_ID` and `API_KEY` match exactly (case-sensitive)

### Device not showing in dashboard
- Device registered but no data uploaded yet
- **Fix:** Wait for ESP32 to upload data, or manually upload a test reading

## See Also

- `firmware/MODULE_SETUP_GUIDE.md` - Complete ESP32 setup guide
- `firmware/GrowSenseModule/README.md` - Firmware documentation

