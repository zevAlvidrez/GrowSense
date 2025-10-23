/*
 * GrowSense ESP32 Module
 * 
 * Collects sensor data and uploads to GrowSense cloud dashboard
 * https://growsense-wer0.onrender.com
 * 
 * Features:
 * - WiFi connectivity with auto-reconnect
 * - Periodic sensor data upload
 * - JSON payload formatting
 * - Automatic retry on failure
 * - Status LED indicator (optional)
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

Adafruit_AM2320 am2320;

// ============================================
// Configuration
// ============================================

// Server configuration
const char* SERVER_URL = "https://growsense-wer0.onrender.com/upload_data";

const int SOLAR_PIN = 1;  // Analog input pin (GPIO 34)

// Device credentials (defined in secrets.h)
// WIFI_SSID, WIFI_PASSWORD, DEVICE_ID, API_KEY

// Upload timing
const unsigned long UPLOAD_INTERVAL = 20;  // 60 seconds (in milliseconds)

// HTTP configuration
const int HTTP_TIMEOUT = 15000;  // 15 second timeout
const int MAX_RETRIES = 3;       // Number of retry attempts

// Status LED (set to -1 to disable)
const int STATUS_LED_PIN = 2;    // Built-in LED on most ESP32 boards (GPIO 2)
                                 // Set to -1 if you don't want LED indicators

// Serial debugging
const bool ENABLE_SERIAL_DEBUG = true;
const long SERIAL_BAUD_RATE = 115200;

// ============================================
// Global Variables
// ============================================

unsigned long lastUploadTime = 0;
unsigned long wifiReconnectTime = 0;
const unsigned long WIFI_RECONNECT_INTERVAL = 30000; // Try to reconnect every 30 seconds

// ============================================
// Setup Function
// ============================================

void setup() {
  // Initialize Serial for debugging
  if (ENABLE_SERIAL_DEBUG) {
    Serial.begin(SERIAL_BAUD_RATE);
    delay(1000);
    Serial.println();
    Serial.println("=================================");
    Serial.println("   GrowSense ESP32 Module v1.0   ");
    Serial.println("=================================");
    Serial.println();
    Serial.println("Solar Cell Monitor Started");
    Serial.println("Reading every 5 seconds...\n");
  }
  
  // Initialize status LED
  if (STATUS_LED_PIN >= 0) {
    pinMode(STATUS_LED_PIN, OUTPUT);
    digitalWrite(STATUS_LED_PIN, LOW);
  }
  
  // Initialize sensors
  initializeSensors();
  
  // Connect to WiFi
  connectToWiFi();
  
  // Blink LED to indicate successful setup
  if (STATUS_LED_PIN >= 0) {
    for (int i = 0; i < 3; i++) {
      digitalWrite(STATUS_LED_PIN, HIGH);
      delay(200);
      digitalWrite(STATUS_LED_PIN, LOW);
      delay(200);
    }
  }
  
  if (ENABLE_SERIAL_DEBUG) {
    Serial.println("Setup complete. Starting main loop...");
    Serial.println();
  }
}

// ============================================
// Main Loop
// ============================================

void loop() {
  // Check WiFi connection
  if (WiFi.status() != WL_CONNECTED) {
    if (ENABLE_SERIAL_DEBUG) {
      Serial.println("WiFi connection lost. Attempting to reconnect...");
    }
    
    // Only try to reconnect every WIFI_RECONNECT_INTERVAL to avoid blocking
    if (millis() - wifiReconnectTime > WIFI_RECONNECT_INTERVAL) {
      connectToWiFi();
      wifiReconnectTime = millis();
    }
    
    delay(1000);
    return;
  }
  
  // Check if it's time to upload data
  unsigned long currentTime = millis();
  
  // Handle millis() overflow (happens after ~50 days)
  if (currentTime < lastUploadTime) {
    lastUploadTime = 0;
  }
  
  if (currentTime - lastUploadTime >= UPLOAD_INTERVAL) {
    if (ENABLE_SERIAL_DEBUG) {
      Serial.println("----------------------------------------");
      Serial.println("Starting data collection and upload...");
    }
    
    // LED on to indicate activity
    if (STATUS_LED_PIN >= 0) {
      digitalWrite(STATUS_LED_PIN, HIGH);
    }
    
    // Read all sensors
    float temperature = readTemperature();
    float humidity = readHumidity();
    int light = readLight();
    float soilMoisture = readSoilMoisture();
    
    // Upload data to server
    bool success = uploadData(temperature, humidity, light, soilMoisture);
    
    if (success) {
      lastUploadTime = currentTime;
      if (ENABLE_SERIAL_DEBUG) {
        Serial.println("✓ Upload successful!");
      }
    } else {
      if (ENABLE_SERIAL_DEBUG) {
        Serial.println("✗ Upload failed after retries.");
      }
      // Don't update lastUploadTime so we'll try again sooner
    }
    
    // LED off
    if (STATUS_LED_PIN >= 0) {
      digitalWrite(STATUS_LED_PIN, LOW);
    }
    
    if (ENABLE_SERIAL_DEBUG) {
      unsigned long nextUpload = (UPLOAD_INTERVAL - (millis() - lastUploadTime)) / 1000;
      Serial.print("Next upload in ~");
      Serial.print(nextUpload);
      Serial.println(" seconds");
      Serial.println("----------------------------------------");
      Serial.println();
    }
  }
  
  // Small delay to prevent watchdog issues
  delay(100);
}

// ============================================
// WiFi Functions
// ============================================

void connectToWiFi() {
  if (ENABLE_SERIAL_DEBUG) {
    Serial.print("Connecting to WiFi: ");
    Serial.println(WIFI_SSID);
  }
  
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  
  int attempts = 0;
  const int MAX_WIFI_ATTEMPTS = 20; // 20 attempts = 10 seconds
  
  while (WiFi.status() != WL_CONNECTED && attempts < MAX_WIFI_ATTEMPTS) {
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
  } else {
    if (ENABLE_SERIAL_DEBUG) {
      Serial.println();
      Serial.println("✗ WiFi connection failed!");
      Serial.println("Will retry in 30 seconds...");
    }
  }
  
  if (STATUS_LED_PIN >= 0) {
    digitalWrite(STATUS_LED_PIN, LOW);
  }
}

// ============================================
// HTTP Upload Function
// ============================================

bool uploadData(float temperature, float humidity, int light, float soilMoisture) {
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
    
    // Optional: Add timestamp (server will add one if not provided)
    // doc["timestamp"] = getTimestamp(); // Implement if you have RTC
    
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
    
    // Wait before retry
    if (attempt < MAX_RETRIES) {
      delay(2000 * attempt); // Exponential backoff: 2s, 4s, 6s
    }
  }
  
  return false; // All retries failed
}

// ============================================
// Sensor Reading Functions (TO BE IMPLEMENTED)
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
    Serial.print("Temperature: ");
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
    Serial.println(" %\n");
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


  int rawValue = analogRead(SOLAR_PIN);
  
  // Convert to voltage (ESP32S3 ADC: 0-2.5)
  float light_voltage = rawValue * (2.5 / 4095.0);

  float lux = light_voltage * 1000.0;
    
  if (ENABLE_SERIAL_DEBUG) {
    // Print results
  Serial.print("Raw Value: ");
  Serial.print(rawValue);
  Serial.print("  |  Voltage: ");
  Serial.print(light_voltage, 2);  // 2 decimal places
  Serial.println(" V");
  }
  
  return lux;
}

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
  
  return 0;
}

// ============================================
// Optional: Timestamp Function (if you have RTC)
// ============================================

/*
String getTimestamp() {
  // TODO: Implement if you have a Real-Time Clock module
  // Return ISO 8601 format: "2024-10-22T12:34:56Z"
  
  // Example with NTP (requires additional setup):
  // time_t now = time(nullptr);
  // struct tm* timeinfo = gmtime(&now);
  // char timestamp[25];
  // strftime(timestamp, sizeof(timestamp), "%Y-%m-%dT%H:%M:%SZ", timeinfo);
  // return String(timestamp);
  
  return ""; // Server will generate timestamp if not provided
}
*/
