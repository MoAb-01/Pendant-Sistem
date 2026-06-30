#include <FastLED.h>
#include <Wire.h>
#include <Adafruit_PWMServoDriver.h>

// --- Pin Definitions ---
#define RELAY_PIN 3      // Pump Relay (Wired NC)
#define LED_PIN 6        // WS2812B Data Pin
#define NUM_LEDS 148     // Number of LEDs in strip

// --- Component Instances ---
CRGB leds[NUM_LEDS];
Adafruit_PWMServoDriver pca = Adafruit_PWMServoDriver(0x40);

// --- Servo Configuration ---
#define SERVOMIN 160
#define SERVOMAX 520
int servo[16];

// System State
bool systemActive = false;

void setup() {
  Serial.begin(9600);
  
  // LED Setup (Initially RED/Standby)
  FastLED.addLeds<WS2812B, LED_PIN, GRB>(leds, NUM_LEDS);
  fill_solid(leds, NUM_LEDS, CRGB::Red);
  FastLED.show();

  // Relay Setup
  pinMode(RELAY_PIN, OUTPUT);
  digitalWrite(RELAY_PIN, HIGH); // Assuming HIGH turns NC to Open (Pump OFF)

  // PCA9685 Setup
  Wire.begin();
  pca.begin();
  pca.setOscillatorFrequency(27000000);
  pca.setPWMFreq(50);
  delay(10);
  
  // Set initial servo positions to 0
  for(int i=0; i<16; i++) {
    servo[i] = 0;
    pca.setPWM(i, 0, angleToPulse(0)); 
  }
  
  Serial.println("Mega Ready. Waiting for Pi/Web Authorization...");
}

uint16_t angleToPulse(int a) {
  a = constrain(a, 0, 180);
  return map(a, 0, 180, SERVOMIN, SERVOMAX);
}

// 🚀 NON-BLOCKING LED FLASH
// Keeps the delay extremely short so the web sliders don't lag
void flashLEDGreen() {
  fill_solid(leds, NUM_LEDS, CRGB::Green);
  FastLED.show();
  delay(150); 
  fill_solid(leds, NUM_LEDS, CRGB::Blue);
  FastLED.show();
}

// Emergency Reset function to fold the arm back to safety
void resetAllArms() {
  int safeChannels[] = {0, 1, 9, 10, 11, 12, 14};
  for (int ch : safeChannels) {
    pca.setPWM(ch, 0, angleToPulse(0));
  }
}

void processCommand(String cmd) {
  cmd.trim();
  cmd.toUpperCase();

  // ==========================================
  // 1. MASTER SYSTEM CONTROLS (Bypasses Lock)
  // ==========================================
  if (cmd == "SYSTEM_READY") {
    systemActive = true;
    fill_solid(leds, NUM_LEDS, CRGB::Blue);
    FastLED.show();
    Serial.println("System Authorized.");
    return; 
  }
  else if (cmd == "SYSTEM_OFF") {
    systemActive = false;
    digitalWrite(RELAY_PIN, HIGH); // Kill Pump
    resetAllArms();                // Fold arm back
    fill_solid(leds, NUM_LEDS, CRGB::Red); // Return to standby
    FastLED.show();
    Serial.println("System Shutdown via UI/Voice.");
    return;
  }

  // IGNORING ALL OTHER COMMANDS IF SYSTEM IS LOCKED
  if (!systemActive) return;

  // ==========================================
  // 2. WEB SLIDER CONTROLS (Direct Servo Parsing)
  // Format: SERVO:port:aci (Example: SERVO:14:90)
  // ==========================================
  if (cmd.startsWith("SERVO:")) {
    int firstColon = cmd.indexOf(':');
    int secondColon = cmd.indexOf(':', firstColon + 1);
    
    if (firstColon > 0 && secondColon > 0) {
      int port = cmd.substring(firstColon + 1, secondColon).toInt();
      int aci = cmd.substring(secondColon + 1).toInt();
      
      pca.setPWM(port, 0, angleToPulse(aci));
      Serial.println("Slider Executed: Port " + String(port) + " -> " + String(aci));
    }
    return; // No green flash for sliders to keep movement perfectly smooth
  }

// ==========================================
  // 3. MECHANICAL & RELAY CONTROLS
  // ==========================================
  if(cmd == "POMPAC") {
    digitalWrite(RELAY_PIN, LOW);
    Serial.println("Pump Activated");
  } 
  else if (cmd == "POMPKAPAT") {
    digitalWrite(RELAY_PIN, HIGH);
    Serial.println("Pump Deactivated");
  }
  else if (cmd.indexOf("KOL GEL") >= 0 || cmd.indexOf("KOL GIT") >= 0) {
    int angle = (cmd.indexOf("GEL") >= 0) ? 90 : 0;
    
    // Emergency full reset
    if (cmd == "KOL GIT") {
        resetAllArms();
        Serial.println("All Arms Reset");
    }
    // Specific arm targeting using Safe ASCII
    else if (cmd.indexOf("ARM1") >= 0) {
      pca.setPWM(0, 0, angleToPulse(angle));
      pca.setPWM(1, 0, angleToPulse(angle));
    } 
    else if (cmd.indexOf("ARM2") >= 0) {
      pca.setPWM(9, 0, angleToPulse(angle));
      pca.setPWM(10, 0, angleToPulse(angle)); 
      pca.setPWM(11, 0, angleToPulse(angle)); 
    }
    else if (cmd.indexOf("ARM3") >= 0) {
      pca.setPWM(13, 0, angleToPulse(angle)); // Connected to port 13
    }
    Serial.println("Arm Moved via Safe ASCII");
  }
  
  // Flash green only for discrete commands (Voice or Buttons), not sliders
  flashLEDGreen();
}

void loop() {
  if (Serial.available()) {
    String command = Serial.readStringUntil('\n');
    processCommand(command);
  }
}
