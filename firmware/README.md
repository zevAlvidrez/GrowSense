# Firmware

This folder contains Arduino sketches for GrowSense ESP32 modules.

## Modules

### GrowSenseModule/ (Production)

**Recommended for new setups** - Production-ready firmware that uploads to GrowSense Flask dashboard.

- ✅ Direct HTTP uploads to https://growsense-wer0.onrender.com
- ✅ WiFi with auto-reconnect
- ✅ Secure API key authentication
- ✅ Modular sensor functions (easy to customize)
- ✅ Comprehensive debugging
- ✅ Works with dummy data for testing without sensors

See `GrowSenseModule/README.md` for complete setup instructions.

**Required Libraries:**
- ArduinoJson (install via Library Manager)

### AdafruitGrowSenseModule/ (Legacy)

Alternative implementation using Adafruit IO for MQTT-based uploads.

**Required Libraries:**
- Adafruit IO Arduino

---

## Quick Start

For new deployments, use **GrowSenseModule**:

1. Open `GrowSenseModule/GrowSenseModule.ino` in Arduino IDE
2. Copy `secrets.h.example` to `secrets.h` and configure
3. Install ArduinoJson library
4. Upload to ESP32
5. Monitor serial output (115200 baud)

See module README for detailed instructions.

## Required Board
- **Board**: ESP32 Dev Module (any variant)
- Make sure you have the ESP32 board support installed in Arduino IDE

## Setting Up secrets.h

Arduino IDE requires the `secrets.h` file to be in a specific location as a tab within your sketch.

### Steps to Create secrets.h:
1. Open `GrowSenseModule.ino` in Arduino IDE
2. Click the **down arrow button (▼)** on the top-right of the editor (near the Serial Monitor button)
3. Select **"New Tab"**
4. Name it exactly: `secrets.h`
5. Paste the following content into this new tab:

```cpp
#ifndef SECRETS_H
#define SECRETS_H

#define WIFI_SSID       "YourPrivateWiFi"
#define WIFI_PASS       "YourPrivatePassword"
#define IO_USERNAME     "YourAdafruitUsername"
#define IO_KEY          "YourPrivateActiveKey"

#endif
```

6. Replace the placeholder values with your actual credentials
7. **Important**: Do **not** commit this file to version control

A `secrets.h.example` is provided as a template reference.
