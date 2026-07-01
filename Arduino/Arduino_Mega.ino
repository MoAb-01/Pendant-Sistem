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

// --- Helper Prototypes ---
uint16_t angleToPulse(int a);
void resetAllArms();
void flashLEDGreen();

void setup() {
  Serial.begin(9600);
  
  // 1. Initialize Outputs immediately
  pinMode(RELAY_PIN, OUTPUT);
  digitalWrite(RELAY_PIN, HIGH); // Force Pump OFF (Relay NC to Open)
  
  // 2. Initialize PCA9685
  Wire.begin();
  pca.begin();
  pca.setOscillatorFrequency(27000000);
  pca.setPWMFreq(50);
  
  // 3. Force Reset ALL Servos to Home (Angle 0)
  for(int i=0; i<16; i++) {
    pca.setPWM(i, 0, angleToPulse(0)); 
  }
  
  // 4. Initialize LEDs
  FastLED.addLeds<WS2812B, LED_PIN, GRB>(leds, NUM_LEDS);
  FastLED.setBrightness(50); 
  fill_solid(leds, NUM_LEDS, CRGB::Red); // Indicate system is STANDBY/RESET
  FastLED.show();
  
  // 5. Final Delay to let hardware settle
  delay(1000); 
  
  Serial.println("Mega Ready. All arms homed, Pump OFF.");
}

void processCommand(String cmd) {
  cmd.trim();
  cmd.toUpperCase();

  // 1. MASTER SYSTEM CONTROLS
  if (cmd == "SYSTEM_READY") {
    systemActive = true;
    fill_solid(leds, NUM_LEDS, CRGB::Blue);
    FastLED.show();
    Serial.println("System Authorized.");
    return; 
  }
  else if (cmd == "SYSTEM_OFF") {
    systemActive = false;
    digitalWrite(RELAY_PIN, HIGH); 
    resetAllArms(); 
    fill_solid(leds, NUM_LEDS, CRGB::Red); 
    FastLED.show();
    Serial.println("System Shutdown via UI/Voice.");
    return;
  }

  if (!systemActive) return;

  // 2. WEB SLIDER CONTROLS
  if (cmd.startsWith("SERVO:")) {
    int firstColon = cmd.indexOf(':');
    int secondColon = cmd.indexOf(':', firstColon + 1);
    
    if (firstColon > 0 && secondColon > 0) {
      int port = cmd.substring(firstColon + 1, secondColon).toInt();
      int aci = cmd.substring(secondColon + 1).toInt();
      pca.setPWM(port, 0, angleToPulse(aci));
      Serial.println("Slider Executed: Port " + String(port) + " -> " + String(aci));
    }
    return;
  }

  // 🔴 BLUE AND PURPLE LED İÇİN EKLENMESİ GEREKEN KISIM
  if (cmd == "LED_BLUE") {
    fill_solid(leds, NUM_LEDS, CRGB::Blue);
    FastLED.show();
    Serial.println("Mod: Calisma (Mavi)");
    return; // Sadece ışık değiştiği için yeşil flaş atmasına gerek yok
  }
  else if (cmd == "LED_PURPLE") {
    fill_solid(leds, NUM_LEDS, CRGB::Purple); // Sterilizasyon rengi
    FastLED.show();
    Serial.println("Mod: Sterilizasyon (Mor)");
    return;
  }

  // 3. MECHANICAL & RELAY CONTROLS
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
    
    if (cmd == "KOL GIT") {
        resetAllArms();
        Serial.println("All Arms Reset");
    }
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
      pca.setPWM(13, 0, angleToPulse(angle));
    }
    Serial.println("Arm Moved via Safe ASCII");
  }
  
  flashLEDGreen();
}

void loop() {
  if (Serial.available()) {
    String command = Serial.readStringUntil('\n');
    processCommand(command);
  }
}

// --- FULL FUNCTION DEFINITIONS (DON'T DELETE THESE!) ---

uint16_t angleToPulse(int a) {
  a = constrain(a, 0, 180);
  return map(a, 0, 180, SERVOMIN, SERVOMAX);
}

void resetAllArms() {
  int safeChannels[] = {0, 1, 9, 10, 11, 12, 14};
  for (int ch : safeChannels) {
    pca.setPWM(ch, 0, angleToPulse(0));
  }
}

void flashLEDGreen() {
  fill_solid(leds, NUM_LEDS, CRGB::Green);
  FastLED.show();
  delay(150); 
  fill_solid(leds, NUM_LEDS, CRGB::Blue);
  FastLED.show();
}
