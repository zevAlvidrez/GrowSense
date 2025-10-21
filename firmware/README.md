# Firmware

This folder contains the Arduino sketch for GrowSense.

## Files
- `GrowSenseModule/` — main Arduino sketch (`GrowSenseModule.ino`)
- `libraries/` — optional: copy library versions you want to pin

## Required Board
- **Board**: ESP32 Dev Module (choose the matching variant in Arduino IDE)
- Make sure you have the ESP32 board support installed in Arduino IDE

## Required Libraries
Install via Arduino Library Manager (**Sketch → Include Library → Manage Libraries**):
- **Adafruit IO Arduino** (this will also install required dependencies like Adafruit MQTT Library)

That's it! The WiFi library is included in the ESP32 core.

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
