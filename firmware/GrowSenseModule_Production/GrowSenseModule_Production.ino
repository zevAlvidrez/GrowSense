/*
 * GrowSense ESP32 Module - PRODUCTION FIRMWARE
 * 
 * Collects sensor data from all PCB sensors and uploads to GrowSense cloud dashboard
 * 
 * Sensors:
 * - Adafruit AM2320: Temperature & Humidity (I2C Bus 1: SDA=48, SCL=35)
 * - BH1750: Light intensity in lux (I2C Bus 0: SDA=6, SCL=7, Address=0x23)
 * - SEN0193: Soil moisture percentage (Analog: GPIO 20)
 * - GUVA-S12SD: UV Index (Analog: GPIO 2)
 * 
 * Features:
 * - Deep sleep mode for ultra-low power consumption (~10-150μA)
 * - WiFi connectivity with auto-reconnect
 * - JSON payload formatting
 * - Automatic retry on failure
 * - Status LED indicator (optional)
 * - All sensor readings in single upload
 * 
 * POWER CONSUMPTION:
 * - Active (WiFi + sensors): ~160-260mA
 * - Deep sleep: ~10-150μA 
 * - Estimated battery life (2000mAh): ~6-12 months (vs 8-12 hours without sleep)
 * 
 * Required Libraries (install via Arduino Library Manager):
 * - ArduinoJson by Benoit Blanchon (v6.x or later)
 * - Adafruit AM2320 by Adafruit
 * 
 * Built-in libraries (no installation needed):
 * - WiFi (ESP32 core)
 * - HTTPClient (ESP32 core)
 * - Wire (ESP32 core - I2C)
 * 
 * LICENSE:
 * - This firmware combines code from multiple sources:
 *   - SEN0193 sensor code based on DFRobot example (GNU Lesser General Public License)
 *   - See <http://www.gnu.org/licenses/> for details
 *   - All other code: See main repository LICENSE file
 */

#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <Wire.h>
#include <Adafruit_AM2320.h>
#include <Preferences.h>
#include "secrets.h"

// ============================================
// Configuration - EASILY CHANGEABLE
// ============================================

// Server configuration
const char* SERVER_URL = "https://growsense-wer0.onrender.com/upload_data";

// Sleep configuration
// This is the DEFAULT value if nothing is stored in flash memory
// It will be overwritten by values from the server
uint64_t sleep_duration_seconds = 30; 

// WiFi connection timeout
const int WIFI_CONNECT_TIMEOUT_MS = 30000;   // 30 seconds max for WiFi connection

// HTTP configuration
const int HTTP_TIMEOUT = 15000;  // 15 second timeout
const int MAX_RETRIES = 3;       // Number of retry attempts

// Status LED (set to -1 to disable to save power)
const int STATUS_LED_PIN = 2;    // Built-in LED on most ESP32 boards (GPIO 2)
                                 // Set to -1 if you don't want LED indicators

// Serial debugging
const bool ENABLE_SERIAL_DEBUG = true;
const long SERIAL_BAUD_RATE = 115200;

// ============================================
// Sensor Pin Definitions
// ============================================

// I2C Bus 0 (for BH1750 Light Sensor)
#define I2C0_SDA 6
#define I2C0_SCL 7
#define BH1750_ADDR 0x23  // BH1750 I2C address

// I2C Bus 1 (for AM2320 Temperature/Humidity Sensor)
#define I2C1_SDA 48
#define I2C1_SCL 35

// Analog Sensors
#define SOIL_MOISTURE_PIN 20  // SEN0193 Capacitive Soil Moisture Sensor
#define UV_SENSOR_PIN 2      // GUVA-S12SD UV Light Sensor

// ============================================
// Sensor Calibration Values
// ============================================

// SEN0193 Soil Moisture Sensor Calibration
// These values are calibrated for the sensor
const int SOIL_AIR_VALUE = 3079;    // Value when sensor is in air (dry)
const int SOIL_WATER_VALUE = 550;   // Value when sensor is in water (wet)

// ============================================
// Global Variables
// ============================================

// I2C Bus 1 for AM2320
TwoWire I2C_AM2320 = TwoWire(1);

// AM2320 Sensor Object
Adafruit_AM2320 am2320 = Adafruit_AM2320(&I2C_AM2320);

// Preferences object for storing sleep duration
Preferences preferences;

// RTC Memory (survives deep sleep)
RTC_DATA_ATTR int bootCount = 0;
RTC_DATA_ATTR int consecutiveFailures = 0;

// ============================================
// Setup Function
// ============================================

void setup() {
  // Increment boot counter
  bootCount++;
  
  // Initialize Serial for debugging
  if (ENABLE_SERIAL_DEBUG) {
    Serial.begin(SERIAL_BAUD_RATE);
    delay(500);  // Reduced delay to save power
    Serial.println();
    Serial.println("=================================");
    Serial.println("   GrowSense Production Firmware ");
    Serial.println("=================================");
    Serial.print("Boot #");
    Serial.println(bootCount);
    Serial.print("Device ID: ");
    Serial.println(DEVICE_ID);
  }

  // Load saved sleep duration
  preferences.begin("growsense", false); // Namespace "growsense", read/write mode
  sleep_duration_seconds = preferences.getULong64("sleep_sec", 30); // Default 30s if not found
  preferences.end();

  if (ENABLE_SERIAL_DEBUG) {
    Serial.print("Consecutive failures: ");
    Serial.println(consecutiveFailures);
    Serial.print("Sleep interval: ");
    Serial.print(sleep_duration_seconds);
    Serial.println(" seconds");
    Serial.println();
  }
  
  // Initialize status LED
  if (STATUS_LED_PIN >= 0) {
    pinMode(STATUS_LED_PIN, OUTPUT);
    digitalWrite(STATUS_LED_PIN, LOW);
  }
  
  // If too many consecutive failures, increase sleep time and reset counter
  if (consecutiveFailures > 5) {
    if (ENABLE_SERIAL_DEBUG) {
      Serial.println("⚠ Too many failures. Sleeping for extended period...");
    }
    consecutiveFailures = 0;
    goToSleep(sleep_duration_seconds * 5); // Sleep 5x longer
    return;
  }
  
  // LED on to indicate activity
  if (STATUS_LED_PIN >= 0) {
    digitalWrite(STATUS_LED_PIN, HIGH);
  }
  
  // Initialize sensors
  initializeSensors();
  
  // Connect to WiFi
  bool wifiConnected = connectToWiFi();
  
  if (!wifiConnected) {
    if (ENABLE_SERIAL_DEBUG) {
      Serial.println("✗ WiFi connection failed. Going to sleep...");
    }
    consecutiveFailures++;
    goToSleep(sleep_duration_seconds);
    return;
  }
  
  // Read all sensors
  if (ENABLE_SERIAL_DEBUG) {
    Serial.println("----------------------------------------");
    Serial.println("Reading sensors...");
    Serial.println("----------------------------------------");
  }
  
  float temperature = readTemperature();
  float humidity = readHumidity();
  int light = readLight();
  float soilMoisture = readSoilMoisture();
  float uvLight = readUVlight();
  
  if (ENABLE_SERIAL_DEBUG) {
    Serial.println("----------------------------------------");
    Serial.println("Sensor Readings:");
    Serial.print("  Temperature: ");
    Serial.print(temperature);
    Serial.println(" °C");
    Serial.print("  Humidity: ");
    Serial.print(humidity);
    Serial.println(" %");
    Serial.print("  Light: ");
    Serial.print(light);
    Serial.println(" lux");
    Serial.print("  Soil Moisture: ");
    Serial.print(soilMoisture);
    Serial.println(" %");
    Serial.print("  UV Index: ");
    Serial.print(uvLight, 1);
    Serial.println();
    Serial.println("----------------------------------------");
  }
  
  // Upload data to server
  bool success = uploadData(temperature, humidity, light, soilMoisture, uvLight);
  
  if (success) {
    if (ENABLE_SERIAL_DEBUG) {
      Serial.println("✓ Upload successful!");
    }
    consecutiveFailures = 0;  // Reset failure counter
  } else {
    if (ENABLE_SERIAL_DEBUG) {
      Serial.println("✗ Upload failed after retries.");
    }
    consecutiveFailures++;
  }
  
  // LED off
  if (STATUS_LED_PIN >= 0) {
    digitalWrite(STATUS_LED_PIN, LOW);
  }
  
  // Disconnect WiFi to save power
  WiFi.disconnect(true);
  WiFi.mode(WIFI_OFF);
  
  // // Calculate total wake time (millis() starts at 0 on each boot)
  // unsigned long totalWakeTime = millis();
  
  // if (ENABLE_SERIAL_DEBUG) {
  //   Serial.println("----------------------------------------");
  //   Serial.println("TIMING REPORT:");
  //   Serial.print("  Total wake time: ");
  //   Serial.print(totalWakeTime);
  //   Serial.println(" ms");
  // }
  // Go to sleep
  goToSleep(sleep_duration_seconds);
}

// ============================================
// Main Loop (Not Used in Deep Sleep Mode)
// ============================================

void loop() {
  // Loop is not used when using deep sleep
  // Device will restart from setup() after waking
}

// ============================================
// Deep Sleep Function
// ============================================

void goToSleep(uint64_t seconds) {
  if (ENABLE_SERIAL_DEBUG) {
    Serial.println("----------------------------------------");
    Serial.print("Going to deep sleep for ");
    Serial.print(seconds);
    Serial.println(" seconds...");
    Serial.println("Current consumption: ~10-150μA");
    Serial.println("========================================");
    Serial.flush();  // Wait for serial to finish
  }
  
  // Configure wake-up timer
  esp_sleep_enable_timer_wakeup(seconds * 1000000ULL);  // Convert to microseconds
  
  // Enter deep sleep
  esp_deep_sleep_start();
  
  // Code never reaches here - device resets on wake
}

// ============================================
// WiFi Functions
// ============================================

bool connectToWiFi() {
  if (ENABLE_SERIAL_DEBUG) {
    Serial.print("Connecting to WiFi: ");
    Serial.println(WIFI_SSID);
  }
  
  // Set WiFi to station mode and disconnect from any previous connection
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  
  unsigned long startAttemptTime = millis();
  int attempts = 0;
  
  while (WiFi.status() != WL_CONNECTED && 
         (millis() - startAttemptTime) < WIFI_CONNECT_TIMEOUT_MS) {
    delay(500);
    if (ENABLE_SERIAL_DEBUG) {
      Serial.print(".");
    }
    
    // Blink LED while connecting
    if (STATUS_LED_PIN >= 0) {
      digitalWrite(STATUS_LED_PIN, attempts % 2);
    }
    
    attempts++;
  }
  
  if (WiFi.status() == WL_CONNECTED) {
    if (ENABLE_SERIAL_DEBUG) {
      Serial.println();
      Serial.println("✓ WiFi connected successfully!");
      Serial.print("IP Address: ");
      Serial.println(WiFi.localIP());
      Serial.print("Signal Strength: ");
      Serial.print(WiFi.RSSI());
      Serial.println(" dBm");
      Serial.println();
    }
    return true;
  } else {
    if (ENABLE_SERIAL_DEBUG) {
      Serial.println();
      Serial.println("✗ WiFi connection timeout!");
    }
    return false;
  }
}

// ============================================
// HTTP Upload Function
// ============================================

bool uploadData(float temperature, float humidity, int light, float soilMoisture, float uvLight) {
  for (int attempt = 1; attempt <= MAX_RETRIES; attempt++) {
    if (ENABLE_SERIAL_DEBUG && attempt > 1) {
      Serial.print("Retry attempt ");
      Serial.print(attempt);
      Serial.print(" of ");
      Serial.println(MAX_RETRIES);
    }
    
    HTTPClient http;
    http.setTimeout(HTTP_TIMEOUT);
    
    // Begin connection
    http.begin(SERVER_URL);
    http.addHeader("Content-Type", "application/json");
    
    // Create JSON payload
    StaticJsonDocument<512> doc;
    doc["device_id"] = DEVICE_ID;
    doc["api_key"] = API_KEY;
    
    // Add sensor data (only include valid values)
    if (!isnan(temperature)) {
      doc["temperature"] = temperature;
    }
    if (!isnan(humidity)) {
      doc["humidity"] = humidity;
    }
    if (light >= 0) {
      doc["light"] = light;
    }
    if (!isnan(soilMoisture)) {
      doc["soil_moisture"] = soilMoisture;
    }
    if (!isnan(uvLight)) {
      doc["uv_light"] = uvLight;  // Stored in raw_json even if not displayed yet
    }
    
    // Serialize JSON to string
    String jsonPayload;
    serializeJson(doc, jsonPayload);
    
    if (ENABLE_SERIAL_DEBUG) {
      Serial.println("Sending payload:");
      Serial.println(jsonPayload);
    }
    
    // Send POST request
    int httpResponseCode = http.POST(jsonPayload);
    
    if (ENABLE_SERIAL_DEBUG) {
      Serial.print("HTTP Response Code: ");
      Serial.println(httpResponseCode);
    }
    
    // Check response
    if (httpResponseCode > 0) {
      String response = http.getString();
      
      if (ENABLE_SERIAL_DEBUG) {
        Serial.print("Server Response: ");
        Serial.println(response);
      }
      
      http.end();
      
      // Success codes: 200 (OK) or 201 (Created)
      if (httpResponseCode == 200 || httpResponseCode == 201) {
        // Check for sleep duration update
        StaticJsonDocument<512> responseDoc;
        DeserializationError error = deserializeJson(responseDoc, response);
        
        if (!error) {
          if (responseDoc.containsKey("sleep_duration")) {
            uint64_t new_sleep = responseDoc["sleep_duration"];
            
            // Validate range (15 seconds to 1 hour)
            if (new_sleep >= 15 && new_sleep <= 3600) {
              if (new_sleep != sleep_duration_seconds) {
                if (ENABLE_SERIAL_DEBUG) {
                  Serial.print("Updating sleep duration to: ");
                  Serial.println((unsigned long)new_sleep);
                }
                
                // Update global variable
                sleep_duration_seconds = new_sleep;
                
                // Save to flash
                preferences.begin("growsense", false);
                preferences.putULong64("sleep_sec", sleep_duration_seconds);
                preferences.end();
              }
            } else {
              if (ENABLE_SERIAL_DEBUG) {
                Serial.println("⚠ Received invalid sleep duration (ignored)");
              }
            }
          }
        } else {
          if (ENABLE_SERIAL_DEBUG) {
            Serial.println("⚠ Failed to parse server response JSON");
          }
        }
        
        return true;
      } else if (httpResponseCode == 401) {
        if (ENABLE_SERIAL_DEBUG) {
          Serial.println("✗ Authentication failed! Check DEVICE_ID and API_KEY in secrets.h");
        }
        return false; // Don't retry auth errors
      } else if (httpResponseCode >= 400) {
        if (ENABLE_SERIAL_DEBUG) {
          Serial.println("✗ Client error - check payload format");
        }
        return false; // Don't retry client errors
      }
    } else {
      if (ENABLE_SERIAL_DEBUG) {
        Serial.print("✗ HTTP Error: ");
        Serial.println(http.errorToString(httpResponseCode));
      }
      http.end();
    }
    
    // Wait before retry (reduced to save power)
    if (attempt < MAX_RETRIES) {
      delay(1000 * attempt);
    }
  }
  
  return false; // All retries failed
}

// ============================================
// Sensor Initialization
// ============================================

void initializeSensors() {
  if (ENABLE_SERIAL_DEBUG) {
    Serial.println("Initializing sensors...");
  }
  
  // Initialize I2C Bus 0 for BH1750 Light Sensor
  Wire.begin(I2C0_SDA, I2C0_SCL);
  
  // Initialize I2C Bus 1 for AM2320 Temperature/Humidity Sensor
  I2C_AM2320.begin(I2C1_SDA, I2C1_SCL);

//start
  // Initialize AM2320
  // if (am2320.begin()) {
  //   if (ENABLE_SERIAL_DEBUG) {
  //     Serial.println("✓ AM2320 (Temperature/Humidity) initialized");
  //   }
  // } else {
  //   if (ENABLE_SERIAL_DEBUG) {
  //     Serial.println("✗ AM2320 NOT found! Check wiring:");
  //     Serial.println("  VCC -> 3.3V");
  //     Serial.println("  GND -> GND");
  //     Serial.print("  SDA -> GPIO ");
  //     Serial.println(I2C1_SDA);
  //     Serial.print("  SCL -> GPIO ");
  //     Serial.println(I2C1_SCL);
  //   }
  // }

  //send

  // Initialize AM2320 with retry
  bool am2320_ok = false;
  for (int i = 0; i < 3 && !am2320_ok; i++) {
    if (am2320.begin()) {
      am2320_ok = true;
      if (ENABLE_SERIAL_DEBUG) Serial.println("✓ AM2320 (Temperature/Humidity) initialized");
    } else {
      delay(200);
    }
  }
  if (!am2320_ok && ENABLE_SERIAL_DEBUG) {
    Serial.println("✗ AM2320 NOT found after retries!");
  }
  
  //start
  // Initialize BH1750 Light Sensor
  // Power on and configure BH1750 - Continuous High Resolution Mode (1 lux resolution)
  // Wire.beginTransmission(BH1750_ADDR);
  // Wire.write(0x10);  // Continuous H-Resolution Mode
  // if (Wire.endTransmission() == 0) {
  //   if (ENABLE_SERIAL_DEBUG) {
  //     Serial.println("✓ BH1750 (Light) initialized");
  //   }
  // } else {
  //   if (ENABLE_SERIAL_DEBUG) {
  //     Serial.println("✗ BH1750 NOT found! Check wiring:");
  //     Serial.print("  SDA -> GPIO ");
  //     Serial.println(I2C0_SDA);
  //     Serial.print("  SCL -> GPIO ");
  //     Serial.println(I2C0_SCL);
  //     Serial.print("  Address: 0x");
  //     Serial.println(BH1750_ADDR, HEX);
  //   }
  // }

 // end

  // Initialize BH1750 Light Sensor with retry
  bool bh1750_ok = false;
  for (int i = 0; i < 3 && !bh1750_ok; i++) {
    Wire.beginTransmission(BH1750_ADDR);
    Wire.write(0x10);  // Continuous H-Resolution Mode
    if (Wire.endTransmission() == 0) {
      bh1750_ok = true;
      if (ENABLE_SERIAL_DEBUG) Serial.println("✓ BH1750 (Light) initialized");
    } else {
      delay(200);
    }
  }
  if (!bh1750_ok && ENABLE_SERIAL_DEBUG) {
    Serial.println("✗ BH1750 NOT found after retries!");
  }
  
  // Configure ADC for analog sensors
  analogReadResolution(12);  // 12-bit resolution (0-4095)
  analogSetAttenuation(ADC_11db);  // Full voltage range (0-3.3V)
  
  // Configure analog input pins
  pinMode(SOIL_MOISTURE_PIN, INPUT);
  pinMode(UV_SENSOR_PIN, INPUT);
  
  if (ENABLE_SERIAL_DEBUG) {
    Serial.print("✓ Analog sensors configured (GPIO ");
    Serial.print(SOIL_MOISTURE_PIN);
    Serial.print(" for soil, GPIO ");
    Serial.print(UV_SENSOR_PIN);
    Serial.println(" for UV)");
    Serial.println();
  }
  
  // Wait for sensors to stabilize (especially BH1750 needs ~180ms for first reading)
  delay(500);
}

// ============================================
// Sensor Reading Functions
// ============================================

/*
 * Read temperature from AM2320 sensor
 * Returns: Temperature in Celsius, or NAN if read fails
 */
// float readTemperature() {
//   float temp = am2320.readTemperature();
  
//   if (isnan(temp)) {
//     if (ENABLE_SERIAL_DEBUG) {
//       Serial.println("⚠ Failed to read temperature from AM2320");
//     }
//     return NAN;
//   }
  
//   return temp;
// }
float readTemperature() {
  for (int i = 0; i < 3; i++) {
    float temp = am2320.readTemperature();
    if (!isnan(temp)) return temp;
    delay(100);
  }
  if (ENABLE_SERIAL_DEBUG) Serial.println("⚠ Failed to read temperature from AM2320");
  return NAN;
}

/*
 * Read humidity from AM2320 sensor
 * Returns: Humidity percentage (0-100), or NAN if read fails
 */
// float readHumidity() {
//   float hum = am2320.readHumidity();
  
//   if (isnan(hum)) {
//     if (ENABLE_SERIAL_DEBUG) {
//       Serial.println("⚠ Failed to read humidity from AM2320");
//     }
//     return NAN;
//   }
  
//   return hum;
// }
float readHumidity() {
  for (int i = 0; i < 3; i++) {
    float hum = am2320.readHumidity();
    if (!isnan(hum)) return hum;
    delay(100);
  }
  if (ENABLE_SERIAL_DEBUG) Serial.println("⚠ Failed to read humidity from AM2320");
  return NAN;
}

/*
 * Read light intensity from BH1750 sensor
 * Based on BH1750_Light_Sensor.ino test code
 * Returns: Light level in lux, or -1 if read fails
 */
// int readLight() {
//   // Request 2 bytes from sensor
//   Wire.requestFrom(BH1750_ADDR, 2);
  
//   if (Wire.available() == 2) {
//     uint16_t raw = Wire.read() << 8 | Wire.read();
//     // Convert to lux (default mode divisor is 1.2)
//     uint16_t lux = raw / 1.2;
//     return lux;
//   }
  
//   if (ENABLE_SERIAL_DEBUG) {
//     Serial.println("⚠ Failed to read light from BH1750");
//   }
//   return -1;  // Return -1 if read fails
// }
int readLight() {
  for (int i = 0; i < 3; i++) {
    Wire.requestFrom(BH1750_ADDR, 2);
    if (Wire.available() == 2) {
      uint16_t raw = Wire.read() << 8 | Wire.read();
      uint16_t lux = raw / 1.2;
      return lux;
    }
    delay(100);
  }
  if (ENABLE_SERIAL_DEBUG) Serial.println("⚠ Failed to read light from BH1750");
  return -1;
}

/*
 * Read soil moisture from SEN0193 capacitive sensor
 * Based on SEN0193_Soil_Moister_Sensor.ino test code
 * 
 * GNU Lesser General Public License.
 * See <http://www.gnu.org/licenses/> for details.
 * All above must be included in any redistribution
 * 
 * Returns: Soil moisture percentage (0-100), or NAN if read fails
 */
float readSoilMoisture() {
  // Read analog value from soil moisture sensor
  int rawValue = analogRead(SOIL_MOISTURE_PIN);
  
  // Calculate moisture percentage based on calibration values
  // Map from raw ADC value to percentage
  // Dry (AirValue) = 0%, Wet (WaterValue) = 100%
  float moisturePercent;
  
  if (rawValue >= SOIL_AIR_VALUE) {
    moisturePercent = 0.0;  // Very dry (in air)
  } else if (rawValue <= SOIL_WATER_VALUE) {
    moisturePercent = 100.0;  // Saturated (in water)
  } else {
    // Linear mapping between AirValue and WaterValue
    moisturePercent = map(rawValue, SOIL_AIR_VALUE, SOIL_WATER_VALUE, 0, 100);
    moisturePercent = constrain(moisturePercent, 0, 100);
  }
  
  return moisturePercent;
}

/*
 * Read UV Index from GUVA-S12SD sensor
 * Based on GUVA-S12SD_UV_Sensor.ino test code
 * 
 * Sensor detects 240-370nm (UVB and most UVA spectrum)
 * Output: Vo = 4.3 * Diode-Current-in-uA
 * UV Index = Output Voltage / 0.1V
 * 
 * Returns: UV Index (0-15+), or NAN if read fails
 */
float readUVlight() {
  // Read analog value
  int sensorValue = analogRead(UV_SENSOR_PIN);
  
  // Convert to voltage (ESP32 ADC: 12-bit, 0-4095 = 0-3.3V)
  float voltage = sensorValue * (3.3 / 4095.0);
  
  // Calculate UV Index (UV Index = Voltage / 0.1V)
  float uvIndex = voltage / 0.1;
  
  // Clamp to reasonable range (0-15)
  if (uvIndex < 0) uvIndex = 0;
  if (uvIndex > 15) uvIndex = 15;
  
  return uvIndex;
}

