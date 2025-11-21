/*
 * GrowSense ESP32 Module - LOW POWER VERSION
 * 
 * Collects sensor data and uploads to GrowSense cloud dashboard
 * https://growsense-wer0.onrender.com
 * 
 * Features:
 * - Deep sleep mode for ultra-low power consumption (~10-150μA)
 * - WiFi connectivity with auto-reconnect
 * - JSON payload formatting
 * - Automatic retry on failure
 * - Status LED indicator (optional)
 * 
 * POWER CONSUMPTION:
 * - Active (WiFi + sensors): ~160-260mA
 * - Deep sleep: ~10-150μA
 * - Estimated battery life (2000mAh): ~6-12 months (vs 8-12 hours without sleep)
 * 
 * Required Libraries (install via Arduino Library Manager):
 * - ArduinoJson by Benoit Blanchon (v6.x or later)
 * 
 * Built-in libraries (no installation needed):
 * - WiFi (ESP32 core)
 * - HTTPClient (ESP32 core)
 */

#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include "secrets.h"
#include <Adafruit_AM2320.h>
#include <BH1750.h>
#include <Wire.h>

Adafruit_AM2320 am2320;
BH1750 lightMeter;

// ============================================
// Configuration
// ============================================

// Server configuration
const char* SERVER_URL = "https://growsense-wer0.onrender.com/upload_data";



// Device credentials (defined in secrets.h)
// WIFI_SSID, WIFI_PASSWORD, DEVICE_ID, API_KEY

// Sleep configuration
const uint64_t SLEEP_DURATION_SECONDS = 15;  // Sleep for 15 seconds between readings
                                               // Adjust this value based on your needs:
                                               // 60 = 1 minute
                                               // 300 = 5 minutes  
                                               // 900 = 15 minutes
                                               // 3600 = 1 hour

// WiFi connection timeout
const int WIFI_CONNECT_TIMEOUT_MS = 30000;   // 30 seconds max for WiFi connection

// HTTP configuration
const int HTTP_TIMEOUT = 15000;  // 15 second timeout
const int MAX_RETRIES = 3;       // Reduced retries to save power

// Status LED (set to -1 to disable to save power)
const int STATUS_LED_PIN = 2;    // Built-in LED on most ESP32 boards (GPIO 2)
                                 // Set to -1 if you don't want LED indicators

// Serial debugging
const bool ENABLE_SERIAL_DEBUG = true;
const long SERIAL_BAUD_RATE = 115200;

// ============================================
// RTC Memory (survives deep sleep)
// ============================================
// Use this to track upload failures across sleep cycles
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
    Serial.println("   GrowSense ESP32 - Low Power   ");
    Serial.println("=================================");
    Serial.print("Boot #");
    Serial.println(bootCount);
    Serial.print("Consecutive failures: ");
    Serial.println(consecutiveFailures);
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
    goToSleep(SLEEP_DURATION_SECONDS * 5); // Sleep 5x longer
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
    goToSleep(SLEEP_DURATION_SECONDS);
    return;
  }
  
  // Read all sensors
  float temperature = readTemperature();
  float humidity = readHumidity();
  int light = readLight();
  float soilMoisture = readSoilMoisture();
  float UVlight = readUVlight();
  
  // Upload data to server
  bool success = uploadData(temperature, humidity, light, soilMoisture, UVlight);
  
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
  
  // Go to sleep
  goToSleep(SLEEP_DURATION_SECONDS);
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
  
  // Optional: Configure other wake sources
  // esp_sleep_enable_ext0_wakeup(GPIO_NUM_33, 1);  // Wake on button press
  // esp_sleep_enable_ext1_wakeup(BUTTON_PIN_BITMASK, ESP_EXT1_WAKEUP_ANY_HIGH);
  
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
  Serial.println("Scanning for networks...");
  int n = WiFi.scanNetworks();
  for (int i = 0; i < n; i++) {
    Serial.println(WiFi.SSID(i));
  }
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  
  // Optional: Set WiFi power save mode to aggressive for faster sleep
  // WiFi.setSleep(true);  // Enable WiFi sleep mode
  
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

bool uploadData(float temperature, float humidity, int light, float soilMoisture, float UVlight) {
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
    
    // Add sensor data (only include non-NaN values)
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
    if (!isnan(UVlight)){
      doc["UVlight"] = UVlight;
    }
    
    // Add boot count for debugging
    doc["boot_count"] = bootCount;
    
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
        return true;
      } else if (httpResponseCode == 401) {
        if (ENABLE_SERIAL_DEBUG) {
          Serial.println("✗ Authentication failed! Check DEVICE_ID and API_KEY in secrets.h");
        }
        return false;
      } else if (httpResponseCode >= 400) {
        if (ENABLE_SERIAL_DEBUG) {
          Serial.println("✗ Client error - check payload format");
        }
        return false;
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
  
  return false;
}

// ============================================
// Sensor Reading Functions
// ============================================

void initializeSensors() {

  /*
   * TODO: Initialize your sensors here
   * 
   * Example:
   * - Set up DHT sensor
   * - Configure ADC pins for analog sensors
   * - Initialize I2C devices
   * - Set pin modes
   * 
   * Example code:
   * pinMode(SOIL_MOISTURE_PIN, INPUT);
   * dht.begin();
   */

  if (ENABLE_SERIAL_DEBUG) {
    Serial.println("Initializing sensors...");
    // Try to initialize sensor
    Wire.begin(1, 2);
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

    //Initialize BH1750
    Wire1.begin(10, 11);
    if (lightMeter.begin(BH1750::CONTINUOUS_HIGH_RES_MODE, 0x23, &Wire1)){
      Serial.prinln("✓  BH1750 found!"):
    } else {
      Serial.println("✗ BH1750 NOT found!");
      Serial.println("Check wiring:");
      Serial.println("  VCC -> 3.3V (or 5V)");
      Serial.println("  GND -> GND");
      Serial.println("  SDA -> GPIO 8");
      Serial.println("  SCL -> GPIO 9");
      Serial.println("  ADDR -> GND (for default 0x23 address)");
    }
  }
}

float readTemperature() {
  /*
   * TODO: Read temperature sensor
   * 
   * Example for DHT22:
   * float temp = dht.readTemperature();
   * if (isnan(temp)) {
   *   Serial.println("Failed to read temperature!");
   *   return NAN;
   * }
   * return temp;
   */
  float temp = am2320.readTemperature();
  
  if (ENABLE_SERIAL_DEBUG) {
    Serial.print("Temp: ");
    Serial.print(temp);
    Serial.println(" °C");
  }
  
  return temp;
}

float readHumidity() {
  /*
   * TODO: Read humidity sensor
   * 
   * Example for DHT22:
   * float hum = dht.readHumidity();
   * if (isnan(hum)) {
   *   Serial.println("Failed to read humidity!");
   *   return NAN;
   * }
   * return hum;
   */
  float hum = am2320.readHumidity();
    
  if (ENABLE_SERIAL_DEBUG) {
    Serial.print("Humidity: ");
    Serial.print(hum);
    Serial.println(" %");
  }
  
  return hum;
}

int readLight() {
  /*
   * TODO: Read light sensor
   * 
   * Example for photoresistor:
   * int rawValue = analogRead(LIGHT_SENSOR_PIN);
   * int lux = map(rawValue, 0, 4095, 0, 1000); // Convert to approximate lux
   * return lux;
   * 
   * Example for BH1750:
   * int lux = lightMeter.readLightLevel();
   * return lux;
   */
  float lux = lightMeter.readLightLevel();
    
  if (ENABLE_SERIAL_DEBUG) {
    Serial.print("Light: ");
    Serial.print(lux);
    Serial.println(" lux");
  }
  
  return (int)lux;
}
const int SOIL_MOISTURE_PIN = 32; //Change accordingly to actualy pin
const int DRY_VALUE = 0; //will need to get an actual reading in dry air
const int WET_VALUE = 0; //will need to get an actual reading in water

float readSoilMoisture() {
  /*
   * TODO: Read soil moisture sensor
   * 
   * Example for capacitive sensor:
   * int rawValue = analogRead(SOIL_MOISTURE_PIN);
   * // Calibrate these values based on your sensor
   * const int DRY_VALUE = 3000;    // Value in dry air
   * const int WET_VALUE = 1200;    // Value in water
   * float moisturePercent = map(rawValue, DRY_VALUE, WET_VALUE, 0, 100);
   * moisturePercent = constrain(moisturePercent, 0, 100);
   * return moisturePercent;
   */
  
  // // Dummy data for testing
  // float dummySoil = 30.0 + random(0, 400) / 10.0; // Random between 30-70%
  
  // if (ENABLE_SERIAL_DEBUG) {
  //   Serial.print("Soil Moisture: ");
  //   Serial.print(dummySoil);
  //   Serial.println(" % (dummy data)");
  // }
  int rawValue = analogRead(SOIL_MOISTURE_PIN);

  float moisturePercent = map(rawValue, DRY_VALUE, WET_VALUE, 0, 100);
  moisturePercent = constrain(moisturePercent, 0, 100);

  if (ENABLE_SERIAL_DEBUG) {
    Serial.print("Soil Moisture: ");
    Serial.print(rawValue);
    Serial.print(" raw (");
    Serial.print(moisturePercent);
    Serial.println(" %)");
  }
  return moisturePercent;
}
const int UV_PIN = 41;
float readUVlight(){
  int rawValue = analogRead(UV_PIN);
  float voltage = rawValue * (3.3 / 4095.0);  // For 3.3V reference
  float UVlight = voltage / 0.1;
  
  if (ENABLE_SERIAL_DEBUG) {
    Serial.print("UV: ");
    Serial.print(voltage, 2);
    Serial.print(" V (UV Index: ");
    Serial.print(UVlight, 1);
    Serial.println(")");
  }
  return UVlight;
}

// ============================================
// Optional: Light Sleep Alternative
// ============================================

/*
 * If you need faster wake times (milliseconds instead of seconds),
 * consider using light sleep instead:
 * 
 * void goToLightSleep(uint64_t seconds) {
 *   esp_sleep_enable_timer_wakeup(seconds * 1000000ULL);
 *   esp_light_sleep_start();
 *   // Code continues here after wake (doesn't reset)
 * }
 * 
 * Light sleep power consumption: ~0.8mA (vs ~10-150μA for deep sleep)
 * Wake time: <1ms (vs ~100-300ms for deep sleep)
 */