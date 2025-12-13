/*
 * ESP32-S3 GUVA-S12SD Analog UV Light Sensor - TEST SCRIPT
 * Reads UV light intensity and calculates UV Index
 * 
 * Sensor detects 240-370nm (UVB and most UVA spectrum)
 * Output: Vo = 4.3 * Diode-Current-in-uA
 * UV Index = Output Voltage / 0.1V
 */

#define UV_SENSOR_PIN 2  // Change to your ADC-capable pin (GPIO 1-10)

void setup() {
  Serial.begin(115200);
  delay(1000);
  
  Serial.println("========================================");
  Serial.println("GUVA-S12SD UV LIGHT SENSOR TEST");
  Serial.println("========================================");
  Serial.println();
  
  // Configure ADC for full voltage range (0-3.3V)
  pinMode(UV_SENSOR_PIN, INPUT);
  analogSetAttenuation(ADC_11db);
  analogReadResolution(12);
  
  Serial.print("UV Sensor Pin: GPIO ");
  Serial.println(UV_SENSOR_PIN);
  Serial.println();
  Serial.println("UV Index Reference:");
  Serial.println("  0-2   : Low");
  Serial.println("  3-5   : Moderate");
  Serial.println("  6-7   : High");
  Serial.println("  8-10  : Very High");
  Serial.println("  11+   : Extreme");
  Serial.println();
  Serial.println("========================================");
  Serial.println("READING UV LEVELS...");
  Serial.println("========================================");
  Serial.println();
}

void loop() {
  // Read analog value
  int sensorValue = analogRead(UV_SENSOR_PIN);
  
  // Convert to voltage (ESP32 ADC: 12-bit, 0-4095 = 0-3.3V)
  float voltage = sensorValue * (3.3 / 4095.0);
  
  // Calculate UV Index (UV Index = Voltage / 0.1V)
  float uvIndex = voltage / 0.1;
  
  // Print results
  Serial.print("Raw ADC: ");
  Serial.print(sensorValue);
  Serial.print(" | Voltage: ");
  Serial.print(voltage, 2);
  Serial.print("V | UV Index: ");
  Serial.print(uvIndex, 1);
  Serial.print(" (");
  
  // Print UV level description
  if (uvIndex < 3) {
    Serial.print("Low");
  } else if (uvIndex < 6) {
    Serial.print("Moderate");
  } else if (uvIndex < 8) {
    Serial.print("High");
  } else if (uvIndex < 11) {
    Serial.print("Very High");
  } else {
    Serial.print("Extreme");
  }
  
  Serial.println(")");
  
  delay(1000);  // Read every second
}