#include <HTTPClient.h>
#include <WiFi.h>
#include <WiFiClientSecure.h> // Added for HTTPS support
#include <Wire.h>
#include <LiquidCrystal_I2C.h>
#include <HX711.h>
#include <TinyGPS++.h>
#include <EEPROM.h>

const char* ssid = "MOSES";
const char* password = "mmmmmmmm";

// Updated URL to HTTPS PythonAnywhere domain
const char* serverURL = "https://basili.pythonanywhere.com/api/iot/";

#define HX_DT 4
#define HX_SCK 5
#define GPS_RX 17
#define GPS_TX 16
#define TRIG1 18
#define ECHO1 19
#define TRIG2 26
#define ECHO2 25
#define I2C_SDA 21
#define I2C_SCL 22

#define EEPROM_SIZE 64
#define CAL_FACTOR_ADDR 0

const float GENERAL_HEIGHT = 35.0;
const float RECYCLE_HEIGHT = 30.0;
const int FULL_LEVEL = 90;

float calibration_factor = -7050.0;

LiquidCrystal_I2C lcd(0x27, 20, 4);
HX711 scale;
TinyGPSPlus gps;
HardwareSerial GPS(2);

unsigned long lastRead = 0;
const unsigned long READ_INTERVAL = 8000;

float readDistance(int trig, int echo) {
  digitalWrite(trig, LOW);
  delayMicroseconds(2);
  digitalWrite(trig, HIGH);
  delayMicroseconds(10);
  digitalWrite(trig, LOW);
  long d = pulseIn(echo, HIGH, 30000);
  if (d == 0) return -1;
  return d * 0.0343 / 2.0;
}

float readAverageDistance(int trig, int echo) {
  float sum = 0;
  int ok = 0;
  for (int i = 0; i < 10; i++) {
    float v = readDistance(trig, echo);
    if (v > 2 && v < 400) {
      sum += v;
      ok++;
    }
    delay(20);
  }
  if (ok == 0) return -1;
  return sum / ok;
}

float levelPercent(float dist, float h) {
  if (dist < 0) return -1;
  float p = ((h - dist) / h) * 100.0;
  if (p < 0) p = 0;
  if (p > 100) p = 100;
  return p;
}

float readWeight() {
  if (scale.is_ready()) {
    float w = scale.get_units(15);
    if (w < 0) w = 0;
    return w;
  } else {
    Serial.println("HX711 not found.");
    return 0;
  }
}

void updateLCD(float w, float r, float kg) {
  lcd.clear();
  lcd.setCursor(0, 0); lcd.print("General: "); lcd.print(w, 0); lcd.print("%");
  lcd.setCursor(0, 1); lcd.print("Recycle: "); lcd.print(r, 0); lcd.print("%");
  lcd.setCursor(0, 2); lcd.print("Weight : "); lcd.print(kg, 2); lcd.print("g");
  lcd.setCursor(0, 3);
  if (w >= FULL_LEVEL && r >= FULL_LEVEL) lcd.print("WARNING:BOTH FULL");
  else if (w >= FULL_LEVEL) lcd.print("GENERAL BIN FULL");
  else if (r >= FULL_LEVEL) lcd.print("RECYCLE BIN FULL");
  else lcd.print("Status: NORMAL");
}

void initWiFi() {
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print("Connecting WiFi...");
  WiFi.begin(ssid, password);
  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 20) {
    delay(500);
    Serial.print(".");
    attempts++;
  }
  lcd.clear();
  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\nWiFi Connected!");
    Serial.println(WiFi.localIP());
    lcd.setCursor(0, 0);
    lcd.print("WiFi Connected!");
    lcd.setCursor(0, 1);
    lcd.print(WiFi.localIP().toString());
  } else {
    lcd.print("WiFi Failed!");
  }
  delay(2000);
}

void setup() {
  Serial.begin(115200);
  Wire.begin(I2C_SDA, I2C_SCL);
  lcd.init();
  lcd.backlight();
  lcd.setCursor(0, 0);
  lcd.print("   SMART BIN v1.0   ");
  delay(1000);

  EEPROM.begin(EEPROM_SIZE);
  initWiFi();

  pinMode(TRIG1, OUTPUT);
  pinMode(ECHO1, INPUT);
  pinMode(TRIG2, OUTPUT);
  pinMode(ECHO2, INPUT);

  float saved_calibration;
  EEPROM.get(CAL_FACTOR_ADDR, saved_calibration);
  if (!isnan(saved_calibration) && saved_calibration != 0 && saved_calibration != -1.0) {
    calibration_factor = saved_calibration;
  }

  scale.begin(HX_DT, HX_SCK);
  scale.set_scale(calibration_factor);
  scale.tare();

  GPS.begin(9600, SERIAL_8N1, GPS_RX, GPS_TX);
  Serial.println("Smart Bin Setup Complete.");
  delay(1000);
  lcd.clear();
}

void loop() {
  while (GPS.available() > 0) {
    gps.encode(GPS.read());
  }

  if (millis() - lastRead >= READ_INTERVAL) {
    lastRead = millis();

    if (WiFi.status() != WL_CONNECTED) {
      Serial.println("WiFi disconnected! Reconnecting...");
      WiFi.disconnect();
      delay(1000);
      WiFi.begin(ssid, password);
      delay(3000);
      return;
    }

    float d1 = readAverageDistance(TRIG1, ECHO1);
    float d2 = readAverageDistance(TRIG2, ECHO2);
    float waste = levelPercent(d1, GENERAL_HEIGHT);
    float recycle = levelPercent(d2, RECYCLE_HEIGHT);
    float weight = readWeight();

    updateLCD(waste, recycle, weight);

    double lat = -1, lon = -1;
    if (gps.location.isValid()) {
      lat = gps.location.lat();
      lon = gps.location.lng();
    }

    Serial.printf("General Level: %.1f%%  Recycle: %.1f%%  Weight: %.2fg\n", waste, recycle, weight);
    Serial.printf("Lat: %.6f  Lon: %.6f\n", lat, lon);

    String payload = "{";
    payload += "\"bin_id\":\"BIN001\",";
    payload += "\"waste_level\":" + String(waste, 1) + ",";
    payload += "\"recycle_level\":" + String(recycle, 1) + ",";
    payload += "\"recycle_weight\":" + String(weight, 2) + ",";
    payload += "\"latitude\":" + String(lat, 6) + ",";
    payload += "\"longitude\":" + String(lon, 6);
    payload += "}";

    Serial.println("Payload: " + payload);

    // Setup SSL / HTTPS connection
    WiFiClientSecure client;
    client.setInsecure(); // Allows HTTPS requests without hardcoding CA certificates

    HTTPClient http;
    http.begin(client, serverURL);
    http.addHeader("Content-Type", "application/json");
    http.setTimeout(10000);

    int httpResponseCode = http.POST(payload);

    if (httpResponseCode > 0) {
      Serial.print("Server OK: ");
      Serial.println(httpResponseCode);
    } else {
      Serial.print("HTTP Error: ");
      Serial.println(http.errorToString(httpResponseCode));
    }
    http.end();
  }
}
