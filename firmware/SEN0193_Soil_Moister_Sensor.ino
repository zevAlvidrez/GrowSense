/*
 * ESP32-S3 SEN0193 Capacitive Soil Moisture Sensor Reader
 * Reads analog sensor value and prints moisture level to Serial Monitor
 * 
 * Based on DFRobot SEN0193 example code
 * Adapted for ESP32-S3 with analog input on GPIO 40
 */

#define SOIL_SENSOR_PIN 20  // Analog pin for soil moisture sensor

// Calibration values - adjust these for your sensor
const int AirValue = 3079;    // Value when sensor is in air (dry)
const int WaterValue = 550;  // Value when sensor is in water (wet)

int intervals = (AirValue - WaterValue) / 3;
int soilMoistureValue = 0;

void setup() {
  Serial.begin(115200);
  delay(1000);
  
  Serial.println("ESP32-S3 SEN0193 Soil Moisture Sensor Reader");
  Serial.println("==========================================");
  Serial.println();

  // pinMode(SOIL_SENSOR_PIN, INPUT);
  
  // Configure ADC resolution (ESP32 default is 12-bit, 0-4095)
  analogReadResolution(12);
  
  Serial.println("Sensor initialized on GPIO");
  Serial.println();
  Serial.println("Calibration Values:");
  Serial.print("  Air Value (dry): ");
  Serial.println(AirValue);
  Serial.print("  Water Value (wet): ");
  Serial.println(WaterValue);
  Serial.println();
}

void loop() {
  // Read analog value from soil moisture sensor
  soilMoistureValue = analogRead(SOIL_SENSOR_PIN);
  
  // Print raw value
  Serial.print("Raw Value: ");
  Serial.print(soilMoistureValue);
  Serial.print(" | Status: ");
  
  // Determine moisture level
  if (soilMoistureValue > WaterValue && soilMoistureValue < (WaterValue + intervals)) {
    Serial.println("Very Wet");
  }
  else if (soilMoistureValue > (WaterValue + intervals) && soilMoistureValue < (AirValue - intervals)) {
    Serial.println("Wet");
  }
  else if (soilMoistureValue < AirValue && soilMoistureValue > (AirValue - intervals)) {
    Serial.println("Dry");
  }
  else if (soilMoistureValue >= AirValue) {
    Serial.println("Very Dry (in air)");
  }
  else if (soilMoistureValue <= WaterValue) {
    Serial.println("Saturated (in water)");
  }
  
  delay(1000);  // Read every second
}