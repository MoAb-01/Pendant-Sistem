#include <Wire.h>
#include <Adafruit_PWMServoDriver.h>

Adafruit_PWMServoDriver pca = Adafruit_PWMServoDriver(0x40);

const int SERVOMIN = 160;
const int SERVOMAX = 520;

int servo[16];   // store angle for each channel (0–15)

uint16_t angleToPulse(int a) {
  a = constrain(a, 0, 180);
  return map(a, 0, 180, SERVOMIN, SERVOMAX);
}

void updateServos() {
  for (int ch = 0; ch < 16; ch++) {
    pca.setPWM(ch, 0, angleToPulse(servo[ch]));
  }
}

void setup() {

  Serial.begin(9600);
  Wire.begin();

  pca.begin();
  pca.setOscillatorFrequency(27000000);
  pca.setPWMFreq(50);

  delay(10);

  // initialize all servos
  for(int i=0;i<16;i++){
    servo[i] = 0;
  }

  updateServos();

  Serial.println("READY");
}

void loop() {

  if (Serial.available()) {

    String cmd = Serial.readStringUntil('\n');
    cmd.trim();
    cmd.toUpperCase();

    if (cmd == "KAPAT") {

      servo[15] = 90;
      servo[1]  = 20;
      servo[2]  = 40;
      servo[3]  = 30;

      updateServos();
    }

    if (cmd == "AÇ") {

      servo[15] = 40;
      servo[1]  = 70;
      servo[2]  = 60;
      servo[3]  = 10;

      updateServos();
    }
  }
}
