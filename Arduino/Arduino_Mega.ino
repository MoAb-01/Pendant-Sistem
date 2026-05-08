#include <FastLED.h>
#include <Wire.h>
#include <Adafruit_PWMServoDriver.h>

// --- Pin Definitions ---
#define RELAY_PIN 3      // Pump Relay (Wired NC)
#define LED_PIN 6        // WS2812B Data Pin
#define NUM_LEDS 3       // Number of LEDs in strip

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
  
  // LED Setup (Initially RED)
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
  
  for(int i=0; i<16; i++) servo[i] = 0;
  Serial.println("Mega Ready. Waiting for Pi Authorization...");
}

uint16_t angleToPulse(int a) {
  a = constrain(a, 0, 180);
  return map(a, 0, 180, SERVOMIN, SERVOMAX);
}

// Visual feedback for successful command
void flashLEDGreen() {
  for(int i=0; i<2; i++) {
    fill_solid(leds, NUM_LEDS, CRGB::Green);
    FastLED.show();
    delay(500);
    fill_solid(leds, NUM_LEDS, CRGB::Black);
    FastLED.show();
    delay(500);
  }
  fill_solid(leds, NUM_LEDS, CRGB::Blue); // Return to active state
  FastLED.show();
}

void processCommand(String cmd) {
  cmd.trim();
  cmd.toUpperCase();

  // 1. Check for System Authorization from Pi
  if (cmd == "SYSTEM_READY") {
    systemActive = true;
    fill_solid(leds, NUM_LEDS, CRGB::Blue);
    FastLED.show();
    Serial.println("System Authorized by Pi.");
    return; // Exit here, no mechanical action needed
  }

  // If system is not active yet, ignore other commands
  if (!systemActive) return;
  
  // 2. Execute Mechanical Commands
  if(cmd == "POMPAC") {
    digitalWrite(RELAY_PIN, LOW); // Activate pump
    Serial.println("Pump Activated");
  } 
  else if (cmd == "POMPKAPAT") {
    digitalWrite(RELAY_PIN, HIGH); // Deactivate pump
    Serial.println("Pump Deactivated");
  }
  else if (cmd.indexOf("KOL GEL") >= 0 || cmd.indexOf("KOL GIT") >= 0) {
    int angle = (cmd.indexOf("GEL") >= 0) ? 90 : 0;
    
    // Arm Channel Mapping
    if (cmd.indexOf("BIRINCI") >= 0) {
      pca.setPWM(0, 0, angleToPulse(angle));
      pca.setPWM(1, 0, angleToPulse(angle));
    } 
    else if (cmd.indexOf("IKINCI") >= 0) {
      pca.setPWM(1, 0, angleToPulse(angle));
      pca.setPWM(2, 0, angleToPulse(angle)); 
    }
    else if (cmd.indexOf("ÜÇÜNCÜ") >= 0) {
      pca.setPWM(3, 0, angleToPulse(angle));
      pca.setPWM(4, 0, angleToPulse(angle));
    }
    Serial.println("Arm Moved");
  }
  
  // Flash green after successfully executing a physical command
  flashLEDGreen(); 
}

void loop() {
  // Process Incoming Serial Commands
  if (Serial.available()) {
    String command = Serial.readStringUntil('\n');
    processCommand(command);
  }
}
