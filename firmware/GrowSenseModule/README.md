# GrowSense ESP32 Module

Production-ready firmware for ESP32 to collect sensor data and upload to GrowSense dashboard.

## Features

- ✅ WiFi connectivity with automatic reconnection
- ✅ Secure API key authentication
- ✅ Periodic data upload (configurable interval)
- ✅ JSON payload formatting
- ✅ Automatic retry on failure with exponential backoff
- ✅ Status LED indicator
- ✅ Comprehensive serial debugging
- ✅ Modular sensor functions (easy to customize)

## Quick Start

### 1. Hardware Requirements

- **ESP32 Development Board** (any variant)
- **Sensors** (optional for testing - uses dummy data):
  - Temperature/Humidity sensor (DHT11, DHT22, or BME280)
  - Light sensor (photoresistor or BH1750)
  - Soil moisture sensor (capacitive or resistive)
- **USB cable** for programming

### 2. Software Requirements

**Arduino IDE Setup:**

1. Install [Arduino IDE](https://www.arduino.cc/en/software) (1.8.x or 2.x)

2. Add ESP32 Board Support:
   - Go to **File → Preferences**
   - Add this URL to "Additional Board Manager URLs":
     ```
     https://raw.githubusercontent.com/espressif/arduino-esp32/gh-pages/package_esp32_index.json
     ```
   - Go to **Tools → Board → Boards Manager**
   - Search for "ESP32" and install "esp32 by Espressif Systems"

3. Install Required Libraries:
   - Open **Sketch → Include Library → Manage Libraries**
   - Search and install:
     - **ArduinoJson** by Benoit Blanchon (v6.x or later)

### 3. Configuration

#### Create secrets.h file:

```bash
# In the GrowSenseModule directory:
cp secrets.h.example secrets.h
```

Then edit `secrets.h` with your credentials:

```cpp
#define WIFI_SSID       "YourActualWiFiName"
#define WIFI_PASSWORD   "YourActualWiFiPassword"
#define DEVICE_ID       "esp32_greenhouse_01"
#define API_KEY         "your-secure-random-api-key"
```

**Important:** 
- The `DEVICE_ID` and `API_KEY` must match an entry in the server's `device_keys.json`
- Never commit `secrets.h` to version control (already in `.gitignore`)

#### Register Device on Server:

**Step 1:** Add your device to `/device_keys.json` on the server:

```json
{
  "esp32_greenhouse_01": { "api_key": "your-secure-random-api-key" },
  "test_device": { "api_key": "test-key-12345" }
}
```

**Step 2:** Register the device to your user account:

After signing in to the dashboard, register the device via API:

```bash
curl -X POST https://your-app-name.onrender.com/devices/register \
  -H "Authorization: Bearer YOUR_FIREBASE_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "device_id": "esp32_greenhouse_01",
    "api_key": "your-secure-random-api-key",
    "name": "Greenhouse Sensor"
  }'
```

**Get Firebase Token:** Open browser console (F12) and run:
```javascript
firebase.auth().currentUser.getIdToken().then(console.log)
```

**Note:** Devices must be registered to a user account before they can upload data. See `MODULE_SETUP_GUIDE.md` for complete setup instructions.

### 4. Upload to ESP32

1. Open `GrowSenseModule.ino` in Arduino IDE
2. Select your board:
   - **Tools → Board → ESP32 Arduino → ESP32 Dev Module**
3. Select your port:
   - **Tools → Port → (your ESP32's port)**
4. Click **Upload** (→ button)
5. Open **Serial Monitor** (Ctrl+Shift+M or Tools → Serial Monitor)
6. Set baud rate to **115200**

### 5. Monitor Output

You should see:

```
=================================
   GrowSense ESP32 Module v1.0   
=================================

Connecting to WiFi: YourWiFiName
........
✓ WiFi connected successfully!
IP Address: 192.168.1.123
Signal Strength: -45 dBm

Initializing sensors...
⚠ NOTE: Sensor initialization code not yet implemented
⚠ Will return dummy data until sensors are configured
Setup complete. Starting main loop...

----------------------------------------
Starting data collection and upload...
Temperature: 24.3 °C (dummy data)
Humidity: 67.2 % (dummy data)
Light: 523 lux (dummy data)
Soil Moisture: 45.8 % (dummy data)
Sending payload:
{"device_id":"esp32_greenhouse_01","api_key":"...","temperature":24.3,"humidity":67.2,"light":523,"soil_moisture":45.8}
HTTP Response Code: 201
Server Response: {"success":true,"message":"Data uploaded successfully",...}
✓ Upload successful!
Next upload in ~60 seconds
----------------------------------------
```

## Configuration Options

Edit these constants in `GrowSenseModule.ino`:

```cpp
// Upload interval (milliseconds)
const unsigned long UPLOAD_INTERVAL = 60000;  // Default: 60 seconds

// HTTP timeout
const int HTTP_TIMEOUT = 15000;  // Default: 15 seconds

// Retry attempts
const int MAX_RETRIES = 3;  // Default: 3 attempts

// Status LED pin (set to -1 to disable)
const int STATUS_LED_PIN = 2;  // Default: GPIO 2 (built-in LED)

// Serial debugging
const bool ENABLE_SERIAL_DEBUG = true;  // Set to false for production
```

## Adding Your Sensors

The firmware has placeholder functions ready for your sensor code:

### 1. Initialize Sensors

Edit `initializeSensors()`:

```cpp
void initializeSensors() {
  // Example: DHT22 sensor
  pinMode(DHT_PIN, INPUT);
  dht.begin();
  
  // Example: Soil moisture (analog)
  pinMode(SOIL_MOISTURE_PIN, INPUT);
  
  Serial.println("Sensors initialized!");
}
```

### 2. Temperature Sensor

Edit `readTemperature()`:

```cpp
float readTemperature() {
  float temp = dht.readTemperature();
  if (isnan(temp)) {
    Serial.println("Failed to read temperature!");
    return NAN;
  }
  return temp;
}
```

### 3. Humidity Sensor

Edit `readHumidity()`:

```cpp
float readHumidity() {
  float hum = dht.readHumidity();
  if (isnan(hum)) {
    Serial.println("Failed to read humidity!");
    return NAN;
  }
  return hum;
}
```

### 4. Light Sensor

Edit `readLight()`:

```cpp
int readLight() {
  int rawValue = analogRead(LIGHT_SENSOR_PIN);
  int lux = map(rawValue, 0, 4095, 0, 1000);
  return lux;
}
```

### 5. Soil Moisture Sensor

Edit `readSoilMoisture()`:

```cpp
float readSoilMoisture() {
  int rawValue = analogRead(SOIL_MOISTURE_PIN);
  const int DRY_VALUE = 3000;
  const int WET_VALUE = 1200;
  float percent = map(rawValue, DRY_VALUE, WET_VALUE, 0, 100);
  return constrain(percent, 0, 100);
}
```

## Troubleshooting

### WiFi Won't Connect

- Check SSID and password in `secrets.h`
- Make sure WiFi is 2.4GHz (ESP32 doesn't support 5GHz)
- Try moving closer to router

### Upload Fails with 401 Error

- Check `DEVICE_ID` and `API_KEY` match server's `device_keys.json`
- Verify no typos in credentials

### Upload Fails with HTTP Error

- Check internet connection
- Verify server URL is correct
- Check if Render service is awake (free tier sleeps after 15 min)

### Serial Monitor Shows Garbage

- Make sure baud rate is set to 115200
- Press the ESP32 reset button

### Compilation Errors

- Make sure ArduinoJson library is installed
- Check that ESP32 board support is properly installed
- Verify `secrets.h` file exists

## Testing Without Sensors

The firmware includes dummy data generation, so you can test the complete upload pipeline without physical sensors connected. Perfect for:

- Testing WiFi connectivity
- Verifying API credentials
- Checking dashboard integration
- Debugging upload logic

Once everything works with dummy data, add your real sensors!

## API Endpoint

The module uploads to:
```
POST https://growsense-wer0.onrender.com/upload_data
```

Payload format:
```json
{
  "device_id": "esp32_greenhouse_01",
  "api_key": "your-api-key",
  "temperature": 24.5,
  "humidity": 65.2,
  "light": 450,
  "soil_moisture": 42.1
}
```

## Power Saving (Optional)

For battery-powered deployments, you can add deep sleep:

```cpp
// At end of loop(), after successful upload:
ESP.deepSleep(UPLOAD_INTERVAL * 1000); // Sleep in microseconds
```

Note: Deep sleep requires hardware modification (connect RST to GPIO for wake-up).

## Support

- Dashboard: https://growsense-wer0.onrender.com
- Repository: https://github.com/zevAlvidrez/GrowSense
- Issues: Submit via GitHub Issues

## License

See main repository LICENSE file.

