/***************************************************
 * GrowSense Prototype: ESP32 + Adafruit IO
 * Sends temperature, humidity, and light data
 ***************************************************/

#include "WiFi.h"
#include "AdafruitIO_WiFi.h"
#include "secrets.h"  // contains WIFI_SSID, WIFI_PASS, IO_USERNAME, IO_KEY

AdafruitIO_WiFi io(IO_USERNAME, IO_KEY, WIFI_SSID, WIFI_PASS);

// Create feeds for each sensor
AdafruitIO_Feed *temperature = io.feed("temperature");
AdafruitIO_Feed *humidity    = io.feed("humidity");
AdafruitIO_Feed *light       = io.feed("light_intensity");

void setup() {
  Serial.begin(115200);
  Serial.print("Connecting to Adafruit IO");

  io.connect();

  // Wait for connection
  while (io.status() < AIO_CONNECTED) {
    Serial.print(".");
    delay(500);
  }

  Serial.println("\nConnected to Adafruit IO!");
}

void loop() {
  // Keep the connection alive
  io.run();

  // --- Example sensor readings (replace with actual sensors later) ---
  float temp = random(200, 300) / 10.0;   // fake temp: 20.0–30.0°C
  float hum  = random(400, 600) / 10.0;   // fake humidity: 40–60%
  float lux  = random(100, 900);          // fake light intensity
  // -------------------------------------------------------------------

  // Send data to Adafruit IO
  temperature->save(temp);
  humidity->save(hum);
  light->save(lux);

  Serial.printf("Sent -> Temp: %.1f  Humidity: %.1f  Light: %.0f\n", temp, hum, lux);

  delay(5000); // update every 5 seconds
}

