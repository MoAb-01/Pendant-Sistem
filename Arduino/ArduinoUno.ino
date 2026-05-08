//SURGEXA®2026 ALL RIGHTS RESERVED
// MEMORY USAGE: %95

#include <MCUFRIEND_kbv.h>
#include <Adafruit_GFX.h>
#include <SPI.h>
#include <SD.h>
#include <DHT.h>

MCUFRIEND_kbv tft;


//          PINS 
//___________________________

#define SD_CS             10
#define LCD_CS            A3
#define DHTPIN            A5
#define OZONE_ANALOG_PIN  A4
#define OZONE_DIGITAL_PIN 4

#define DHTTYPE   DHT22
#define BUFFPIXEL 10   

DHT dht(DHTPIN, DHTTYPE);

//          Variables 
//___________________________
unsigned long imageDisplayTime = 0; //img display time counter
unsigned long lastSensorUpdate = 0; //sensor display time counter
bool showingImage     = false;      //image showing state
bool showingMusicList = false;      //music List state

//MUSIC NAMES LIST
const char s0[] PROGMEM = "1 - UZUNINCE";  //music list 1
const char s1[] PROGMEM = "2 - SANDMAN";  //music list 2
const char s2[] PROGMEM = "3 - CICEKLER"; // music list 3
const char s3[] PROGMEM = "4 - LAZZIYA";  // music list 4
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

//       Screen drawing        
//___________________________

//Idle State Screen
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
// Update Idle Screen states
void updateIdleSensors() {
  if (showingImage || showingMusicList) return;
  float hum      = dht.readHumidity();
  float temp     = dht.readTemperature();
  int   rawOzone = analogRead(OZONE_ANALOG_PIN);
  int   ozDig    = digitalRead(OZONE_DIGITAL_PIN);
  tft.setTextColor(0xFFFF, 0x0000);
  tft.setTextSize(2);
  tft.setCursor(130, 55);
  if (!isnan(temp)) { tft.print(temp); tft.print(F(" C  ")); } 
  else { tft.print(F("-- C  ")); }
  tft.setCursor(130, 105);
  if (!isnan(hum)) { tft.print(hum);  tft.print(F(" %  ")); } 
  else { tft.print(F("-- %  ")); }
  tft.setCursor(130, 155);
  tft.print(rawOzone);
  tft.print(F(" | "));
  tft.print(ozDig ? F("DET") : F("OK "));
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

// Pins Configurations And Setup       
//___________________________

void setup() {
  Serial.begin(9600);
  dht.begin();
  
  pinMode(OZONE_ANALOG_PIN,  INPUT);
  pinMode(OZONE_DIGITAL_PIN, INPUT);
  pinMode(SD_CS,  OUTPUT); digitalWrite(SD_CS,  HIGH);
  pinMode(LCD_CS, OUTPUT); digitalWrite(LCD_CS, HIGH);

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

    // 1..command: Show image 

    // EKRAN-LAST 3 DIGITS OF RFID card
    if (strncmp(cmd, "EKRAN-", 6) == 0) {
      char filename[25]; // Increased size for safety
      strcpy(filename, cmd + 6);
      strcat(filename, ".BMP");
      
      showingImage = true;
      showingMusicList = false;
      tft.fillScreen(0x0000); // clear screen before idle menu case
      bmpDraw(filename, 0, 0);
      
      imageDisplayTime = millis();
    }
    // 1..command:MUZIK AC
    else if (strcmp(cmd, "MUZIK_AC") == 0) {
      showingMusicList = true;
      showingImage = false;
      drawMusicList();
    }
    // 2.. Command: MUZIK KAPAT 
    else if (strcmp(cmd, "MUZIK_KAPAT") == 0) {
      showingMusicList = false;
      showingImage = false;
      drawIdleTemplate();
    }
    // 3..Command: Song Selection ---
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

  if (showingImage && (now - imageDisplayTime >= 10000)) {
    showingImage = false;
    drawIdleTemplate();
  }

  if (!showingImage && !showingMusicList && (now - lastSensorUpdate >= 2000)) {
    updateIdleSensors();
    lastSensorUpdate = now;
  }
}

// Pins Configurations And Setup Utilizations and Helper Functions  
//Rights Reserved For Tech Trends     
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
