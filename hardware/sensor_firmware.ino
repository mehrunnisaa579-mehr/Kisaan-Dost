/*
 * ====================================================================
 * KisaanDost — ESP32 IoT Sensor Firmware
 * ====================================================================
 * Hardware Wiring:
 *   - DHT11 Data Pin   --> ESP32 GPIO4 (powered from 3.3V & GND)
 *   - HW-330 Analog Out--> ESP32 GPIO34 (powered from 3.3V & GND)
 *
 * Required Libraries (Install via Arduino IDE Library Manager):
 *   1. "DHT sensor library" by Adafruit
 *   2. "Adafruit Unified Sensor" (dependency for DHT library)
 *   3. WiFi.h (Built-in ESP32 core)
 *   4. HTTPClient.h (Built-in ESP32 core)
 * ====================================================================
 */

#include <WiFi.h>
#include <HTTPClient.h>
#include <DHT.h>

// ═════════════════════════════════════════════════════════════════════
// EDIT BEFORE UPLOADING (Configuration Constants)
// ═════════════════════════════════════════════════════════════════════
const char* WIFI_SSID     = "YOUR_WIFI_SSID";       // EDIT: Your local Wi-Fi SSID
const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";   // EDIT: Your local Wi-Fi Password

// SERVER_URL must match backend PC's local IP address (e.g. 192.168.1.50:8000)
// Same IP as frontend/services/api.js BASE_URL
const char* SERVER_URL    = "http://192.168.1.X:8000/iot/reading"; // EDIT BEFORE UPLOADING

const char* DEVICE_ID     = "field_1";              // Default device identifier

// CALIBRATE by testing actual dry vs wet soil using HW-330 sensor:
// In completely dry air/soil, raw ADC is around 4095.
// In water/wet soil, raw ADC drops to ~1500.
const int SOIL_DRY_RAW    = 4095;                   // CALIBRATE: Dry soil ADC reading
const int SOIL_WET_RAW    = 1500;                   // CALIBRATE: Wet soil ADC reading
// ═════════════════════════════════════════════════════════════════════

// Hardware Pin Definitions
#define DHTPIN 4          // GPIO4 connected to DHT11 Data pin
#define DHTTYPE DHT11     // DHT sensor model (DHT11)
#define SOIL_PIN 34       // GPIO34 connected to HW-330 Analog Output pin

DHT dht(DHTPIN, DHTTYPE);

// Non-blocking timer variables
unsigned long lastSendTime = 0;
const unsigned long SEND_INTERVAL_MS = 10000; // Send telemetry every 10 seconds

void setup() {
  Serial.begin(115200);
  delay(1000);
  Serial.println("\n[KisaanDost IoT] Initializing ESP32 Sensor Unit...");

  // Initialize DHT11 sensor
  dht.begin();
  Serial.println("[DHT11] Sensor initialized on GPIO4.");

  // Configure HW-330 ADC pin
  pinMode(SOIL_PIN, INPUT);
  Serial.println("[HW-330] Soil moisture sensor configured on GPIO34.");

  // Connect to WiFi
  Serial.print("[WiFi] Connecting to ");
  Serial.println(WIFI_SSID);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  int retries = 0;
  while (WiFi.status() != WL_CONNECTED && retries < 20) {
    delay(500);
    Serial.print(".");
    retries++;
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\n[WiFi] Connected successfully!");
    Serial.print("[WiFi] ESP32 IP Address: ");
    Serial.println(WiFi.localIP());
  } else {
    Serial.println("\n[WiFi] Connection timeout. Will retry automatically during main loop.");
  }
}

void loop() {
  unsigned long currentMillis = millis();

  // Millis-based non-blocking 10-second interval check
  if (currentMillis - lastSendTime >= SEND_INTERVAL_MS) {
    lastSendTime = currentMillis;

    // 1. Read DHT11 Temperature & Humidity
    float tempC = dht.readTemperature();
    float humidityPct = dht.readHumidity();

    // Check for sensor read failures
    if (isnan(tempC) || isnan(humidityPct)) {
      Serial.println("[ERROR] Failed to read from DHT11 sensor! Skipping this cycle.");
      return;
    }

    // 2. Read HW-330 Soil Moisture ADC and map to percentage (0 - 100%)
    int rawSoilVal = analogRead(SOIL_PIN);
    float soilMoisturePct = map(rawSoilVal, SOIL_DRY_RAW, SOIL_WET_RAW, 0, 100);
    soilMoisturePct = constrain(soilMoisturePct, 0.0, 100.0);

    Serial.printf("[SENSOR READ] Temp: %.1f C | Humidity: %.1f %% | Raw Soil: %d | Moisture: %.1f %%\n",
                  tempC, humidityPct, rawSoilVal, soilMoisturePct);

    // 3. Ensure WiFi connection is active (reconnect if disconnected)
    if (WiFi.status() != WL_CONNECTED) {
      Serial.println("[WiFi] Connection lost. Attempting reconnection...");
      WiFi.disconnect();
      WiFi.reconnect();
      delay(2000);
      if (WiFi.status() != WL_CONNECTED) {
        Serial.println("[WiFi] Reconnection failed. Skipping HTTP POST.");
        return;
      }
      Serial.println("[WiFi] Reconnected!");
    }

    // 4. Construct JSON payload and POST to backend SERVER_URL
    HTTPClient http;
    http.begin(SERVER_URL);
    http.addHeader("Content-Type", "application/json");

    String jsonPayload = "{";
    jsonPayload += "\"device_id\":\"" + String(DEVICE_ID) + "\",";
    jsonPayload += "\"soil_moisture\":" + String(soilMoisturePct, 1) + ",";
    jsonPayload += "\"temperature\":" + String(tempC, 1) + ",";
    jsonPayload += "\"humidity\":" + String(humidityPct, 1);
    jsonPayload += "}";

    Serial.print("[HTTP] Sending POST to ");
    Serial.println(SERVER_URL);
    Serial.println("[HTTP] Payload: " + jsonPayload);

    int httpResponseCode = http.POST(jsonPayload);

    if (httpResponseCode > 0) {
      String response = http.getString();
      Serial.printf("[HTTP] Success! Response Code: %d | Body: %s\n", httpResponseCode, response.c_str());
    } else {
      Serial.printf("[HTTP ERROR] POST failed, error code / msg: %s\n", http.errorToString(httpResponseCode).c_str());
    }

    http.end(); // Free resources
  }
}
