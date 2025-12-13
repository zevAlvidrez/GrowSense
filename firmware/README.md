# GrowSense ESP32 Firmware

Complete firmware for ESP32-based plant monitoring modules that collect sensor data and upload it to the GrowSense cloud dashboard.

## Overview

The GrowSense firmware runs on ESP32 development boards and collects environmental data from four sensors:
- **AM2320**: Temperature and Humidity (I2C)
- **BH1750**: Light intensity in lux (I2C)
- **SEN0193**: Soil moisture percentage (Analog)
- **GUVA-S12SD**: UV Index (Analog)

The firmware implements deep sleep mode for ultra-low power consumption, enabling 6-12 months of battery operation.

## Sensors

### AM2320 Temperature & Humidity Sensor
- **Interface**: I2C Bus 1
- **Pins**: SDA=GPIO 48, SCL=GPIO 35
- **Range**: Temperature -40°C to 80°C, Humidity 0-100% RH
- **Accuracy**: ±0.5°C, ±3% RH

### BH1750 Light Sensor
- **Interface**: I2C Bus 0
- **Pins**: SDA=GPIO 6, SCL=GPIO 7
- **Address**: 0x23
- **Range**: 1-65535 lux
- **Resolution**: 1 lux

### SEN0193 Capacitive Soil Moisture Sensor
- **Interface**: Analog
- **Pin**: GPIO 20
- **Range**: 0-100% (calibrated)
- **Calibration**: Requires air (dry) and water (wet) calibration values

### GUVA-S12SD UV Light Sensor
- **Interface**: Analog
- **Pin**: GPIO 2
- **Range**: 0-15 UV Index
- **Spectral Range**: 240-370nm (UVB and UVA)

## Quick Start

### 1. Install Required Libraries

Via Arduino Library Manager:
- **ArduinoJson** by Benoit Blanchon (v6.x or later)
- **Adafruit AM2320** by Adafruit

### 2. Configure Secrets

1. Open `GrowSenseModule_Production/GrowSenseModule_Production.ino` in Arduino IDE
2. Create a new tab in Arduino IDE (click the down arrow → "New Tab")
3. Name it exactly: `secrets.h`
4. Copy content from `secrets.h.example` and fill in your values:

```cpp
#ifndef SECRETS_H
#define SECRETS_H

#define WIFI_SSID       "YourWiFiNetwork"
#define WIFI_PASSWORD   "YourWiFiPassword"
#define DEVICE_ID       "esp32_device_001"
#define API_KEY         "your-secret-api-key"

#endif
```

**Important**: Never commit `secrets.h` to version control. It's already in `.gitignore`.

### 3. Configure Board Settings

In Arduino IDE:
- **Board**: ESP32 Dev Module (or your specific ESP32 variant)
- **Upload Speed**: 115200
- **CPU Frequency**: 240MHz (WiFi/BT)
- **Flash Frequency**: 80MHz
- **Flash Mode**: QIO
- **Partition Scheme**: Default 4MB with spiffs

### 4. Upload Firmware

1. Connect ESP32 via USB
2. Select the correct COM port
3. Click Upload
4. Open Serial Monitor (115200 baud) to see sensor readings

### 5. Register Device

After uploading, register the device in the GrowSense dashboard:
1. Sign in to the dashboard
2. Use the device registration API or dashboard interface
3. Use the same `DEVICE_ID` and `API_KEY` from your `secrets.h`

## Configuration

Edit these constants at the top of `GrowSenseModule_Production.ino`:

```cpp
// Server URL - Update to your deployment URL
const char* SERVER_URL = "https://your-app.onrender.com/upload_data";

// Default sleep duration (seconds) - Can be updated remotely via server response
uint64_t sleep_duration_seconds = 30;

// WiFi connection timeout
const int WIFI_CONNECT_TIMEOUT_MS = 30000;  // 30 seconds

// HTTP timeout
const int HTTP_TIMEOUT = 15000;  // 15 seconds

// Status LED pin (set to -1 to disable)
const int STATUS_LED_PIN = 2;
```

### Remote Configuration

The firmware supports remote configuration of sleep intervals:
- Server can return `sleep_duration` in the upload response
- Valid range: 15 seconds to 3600 seconds (1 hour)
- Value is stored in ESP32 flash memory and persists across reboots

## Sensor Testing

Before deploying the full production firmware, test each sensor individually:

### Temperature & Humidity (AM2320)
```bash
# Upload and open Serial Monitor
firmware/Adafruit_AM2320.ino
```
- Verifies I2C communication
- Displays temperature and humidity readings
- Check wiring if sensor not detected

### Light Sensor (BH1750)
```bash
firmware/BH1750_Light_Sensor.ino
```
- Tests I2C communication on Bus 0
- Displays light readings in lux
- Cover sensor to verify readings change

### Soil Moisture (SEN0193)
```bash
firmware/SEN0193_Soil_Moister_Sensor.ino
```
- Displays raw ADC values and moisture percentage
- Test in air (should read ~0%) and water (should read ~100%)

### UV Sensor (GUVA-S12SD)
```bash
firmware/GUVA-S12SD_UV_Sensor.ino
```
- Displays UV Index (0-15)
- Test in sunlight vs. shade to verify readings

## Calibration

### Soil Moisture Sensor Calibration

The SEN0193 sensor requires calibration for accurate readings:

1. **Upload calibration tool:**
   ```bash
   firmware/SEN0193_Calibration.ino
   ```

2. **Calibrate dry value (0%):**
   - Keep sensor probe exposed to air
   - Record the stabilized value as `SOIL_AIR_VALUE`

3. **Calibrate wet value (100%):**
   - Submerge sensor probe in water
   - Record the stabilized value as `SOIL_WATER_VALUE`

4. **Update production firmware:**
   - Edit `GrowSenseModule_Production.ino`
   - Update these constants:
     ```cpp
     const int SOIL_AIR_VALUE = 3079;    // Your dry value
     const int SOIL_WATER_VALUE = 550;  // Your wet value
     ```

## Power Consumption

### Active Mode
- **WiFi + Sensors**: ~160-260mA
- **Duration**: ~2-5 seconds per measurement cycle

### Deep Sleep Mode
- **Current Draw**: ~10-150μA
- **Duration**: Configurable (default 30 seconds)

### Battery Life Estimation

For a 2000mAh battery:
- **Without sleep**: ~8-12 hours
- **With deep sleep (30s interval)**: ~6-12 months

**Calculation:**
- Active: 200mA × 3s = 0.6mAh per cycle
- Sleep: 50μA × 30s = 0.0004mAh per cycle
- Total per cycle: ~0.6mAh
- Cycles per day (30s interval): 2880
- Daily consumption: ~1.7mAh
- Battery life: 2000mAh / 1.7mAh/day ≈ 1176 days (3+ years)

*Note: Actual battery life depends on battery quality, temperature, and WiFi signal strength.*

## Troubleshooting

### Sensor Not Detected

**AM2320:**
- Check I2C wiring (SDA=48, SCL=35)
- Verify 3.3V power supply
- Check Serial Monitor for I2C errors

**BH1750:**
- Check I2C wiring (SDA=6, SCL=7)
- Verify I2C address (0x23)
- Check Serial Monitor for I2C errors

**Analog Sensors (Soil/UV):**
- Verify GPIO pins (Soil=20, UV=2)
- Check ADC configuration in code
- Test with multimeter if readings are 0

### WiFi Connection Issues

- Verify SSID and password in `secrets.h`
- Check WiFi signal strength (RSSI in Serial Monitor)
- Increase `WIFI_CONNECT_TIMEOUT_MS` if needed
- Check for special characters in SSID/password

### Upload Failures

- Check COM port selection
- Try different USB cable
- Press BOOT button during upload if needed
- Verify board selection matches your ESP32 variant

### Data Not Appearing in Dashboard

- Verify `SERVER_URL` is correct
- Check `DEVICE_ID` and `API_KEY` match dashboard registration
- Check Serial Monitor for HTTP response codes
- Verify device is registered to your user account

### High Power Consumption

- Ensure deep sleep is working (check Serial Monitor for sleep messages)
- Disable status LED if not needed (`STATUS_LED_PIN = -1`)
- Reduce WiFi connection timeout
- Check for code that prevents sleep (e.g., infinite loops)

## Production Firmware Features

- All 4 sensors integrated
- Deep sleep for low power
- WiFi auto-reconnect
- HTTP retry logic (3 attempts)
- Remote sleep interval configuration
- Comprehensive error handling
- Serial debugging (can be disabled)
- Status LED indicators
- Flash memory persistence for settings

## Required Hardware

- ESP32 development board (any variant)
- AM2320 temperature/humidity sensor
- BH1750 light sensor
- SEN0193 capacitive soil moisture sensor
- GUVA-S12SD UV sensor
- Jumper wires
- Optional: 2000mAh+ battery for portable operation

## Pin Connections

| Component | Pin | ESP32 GPIO |
|-----------|-----|------------|
| AM2320 SDA | I2C Bus 1 | 48 |
| AM2320 SCL | I2C Bus 1 | 35 |
| BH1750 SDA | I2C Bus 0 | 6 |
| BH1750 SCL | I2C Bus 0 | 7 |
| SEN0193 | Analog | 20 |
| GUVA-S12SD | Analog | 2 |
| Status LED | Digital | 2 (optional) |

All sensors use 3.3V power and share common ground.

## License

See main repository LICENSE file.
