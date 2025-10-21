# Firmware

This folder contains the Arduino sketch for GrowSense.

## Files
- `GrowSenseFirmware/` — main Arduino sketch (`GrowSenseModule.ino`)
- `libraries/` — optional: copy library versions you want to pin

## Required board (example)
- Board: ESP32 Dev Module (choose the matching variant in Arduino IDE)

## Required libraries
Install via Arduino Library Manager:
- Adafruit AM2320
- PubSubClient (MQTT)
- WiFi (included in ESP32 core)
- Any other libraries used

## Secrets
Create `secrets.h` in the same folder as `GrowSenseModule.ino`. Do **not** commit it.
A `secrets.h.example` is provided.
