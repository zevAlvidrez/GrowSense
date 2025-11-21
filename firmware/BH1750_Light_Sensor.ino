/*
 * ESP32-S3 BH1750 Light Sensor - TEST SCRIPT
 * Reads light intensity (lux) over I2C and prints to Serial Monitor
 */

#include <Wire.h>

#define BH1750_ADDR 0x23  // BH1750 I2C address (0x23 or 0x5C depending on ADDR pin)
#define SDA_PIN 6         // Change to your SDA pin
#define SCL_PIN 7         // Change to your SCL pin

void setup() {
  Serial.begin(115200);
  delay(1000);
  
  Serial.println("========================================");
  Serial.println("BH1750 LIGHT SENSOR TEST");
  Serial.println("========================================");
  Serial.println();
  
  // Initialize I2C
  Wire.begin(SDA_PIN, SCL_PIN);
  
  Serial.println("I2C Initialized");
  Serial.print("SDA Pin: GPIO ");
  Serial.println(SDA_PIN);
  Serial.print("SCL Pin: GPIO ");
  Serial.println(SCL_PIN);
  Serial.println();
  
  // Power on and configure BH1750
  // Continuous High Resolution Mode (1 lux resolution)
  Wire.beginTransmission(BH1750_ADDR);
  Wire.write(0x10);  // Continuous H-Resolution Mode
  if (Wire.endTransmission() == 0) {
    Serial.println("BH1750 sensor initialized successfully!");
  } else {
    Serial.println("ERROR: Could not find BH1750 sensor!");
    Serial.println("Check wiring and I2C address (0x23 or 0x5C)");
  }
  
  Serial.println();
  Serial.println("========================================");
  Serial.println("READING LIGHT LEVELS...");
  Serial.println("========================================");
  Serial.println();
  
  delay(180);  // Wait for first measurement
}

void loop() {
  uint16_t lightLevel = readBH1750();
  
  Serial.print("Light Level: ");
  Serial.print(lightLevel);
  Serial.println(" lux");
  
  delay(1000);  // Read every second
}

uint16_t readBH1750() {
  // Request 2 bytes from sensor
  Wire.requestFrom(BH1750_ADDR, 2);
  
  if (Wire.available() == 2) {
    uint16_t raw = Wire.read() << 8 | Wire.read();
    // Convert to lux (default mode divisor is 1.2)
    return raw / 1.2;
  }
  
  return 0;  // Return 0 if read fails
}