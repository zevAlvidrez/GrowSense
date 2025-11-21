#include <Wire.h>
#include <Adafruit_AM2320.h>

// Define custom I2C pins
#define I2C_SDA 48
#define I2C_SCL 35

Adafruit_AM2320 am2320;

void setup() {
  Serial.begin(115200);
  delay(2000);
  
  Serial.println("AM2320 Sensor Test");
  Serial.println("==================\n");

  // Initialize I2C with custom pins
  Wire.begin(I2C_SDA, I2C_SCL);
  
  // Try to initialize sensor
  if (am2320.begin()) {
    Serial.println("✓ AM2320 found!");
  } else {
    Serial.println("✗ AM2320 NOT found!");
    Serial.println("Check wiring:");
    Serial.println("  VCC -> 3.3V");
    Serial.println("  GND -> GND");
    Serial.println("  SDA -> GPIO 8 (or 21)");
    Serial.println("  SCL -> GPIO 9 (or 22)");
  }
  
  Serial.println("\nReading sensor...\n");
}

void loop() {
  float temp = am2320.readTemperature();
  float hum = am2320.readHumidity();
  
  Serial.print("Temperature: ");
  Serial.print(temp);
  Serial.println(" °C");
  
  Serial.print("Humidity: ");
  Serial.print(hum);
  Serial.println(" %\n");
  
  delay(2000);
}