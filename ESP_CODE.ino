#include <WiFi.h>
#include <ESP32Servo.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <ESPAsyncWebServer.h>

// WiFi Credentials
const char* ssid = "TP-Link_EA52";          // Replace with your WiFi SSID
const char* password = "71063508";  // Replace with your WiFi password

// Flask Server URL
const String FLASK_SERVER = "http://192.168.0.104:5000/update_slot";  // Replace with your Flask server IP

// Supabase Direct URL (Optional - for direct Supabase communication)
// const String SUPABASE_URL = "https://your-supabase-url.supabase.co/rest/v1/bookings?select=*";

// Pins Configuration
const int irPins[] = {32, 33, 25, 26};     // IR sensors for A1-A4
const int redPins[] = {27, 14, 12, 13};   // Red LEDs
const int greenPins[] = {18, 19, 21, 22}; // Green LEDs
const int servoPin = 23;                 // Servo motor for gate
const int buzzerPin = 5;                 // Buzzer

// Create servo object
Servo gateServo;

// Create web server on port 80
AsyncWebServer server(80);

// Store previous slot states
bool previousStates[4] = {LOW, LOW, LOW, LOW};

void setup() {
  // Start serial communication
  Serial.begin(115200);
  
  // Connect to WiFi
  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) {
    delay(1000);
    Serial.println("Connecting to WiFi...");
  }
  Serial.println("Connected to WiFi");
  Serial.println(WiFi.localIP());

  // Attach servo motor
  gateServo.attach(servoPin);
  
  // Set pin modes
  pinMode(buzzerPin, OUTPUT);
  
  for (int i = 0; i < 4; i++) {
    pinMode(irPins[i], INPUT);
    pinMode(redPins[i], OUTPUT);
    pinMode(greenPins[i], OUTPUT);
  }

  // Set up gate control endpoint
  server.on("/gate", HTTP_POST, [](AsyncWebServerRequest *request){},
    NULL,
    handleGate
  );

  // Set up slot status endpoint
  server.on("/slots", HTTP_GET, [](AsyncWebServerRequest *request){
    StaticJsonDocument<200> doc;
    JsonArray slots = doc.createNestedArray("slots");
    
    for (int i = 0; i < 4; i++) {
      JsonObject slot = slots.createNestedObject();
      slot["slot_id"] = "A" + String(i + 1);
      
      // Read current state
      bool occupied = digitalRead(irPins[i]) == HIGH;
      slot["status"] = occupied ? "Occupied" : "Available";
    }
    
    String response;
    serializeJson(doc, response);
    request->send(200, "application/json", response);
  });

  // Start web server
  server.begin();
  Serial.println("Web server started");
}

void loop() {
  // Monitor parking slots
  for (int i = 0; i < 4; i++) {
    // Read sensor value
    bool currentState = digitalRead(irPins[i]);
    
    // Only update if state has changed
    if (currentState != previousStates[i]) {
      previousStates[i] = currentState;
      
      // Update LED indicators
      digitalWrite(redPins[i], currentState ? HIGH : LOW);
      digitalWrite(greenPins[i], currentState ? LOW : HIGH);
      
      // Send update to server - ✅ INVERTED STATUS
      sendStatus("A" + String(i + 1), currentState ? "Available" : "Occupied");
      
      // Small delay between slot updates
      delay(100);
    }
  }
  
  // Small delay to prevent excessive CPU usage
  delay(100);
}

// Function to send slot status to Flask server
void sendStatus(String slot, String status) {
  HTTPClient http;
  http.begin(FLASK_SERVER);
  http.addHeader("Content-Type", "application/json");

  // Create JSON payload
  StaticJsonDocument<128> doc;
  doc["slot_id"] = slot;
  doc["status"] = status;
  
  String payload;
  serializeJson(doc, payload);

  // Send POST request
  int httpResponseCode = http.POST(payload);
  
  if (httpResponseCode > 0) {
    Serial.print("HTTP Response code: ");
    Serial.println(httpResponseCode);
  } else {
    Serial.print("Error code: ");
    Serial.println(httpResponseCode);
  }
  
  http.end();
}

// Function to handle gate control
void handleGate(AsyncWebServerRequest *request, uint8_t *data, size_t len, size_t index, size_t total) {
  StaticJsonDocument<200> doc;
  DeserializationError error = deserializeJson(doc, data);

  if (error) {
    Serial.print("JSON parsing failed: ");
    Serial.println(error.c_str());
    request->send(400, "text/plain", "JSON Error");
    return;
  }

  const char* action = doc["action"];
  if (strcmp(action, "open") == 0) {
    Serial.println("Opening gate...");
    
    // Activate buzzer
    tone(buzzerPin, 1000, 500);  // Buzzer on pin 5
    
    // Open gate (90 degrees)
    gateServo.write(90);
    
    // Keep gate open for 5 seconds
    delay(5000);
    
    // Close gate (0 degrees)
    gateServo.write(0);
    
    request->send(200, "text/plain", "Gate opened");
  } else {
    Serial.println("Invalid gate action");
    request->send(400, "text/plain", "Invalid action");
  }
}