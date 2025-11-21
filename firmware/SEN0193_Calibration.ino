/*
 * ESP32-S3 SEN0193 Soil Moisture Sensor - CALIBRATION TOOL
 * 
 * This script helps you calibrate your soil moisture sensor
 * Follow the instructions in the Serial Monitor
 */


#define SOIL_SENSOR_PIN 1  // Change to your ADC-capable pin (try GPIO 1-10)

void setup() {
  Serial.begin(115200);
  delay(2000);
  
  // Configure ADC for full voltage range
  analogSetAttenuation(ADC_11db);
  analogReadResolution(12);
  pinMode(SOIL_SENSOR_PIN, INPUT);
  
  // Print calibration instructions
  Serial.println("========================================");
  Serial.println("SOIL MOISTURE SENSOR CALIBRATION TOOL");
  Serial.println("========================================");
  Serial.println();
  Serial.println("INSTRUCTIONS:");
  Serial.println();
  Serial.println("STEP 1: Calibrate DRY value (0% humidity)");
  Serial.println("  - Keep the sensor probe EXPOSED TO AIR");
  Serial.println("  - Watch the values below stabilize");
  Serial.println("  - Record the value as 'Value_1' (AirValue)");
  Serial.println();
  Serial.println("STEP 2: Calibrate WET value (100% humidity)");
  Serial.println("  - Take a cup of water");
  Serial.println("  - Insert probe INTO WATER up to the RED LINE");
  Serial.println("  - DO NOT submerge past the red line!");
  Serial.println("  - Watch the values below stabilize");
  Serial.println("  - Record the value as 'Value_2' (WaterValue)");
  Serial.println();
  Serial.println("STEP 3: Calculate ranges");
  Serial.println("  - Dry range: (Value_1, Value_1 - (Value_1-Value_2)/3]");
  Serial.println("  - Wet range: middle third");
  Serial.println("  - Water range: (Value_2 + (Value_1-Value_2)/3, Value_2]");
  Serial.println();
  Serial.println("========================================");
  Serial.println("READING SENSOR VALUES...");
  Serial.println("========================================");
  Serial.println();
  delay(2000);
}

void loop() {
  int sensorValue = analogRead(SOIL_SENSOR_PIN);
  
  Serial.print("Sensor Value: ");
  Serial.println(sensorValue);
  
  delay(500);  // Read twice per second for stable readings
}