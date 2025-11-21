# GrowSense Production Firmware

Complete production firmware for ESP32 with all PCB sensors integrated.

## Quick Start

1. **Install Required Libraries** (via Arduino Library Manager):
   - `ArduinoJson` by Benoit Blanchon (v6.x or later)
   - `Adafruit AM2320` by Adafruit

2. **Configure Secrets**:
   ```bash
   cp secrets.h.example secrets.h
   ```
   Then edit `secrets.h` with your WiFi credentials, device ID, and API key.

3. **Open in Arduino IDE**:
   - Open `GrowSenseModule_Production.ino`
   - Select your ESP32 board (Tools → Board → ESP32 Arduino → ESP32 Dev Module)
   - Select your port
   - Click Upload

4. **Monitor Output**:
   - Open Serial Monitor (115200 baud)
   - Watch for sensor readings and upload confirmations

## Configuration

Edit these constants at the top of `GrowSenseModule_Production.ino`:

- `SLEEP_DURATION_SECONDS` - Measurement interval (default: 30 seconds)
- `SERVER_URL` - Backend API endpoint
- `STATUS_LED_PIN` - LED pin (set to -1 to disable)

## Sensors

- **AM2320**: Temperature & Humidity (I2C Bus 1: SDA=48, SCL=35)
- **BH1750**: Light intensity (I2C Bus 0: SDA=6, SCL=7)
- **SEN0193**: Soil moisture (Analog: GPIO 20)
- **GUVA-S12SD**: UV Index (Analog: GPIO 2)

## Power Consumption

- Active: ~160-260mA
- Deep Sleep: ~10-150μA
- Estimated battery life (2000mAh): ~6-12 months

## Troubleshooting

See the main `MODULE_SETUP_GUIDE.md` in the parent directory for detailed setup instructions.

