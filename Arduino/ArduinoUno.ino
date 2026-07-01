// SURGEXA®2026 ALL RIGHTS RESERVED
// HYBRID MODE: REAL DHT22 + FAKE OZONE ARRAY

#include <MCUFRIEND_kbv.h>
#include <Adafruit_GFX.h>
#include <SPI.h>
#include <SD.h>
#include <DHT.h>

MCUFRIEND_kbv tft;

//          PINS (Arduino Uno)
//___________________________

#define SD_CS             10
#define LCD_CS            A3
#define DHTPIN            A5  // MUST BE A5: The only free pin on the Uno with this shield!

#define DHTTYPE   DHT22
#define BUFFPIXEL 10   

DHT dht(DHTPIN, DHTTYPE);

//          Variables 
//___________________________
unsigned long imageDisplayTime = 0; 
unsigned long lastSensorUpdate = 0; 
bool showingImage     = false;      
bool showingMusicList = false;      

// MUSIC NAMES LIST
const char s0[] PROGMEM = "1 - UZUNINCE";   
const char s1[] PROGMEM = "2 - SANDMAN";    
const char s2[] PROGMEM = "3 - CICEKLER"; 
const char s3[] PROGMEM = "4 - LAZZIYA";  
const char* const sarkiListesi[] PROGMEM = {s0, s1, s2, s3};
const uint8_t sarkiSayisi = 4;

char sarkiBuf[20];

void getSarki(uint8_t i) {
  strcpy_P(sarkiBuf, (char*)pgm_read_word(&(sarkiListesi[i])));
}

void trimStr(char* s) {
  int start = 0;
  while (s[start] == ' ' || s[start] == '\n' || s[start] == '\r') start++;
  if (start) memmove(s, s + start, strlen(s) - start + 1);
  int end = strlen(s) - 1;
  while (end >= 0 && (s[end] == ' ' || s[end] == '\n' || s[end] == '\r')) s[end--] = '\0';
}

//          Fake Sensor Data Array (Ozone Only)
//___________________________
const int fakeDataLength = 10;
int fakeDataIndex = 0;

// Simulates an ozone leak that crosses the 500 threshold, then dissipates
int fakeOzone[fakeDataLength]  = {150, 210, 340, 480, 530, 610, 540, 420, 280, 170}; 


//       Screen drawing        
//___________________________

// Idle State Screen
void drawIdleTemplate() {
  tft.fillScreen(0x0000);
  tft.setTextColor(0xFFFF, 0x0000);
  tft.setTextSize(2);
  tft.setCursor(10, 10);  tft.print(F("Surgexa Idle"));
  tft.drawFastHLine(0, 35, 320, 0xFFFF);
  tft.setCursor(10, 55);  tft.print(F("Temp:"));
  tft.setCursor(10, 105); tft.print(F("Hum :"));
  tft.setCursor(10, 155); tft.print(F("Ozone:"));
  
  updateIdleSensors();
}

// Update Idle Screen states (HYBRID)
void updateIdleSensors() {
  if (showingImage || showingMusicList) return;
  
  // 1. REAL Data from physical DHT22
  float hum  = dht.readHumidity();
  float temp = dht.readTemperature();
  
  // 2. FAKE Data from array for Ozone
  int rawOzone = fakeOzone[fakeDataIndex];
  
  // Advance the index for the next cycle
  fakeDataIndex++;
  if (fakeDataIndex >= fakeDataLength) {
    fakeDataIndex = 0;
  }
  
  // Software Logic for Digital Trigger 
  bool ozDet = (rawOzone > 500); 

  tft.setTextColor(0xFFFF, 0x0000);
  tft.setTextSize(2);
  
  // Temperature (Real)
  tft.setCursor(130, 55);
  if (!isnan(temp)) { tft.print(temp, 1); tft.print(F(" C  ")); } 
  else { tft.print(F("-- C  ")); }
  
  // Humidity (Real)
  tft.setCursor(130, 105);
  if (!isnan(hum)) { tft.print(hum, 1);  tft.print(F(" %  ")); } 
  else { tft.print(F("-- %  ")); }
  
  // Ozone (Fake)
  tft.setCursor(130, 155);
  // Pad with spaces to clear old trailing digits if the number drops
  if (rawOzone < 1000) tft.print(F(" ")); 
  if (rawOzone < 100)  tft.print(F(" "));
  if (rawOzone < 10)   tft.print(F(" "));
  tft.print(rawOzone);
  tft.print(F(" | "));
  tft.print(ozDet ? F("DET") : F("OK "));

  // Send Data to Node.js/Python format
  if (!isnan(hum)) {
    Serial.print("SENSOR:");
    Serial.print(hum);
    Serial.print(":");
    Serial.println(rawOzone);
  }
}

// Music List Menu
void drawMusicList() {
  tft.fillScreen(0x0000);
  tft.setTextColor(0x07E0); 
  tft.setTextSize(3);
  tft.setCursor(10, 10); tft.print(F("Muzik"));
  tft.drawFastHLine(0, 40, 320, 0xFFFF);  
  tft.setTextColor(0xFFFF);
  tft.setTextSize(2);
  for (uint8_t i = 0; i < sarkiSayisi; i++) {
    getSarki(i);
    tft.setCursor(10, 60 + (i * 35));
    tft.print(sarkiBuf);
  }
}

//       Pins Configurations And Setup       
//___________________________

void setup() {
  Serial.begin(9600);
  dht.begin();
  
  pinMode(SD_CS, OUTPUT); 
  digitalWrite(SD_CS, HIGH);
  
  pinMode(LCD_CS, OUTPUT); 
  digitalWrite(LCD_CS, HIGH);

  tft.reset();
  uint16_t identifier = tft.readID();
  if (identifier == 0x0000 || identifier == 0x1919) identifier = 0x9341;
  tft.begin(identifier);
  tft.setRotation(1);

  if (!SD.begin(SD_CS)) {
    Serial.println(F("SD Init Fail!"));
  } else {
    Serial.println(F("SD Init OK."));
  }

  drawIdleTemplate();
}

void loop() {
  if (Serial.available()) {
    char cmd[24];
    uint8_t len = Serial.readBytesUntil('\n', cmd, 23);
    cmd[len] = '\0';
    
    for(int i=0; i<len; i++) {
      cmd[i] = toupper(cmd[i]);
    }
    trimStr(cmd);

    // 1. Command: Show Image
    if (strncmp(cmd, "EKRAN-", 6) == 0) {
      char filename[25]; 
      strcpy(filename, cmd + 6);
      strcat(filename, ".BMP");
      
      showingImage = true;
      showingMusicList = false;
      tft.fillScreen(0x0000); 
      bmpDraw(filename, 0, 0);
      
      imageDisplayTime = millis();
    }
    
    // 2. Command: MUZIK AC
    else if (strcmp(cmd, "MUZIK_AC") == 0) {
      showingMusicList = true;
      showingImage = false;
      drawMusicList();
    }
    
    // 3. Command: MUZIK KAPAT 
    else if (strcmp(cmd, "MUZIK_KAPAT") == 0) {
      showingMusicList = false;
      showingImage = false;
      drawIdleTemplate();
    }
    
    // 4. Command: Song Selection
    else if (showingMusicList && strlen(cmd) == 1 && cmd[0] >= '1' && cmd[0] <= '4') {
      int choice = cmd[0] - '1';
      getSarki(choice);
      Serial.print(F("Playing: ")); Serial.println(sarkiBuf);
      tft.fillRect(0, 200, 320, 40, 0x0000);
      tft.setCursor(10, 210);
      tft.setTextColor(0xF800); 
      tft.print(F("Playing: ")); tft.print(sarkiBuf);
    }
  }

  unsigned long now = millis();

  // Return to idle screen after 10 seconds of showing an image
  if (showingImage && (now - imageDisplayTime >= 10000)) {
    showingImage = false;
    drawIdleTemplate();
  }

  // Update sensors every 2 seconds (2000 ms) so you can see the array work!
  // If you want to change it back to 10 minutes later, change 2000 to 600000UL
  if (!showingImage && !showingMusicList && (now - lastSensorUpdate >= 2000)) {
    updateIdleSensors();
    lastSensorUpdate = now;
  }
}

//       BMP Drawing Helper Function       
//___________________________

void bmpDraw(char* filename, int x, int y) {
  File     bmpFile;
  int      bmpWidth, bmpHeight;
  uint8_t  bmpDepth;
  uint32_t bmpImageoffset;
  uint32_t rowSize;
  uint8_t  sdbuffer[3 * BUFFPIXEL];
  uint16_t lcdbuffer[BUFFPIXEL];
  uint8_t  buffidx = sizeof(sdbuffer);
  bool     flip    = true;
  int      w, h, row, col;
  uint8_t  r, g, b;
  uint32_t pos     = 0;
  uint8_t  lcdidx  = 0;
  bool     first   = true;

  if ((bmpFile = SD.open(filename)) == NULL) {
    Serial.print(F("Not found: ")); Serial.println(filename);
    drawIdleTemplate(); 
    showingImage = false;
    return;
  }

  if (read16(bmpFile) == 0x4D42) {
    read32(bmpFile); read32(bmpFile);
    bmpImageoffset = read32(bmpFile);
    read32(bmpFile);
    bmpWidth  = read32(bmpFile);
    bmpHeight = read32(bmpFile);

    if (read16(bmpFile) == 1) {
      bmpDepth = read16(bmpFile);
      if (bmpDepth == 24 && read32(bmpFile) == 0) {
        rowSize = (bmpWidth * 3 + 3) & ~3;
        if (bmpHeight < 0) { bmpHeight = -bmpHeight; flip = false; }
        w = bmpWidth; h = bmpHeight;
        if ((x + w - 1) >= tft.width())  w = tft.width()  - x;
        if ((y + h - 1) >= tft.height()) h = tft.height() - y;

        tft.setAddrWindow(x, y, x + w - 1, y + h - 1);

        for (row = 0; row < h; row++) {
          pos = flip ? bmpImageoffset + (bmpHeight - 1 - row) * rowSize : bmpImageoffset + row * rowSize;
          if (bmpFile.position() != pos) {
            bmpFile.seek(pos);
            buffidx = sizeof(sdbuffer);
          }
          for (col = 0; col < w; col++) {
            if (buffidx >= sizeof(sdbuffer)) {
              if (lcdidx > 0) { tft.pushColors(lcdbuffer, lcdidx, first); lcdidx = 0; first = false; }
              bmpFile.read(sdbuffer, sizeof(sdbuffer));
              buffidx = 0;
            }
            b = sdbuffer[buffidx++]; g = sdbuffer[buffidx++]; r = sdbuffer[buffidx++];
            lcdbuffer[lcdidx++] = tft.color565(r, g, b);
          }
        }
        if (lcdidx > 0) tft.pushColors(lcdbuffer, lcdidx, first);
      }
    }
  }
  bmpFile.close();
}

uint16_t read16(File f) { uint16_t result; f.read((uint8_t*)&result, sizeof(result)); return result; }
uint32_t read32(File f) { uint32_t result; f.read((uint8_t*)&result, sizeof(result)); return result; }
