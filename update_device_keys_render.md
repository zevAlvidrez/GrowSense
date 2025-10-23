# How to Add New Devices to Render

Since `device_keys.json` is not committed to git (for security), you need to manually update it on Render when adding new ESP32 devices.

## Option 1: Render Secret Files (Recommended)

### Step 1: Prepare your device_keys.json

Edit your local `/Users/zev/Downloads/GrowSense/device_keys.json`:

```json
{
  "test_device": "test-key-12345",
  "esp32_device_001": "change-this-to-a-secure-key",
  "esp32_greenhouse_01": "gs-greenhouse-2024-secure-key-abc123"
}
```

### Step 2: Add to Render

1. Go to your Render dashboard
2. Select your `growsense` service
3. Go to "Environment" tab
4. Scroll down to "Secret Files"
5. Click "Add Secret File"
   - **Filename**: `device_keys.json`
   - **Contents**: Paste your entire device_keys.json content

### Step 3: Redeploy

Click "Manual Deploy" → "Deploy latest commit" to restart with the new file.

---

## Option 2: Temporary - Use Test Device

For immediate testing, you can use the existing `test_device`:

In your ESP32 `secrets.h`:
```cpp
#define DEVICE_ID       "test_device"
#define API_KEY         "test-key-12345"
```

This will work immediately without Render changes!

---

## Option 3: Environment Variable (Future Enhancement)

We could enhance the code to support individual device environment variables:

```
DEVICE_esp32_greenhouse_01=gs-greenhouse-2024-secure-key-abc123
DEVICE_test_device=test-key-12345
```

Then modify `app/routes.py` to check environment variables as a fallback.

---

## Current Device Keys on Render

Since device_keys.json is not in git, Render is currently using whatever was last uploaded.

**Quick Test:** Try using `test_device` credentials first to verify everything works!

