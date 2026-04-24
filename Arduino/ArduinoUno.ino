#include <MCUFRIEND_kbv.h>
#include <Adafruit_GFX.h>
#include <SPI.h>
#include <SD.h>
#include <DHT.h>

// --- LCD Definitions ---
MCUFRIEND_kbv tft;
#define SD_CS 10

// --- Sensor Definitions ---
#define DHTPIN 13
#define DHTTYPE DHT22
#define OZONE_PIN 12

DHT dht(DHTPIN, DHTTYPE);

// --- State and Timing Variables ---
unsigned long imageDisplayTime = 0;
unsigned long lastSensorUpdate = 0;
bool showingImage = false;

void setup() {
  Serial.begin(9600);
  
  // Sensor Setup
  dht.begin();
  pinMode(OZONE_PIN, INPUT);

  // SD Setup
  pinMode(10, OUTPUT);
  digitalWrite(10, HIGH);
  if (!SD.begin(SD_CS)) {
    Serial.println("SD failed!");
  }

  // TFT Setup & ID Fix
  tft.reset();
  uint16_t ID = tft.readID();
  Serial.print("Raw TFT ID = 0x");
  Serial.println(ID, HEX);
  if (ID == 0x1919) ID = 0x9341; // Fix for specific shield bug
  
  tft.begin(ID);
  tft.setRotation(1);

  // Draw the initial UI Template
  drawIdleTemplate();
}

// Draws the static text (run once when entering idle state)
void drawIdleTemplate() {
  tft.fillScreen(0x0000); // Black background
  tft.setTextColor(0xFFFF, 0x0000); // White text
  tft.setTextSize(2);

  tft.setCursor(10, 10);
  tft.print("Surgexa System Idle");

  tft.drawFastHLine(0, 35, 320, 0xFFFF);

  tft.setCursor(10, 55);
  tft.print("Temp:");

  tft.setCursor(10, 105);
  tft.print("Hum :");

  tft.setCursor(10, 155);
  tft.print("Ozone:");
  
  // Force an immediate sensor read
  updateIdleSensors(); 
}

// Updates just the numbers so the screen doesn't flicker
void updateIdleSensors() {
  float hum = dht.readHumidity();
  float temp = dht.readTemperature();
  int ozone = digitalRead(OZONE_PIN);

  // Clear ONLY the areas where sensor values go
  tft.fillRect(130, 50, 180, 35, 0x0000); // Clear Temp area
  tft.fillRect(130, 100, 180, 35, 0x0000); // Clear Hum area
  tft.fillRect(130, 150, 180, 35, 0x0000); // Clear Ozone area
  tft.fillRect(10, 240, 300, 20, 0x0000);  // Clear Error text area

  tft.setTextColor(0xFFFF, 0x0000);
  tft.setTextSize(2);

  if (isnan(hum) || isnan(temp)) {
    tft.setCursor(10, 240);
    tft.print("DHT ERROR");
  } else {
    tft.setCursor(130, 55);
    tft.print(temp, 1);
    tft.print(" C");

    tft.setCursor(130, 105);
    tft.print(hum, 1);
    tft.print(" %");
  }

  tft.setCursor(130, 155);
  if (ozone == HIGH) {
    tft.print("DETECTED");
  } else {
    tft.print("CLEAR");
  }
}

void loop() {
  unsigned long currentMillis = millis();

  // 1. Manage Active Image State
  if (showingImage) {
    // Check if 10 seconds have passed
    if (currentMillis - imageDisplayTime >= 10000) {
      showingImage = false;
      drawIdleTemplate(); // Restore the sensor UI
      Serial.println("DEBUG: Screen Cleared");
    }
  } 
  // 2. Manage Idle State (Update sensors every 1 second without blocking)
  else {
    if (currentMillis - lastSensorUpdate >= 1000) {
      updateIdleSensors();
      lastSensorUpdate = currentMillis;
    }
  }

  // 3. Listen for Raspberry Pi Commands (Instantly responsive!)
  if (Serial.available()) {
    String cmd = Serial.readStringUntil('\n');
    cmd.trim();
    cmd.toUpperCase();
    
    if (cmd.startsWith("EKRAN-")) {
      String fileId = cmd.substring(6);
      String filename = fileId + ".bmp";
      
      char charBuf[50];
      filename.toCharArray(charBuf, 50);
      
      tft.fillScreen(0x0000); // Clear screen to black for the image
      bmpDraw(charBuf, 0, 0); // Draw image from SD
      
      showingImage = true;
      imageDisplayTime = millis();
    }
  }
}

// ==========================================
// BMP DRAWING FUNCTION
// ==========================================
#define BUFFPIXEL 20

void bmpDraw(char *filename, int x, int y) {
  File bmpFile;
  int bmpWidth, bmpHeight;
  uint8_t bmpDepth;
  uint32_t bmpImageoffset;
  uint32_t rowSize;
  uint8_t sdbuffer[3*BUFFPIXEL];
  uint16_t lcdbuffer[BUFFPIXEL];
  boolean goodBmp = false;
  boolean flip = true;
  int w, h, row, col;
  uint8_t r, g, b;
  uint32_t pos = 0;
  uint8_t lcdidx = 0;
  boolean first = true;

  if((x >= tft.width()) || (y >= tft.height())) return;

  if ((bmpFile = SD.open(filename)) == NULL) {
    Serial.print(F("File not found: "));
    Serial.println(filename);
    return;
  }

  if (read16(bmpFile) == 0x4D42) { // BMP signature
    (void)read32(bmpFile); // Read & ignore creator bytes
    bmpImageoffset = read32(bmpFile); // Start of image data
    read32(bmpFile); // Read & ignore Header size
    
    bmpWidth  = read32(bmpFile);
    bmpHeight = read32(bmpFile);
    if(read16(bmpFile) == 1) { // # planes -- must be '1'
      bmpDepth = read16(bmpFile); // bits per pixel
      if((bmpDepth == 24) && (read32(bmpFile) == 0)) { // 0 = uncompressed
        goodBmp = true;
        rowSize = (bmpWidth * 3 + 3) & ~3;
        if(bmpHeight < 0) {
          bmpHeight = -bmpHeight;
          flip = false;
        }

        w = bmpWidth;
        h = bmpHeight;
        if((x+w-1) >= tft.width())  w = tft.width()  - x;
        if((y+h-1) >= tft.height()) h = tft.height() - y;

        tft.setAddrWindow(x, y, x+w-1, y+h-1);

        for (row=0; row<h; row++) { 
          if(flip) pos = bmpImageoffset + (bmpHeight - 1 - row) * rowSize;
          else     pos = bmpImageoffset + row * rowSize;
          if(bmpFile.position() != pos) {
            bmpFile.seek(pos);
            lcdidx = 0; // Force buffer reload
          }

          for (col=0; col<w; col++) { 
            if (lcdidx >= sizeof(sdbuffer)) { 
              bmpFile.read(sdbuffer, sizeof(sdbuffer));
              lcdidx = 0; 
            }
            b = sdbuffer[lcdidx++];
            g = sdbuffer[lcdidx++];
            r = sdbuffer[lcdidx++];
            lcdbuffer[col] = tft.color565(r,g,b);
          }
          tft.pushColors(lcdbuffer, w, first);
          first = false;
        }
      } 
    }
  }

  bmpFile.close();
  if(!goodBmp) Serial.println(F("BMP format not recognized."));
}

uint16_t read16(File f) {
  uint16_t result;
  ((uint8_t *)&result)[0] = f.read(); // LSB
  ((uint8_t *)&result)[1] = f.read(); // MSB
  return result;
}

uint32_t read32(File f) {
  uint32_t result;
  ((uint8_t *)&result)[0] = f.read(); // LSB
  ((uint8_t *)&result)[1] = f.read();
  ((uint8_t *)&result)[2] = f.read();
  ((uint8_t *)&result)[3] = f.read(); // MSB
  return result;
}