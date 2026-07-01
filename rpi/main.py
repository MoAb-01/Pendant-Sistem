import sys
import json
import time
import serial
import pygame
import os
import threading
import pyaudio
import spidev  
import socket
import RPi.GPIO as GPIO
from mfrc522 import SimpleMFRC522
from vosk import Model, KaldiRecognizer, SetLogLevel
from fuzzywuzzy import fuzz
import builtins

# ==========================================
# TERMINAL YAYIN SİSTEMİ (LOGGER)
# ==========================================
##--> Kaan--->LAPTOP_IP = "192.168.1.35" # <--- WEB SUNUCUSUNUN IP'Sİ
##--> Mohamed--->LAPTOP_IP = "192.168.1.34" # <--- WEB SUNUCUSUNUN IP'Sİ
LOG_PORT = 5006
log_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

def custom_print(*args, **kwargs):
    msg = " ".join(map(str, args))
    builtins.print(msg) 
    try:
        if msg.strip() != "":
            log_sock.sendto(f"PILOG:{msg}".encode('utf-8'), (LAPTOP_IP, LOG_PORT))
    except:
        pass

print = custom_print 
SetLogLevel(-1)

# ==========================================
# CUSTOM LED CONTROLLER (APA102)
# ==========================================
class PiHAT_LEDs:
    def __init__(self, num_leds=3):
        self.num_leds = num_leds
        self.spi = spidev.SpiDev()
        self.spi.open(0, 0)
        self.spi.max_speed_hz = 8000000
        self.led_data = [[0, 0, 0] for _ in range(num_leds)]
        self.brightness = 15

    def set_all(self, r, g, b):
        for i in range(self.num_leds):
            self.led_data[i] = [r, g, b]
        self.show()

    def off(self):
        self.set_all(0, 0, 0)

    def show(self):
        data = [0x00, 0x00, 0x00, 0x00]
        for r, g, b in self.led_data:
            data.append(0xE0 | self.brightness)
            data.append(b)
            data.append(g)
            data.append(r)
        data += [0xFF, 0xFF, 0xFF, 0xFF]
        self.spi.xfer2(data)

leds = PiHAT_LEDs()

# ==========================================
# CONFIG & INIT
# ==========================================
MODEL_PATH = '/home/pi/Downloads/vosk-model-small-tr-0.3'
MEGA_PORT = "/dev/arduino_mega" 
UNO_PORT = "/dev/arduino_uno" 
BAUD_RATE = 9600 
AUDIO_FOLDER = "/home/pi/HospitalVC/Audios/TR"
VALID_UID_HEX = "633A18F6B7"

MAIN_COMMANDS = [
    "birinci kol gel", "birinci kol git", 
    "ikinci kol gel", "ikinci kol git", 
    "üçüncü kol gel", "üçüncü kol git",
    "ekran göster", "pompa çalış", "pompa kapat",
    "kol", "müzik aç", "müzik çal", "müzik sustur", "sustur", "durdur", "çıkış",
    "mail gönder","steril yap","oda hazırla"
]
MUSIC_NUMBERS = ["şarkı bir", "şarkı iki", "şarkı üç", "şarkı dört"]
SENSITIVITY = 70

# --- MASTER STATE VARIABLES ---
system_active = False 
is_music_menu_open = False  
web_mic_blocked = False  

UNIQUE_WORDS = set(" ".join(MAIN_COMMANDS + MUSIC_NUMBERS).split())
UNIQUE_WORDS.update(["ac", "kapat", "[unk]"])
GRAMMAR_JSON = json.dumps(list(UNIQUE_WORDS), ensure_ascii=False)

try:
    pygame.mixer.init()
except Exception as e:
    print(f"[AUDIO ERROR] Mixer start failed: {e}")

def play_audio(filename):
    full_path = os.path.join(AUDIO_FOLDER, filename)
    if not os.path.exists(full_path):
        print(f"[AUDIO WARNING] File not found: {full_path}")
        return
    try:
        if pygame.mixer.music.get_busy():
            pygame.mixer.music.stop()
        pygame.mixer.music.load(full_path)
        pygame.mixer.music.play()
    except Exception as e:
        print(f"[AUDIO FAILED] {e}")

# ==========================================
# MUSIC PLAYER ROUTINE
# ==========================================
SONG_MAP = {
    "şarkı bir": "uzunincebiryoldayim.mp3", 
    "şarkı iki": "entersandman.mp3",
    "şarkı üç": "cicekleryasta.mp3", 
    "şarkı dört": "lazziya.mp3"
}

def play_music_routine(cmd, ser_uno):
    global is_music_menu_open 
    if cmd in ["müzik çal", "müzik aç"]:
        is_music_menu_open = True 
        send_cmd(ser_uno, "MUZIK_AC", "UNO")
        print("[MUSIC] Müzik menüsü açıldı.")
    elif cmd in SONG_MAP:
        if not is_music_menu_open: return
        if pygame.mixer.music.get_busy():
            pygame.mixer.music.stop()
            pygame.mixer.music.unload()
        song_index = list(SONG_MAP.keys()).index(cmd) + 1
        send_cmd(ser_uno, str(song_index), "UNO")
        play_audio(SONG_MAP[cmd])
    elif cmd in ["müzik sustur", "sustur", "durdur", "çıkış"]:
        is_music_menu_open = False 
        send_cmd(ser_uno, "MUZIK_KAPAT", "UNO") 
        if pygame.mixer.music.get_busy():
            pygame.mixer.music.stop()
            pygame.mixer.music.unload()
        print("[MUSIC] Müzik durduruldu.")

def send_cmd(ser, cmd, name):
    if not ser: return
    msg = cmd.upper() + "\n"
    ser.write(msg.encode())
    ser.flush()
    print(f"[{name}] Sent: {msg.strip()}")

# ==========================================
# LISTENER CLASS
# ==========================================
class ActiveListener:
    def __init__(self, model_path, sensitivity=70):
        self.model_path = model_path
        self.sensitivity = sensitivity
        self.sample_rate = 16000
        self.chunk_size = 1024
        self.is_muted = False
        self.mute_until = 0
        
        print(f"[INIT] Loading Vosk Model...")
        try:
            model = Model(self.model_path)
            self.rec = KaldiRecognizer(model, self.sample_rate, GRAMMAR_JSON)
        except Exception as e:
            sys.exit(1)

    def start(self):
        self.p = pyaudio.PyAudio()
        dev_idx = None
        for i in range(self.p.get_device_count()):
            dev_name = self.p.get_device_info_by_index(i).get("name", "").lower()
            if "seeed" in dev_name or "respeaker" in dev_name:
                dev_idx = i
                break

        self.stream = self.p.open(format=pyaudio.paInt16, channels=1, rate=self.sample_rate,
                                  input=True, input_device_index=dev_idx,
                                  frames_per_buffer=self.chunk_size)
        self.stream.start_stream()
        
        if web_mic_blocked:
            leds.set_all(255, 69, 0) # Orange: Mic Blocked by Web
            print("[STATUS] Microphone Active, but BLOCKED by Website.")
        else:
            leds.set_all(0, 0, 255) # Blue: Listening
            print("[STATUS] Microphone Active. Listening for commands...")

    def pause(self, seconds):
        self.mute_until = time.time() + seconds
        self.is_muted = True
        leds.set_all(255, 0, 0) # Red: Hardware moving
        print(f"\n[STATUS] Mic MUTED for {seconds}s (Waiting for hardware to stop)...")

    def validate_command(self, text):
        global is_music_menu_open
        active_commands = MAIN_COMMANDS.copy()
        if is_music_menu_open:
            active_commands.extend(MUSIC_NUMBERS)

        best_match = None
        best_score = 0
        heard_len = len(text)

        for cmd in active_commands:
            if text == cmd: return cmd, 100
            base_score = fuzz.token_set_ratio(text, cmd)
            cmd_len = len(cmd)
            length_ratio = min(heard_len, cmd_len) / max(heard_len, cmd_len)
            final_score = base_score * length_ratio

            if final_score > best_score:
                best_score = final_score
                best_match = cmd

        if best_score >= self.sensitivity:
            return best_match, best_score
        return None, best_score

    def listen(self):
        global web_mic_blocked
        while True:
            try:
                data = self.stream.read(self.chunk_size, exception_on_overflow=False)
                
                # --- WEB MIC BLOCK INTERCEPTOR ---
                if web_mic_blocked:
                    continue 
                
                # --- HARDWARE PAUSE INTERCEPTOR ---
                if self.is_muted:
                    if time.time() < self.mute_until:
                        continue 
                    else:
                        self.is_muted = False
                        self.rec.Reset()
                        leds.set_all(0, 0, 255)
                        print("[STATUS] Mic READY. Listening for commands...")
                
                if self.rec.AcceptWaveform(data):
                    process_start_time = time.time() 
                    res = json.loads(self.rec.Result())
                    raw_text = res.get("text", "").strip()
                    
                    if not raw_text: continue
                    text = raw_text 
                    
                    print(f"\n[VOICE] Raw Heard : {raw_text}")
                    match, score = self.validate_command(text)
                    process_time_ms = (time.time() - process_start_time) * 1000 
                    
                    if match:
                        leds.set_all(0, 255, 0)
                        print(f"[VOICE] Processing Time: {process_time_ms:.1f} ms")
                        time.sleep(0.2) 
                        yield match, score
                    else:
                        print(f"[VOICE] No valid command (Confidence: {score:.1f})")
                        
            except Exception as e:
                break

# ==========================================
# 1. DUAL ENTRY: RFID LISTENER
# ==========================================
def rfid_listener():
    global system_active
    reader = SimpleMFRC522()
    
    try:
        while True:
            if not system_active:
                id, text = reader.read()
                if id:
                    tag_hex = hex(id).upper().replace('0X', '')
                    if tag_hex == VALID_UID_HEX:
                        system_active = True
                        leds.set_all(255, 255, 0) # Yellow: Booting
                        print("[SYSTEM] RFID Validated. Activating System...")                        
                        play_audio("Ekran.mp3")
                        send_cmd(ser_mega, "SYSTEM_READY", "MEGA") 
                    else:
                        print(f"[RFID] Unauthorized Card: {tag_hex}")
                time.sleep(2) 
            else:
                time.sleep(1) 
    except Exception as e:
        print(f"[RFID ERROR] {e}")

# ==========================================
# 2. DUAL ENTRY: UDP / WEB LISTENER
# ==========================================
def udp_listener():
    global system_active
    global is_music_menu_open
    global web_mic_blocked  
    
    UDP_IP = "0.0.0.0"  
    UDP_PORT = 5005
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((UDP_IP, UDP_PORT))
    print(f"[WEB UI] Laptop arayüz dinleyicisi {UDP_PORT} portunda aktif.")
    
    while True:
        try:
            data, addr = sock.recvfrom(1024)
            msg = data.decode('utf-8').strip()
            
            if msg == "PING":
                sock.sendto(b"PONG", (addr[0], 5006))
                continue
            
            if msg.startswith("CMD:"):
                cmd = msg.split(":")[1]
                
                if cmd == "SYSTEM_ON" and not system_active:
                    system_active = True  
                    leds.set_all(255, 255, 0) # Yellow: Booting
                    print("[SYSTEM] Sistem Arayüzden Aktif Edildi!")
                    play_audio("Ekran.mp3")
                    send_cmd(ser_mega, "SYSTEM_READY", "MEGA")
                    
                elif cmd == "SYSTEM_OFF":
                    system_active = False  
                    is_music_menu_open = False
                    if pygame.mixer.music.get_busy():
                        pygame.mixer.music.stop()
                    send_cmd(ser_mega, "SYSTEM_OFF", "MEGA") 
                    send_cmd(ser_uno, "MUZIK_KAPAT", "UNO") 
                    leds.set_all(10, 10, 10) # Dim White: Standby Mode
                    print("[SYSTEM] 🛑 SİSTEM KAPATILDI (Fiş Çekildi) - Bekleme Modunda!")
                    
                elif cmd == "MIC_OFF":
                    web_mic_blocked = True
                    print("[WEB UI] Microphone BLOCKED by Website.")
                    if system_active: leds.set_all(255, 69, 0) # Orange
                    
                elif cmd == "MIC_ON":
                    web_mic_blocked = False
                    print("[WEB UI] Microphone ALLOWED by Website.")
                    if system_active: leds.set_all(0, 0, 255) # Blue

                # ARAYÜZDEN GELEN MÜZİK KOMUTLARI
                elif cmd in ["müzik aç", "müzik çal", "şarkı bir", "şarkı iki", "şarkı üç", "şarkı dört", "müzik sustur", "sustur", "durdur", "çıkış"]:
                    play_music_routine(cmd, ser_uno)
                    print(f"[WEB UI] Müzik Komutu Tetiklendi: {cmd}")
                    
                elif cmd == "PUMP_ON":
                    send_cmd(ser_mega, "POMPAC", "MEGA")
                elif cmd == "PUMP_OFF":
                    send_cmd(ser_mega, "POMPKAPAT", "MEGA")
                elif cmd == "KOL_GIT":
                    send_cmd(ser_mega, "KOL GIT", "MEGA")     
                else:
                    send_cmd(ser_mega, cmd, "MEGA")
                    
                print(f"[AĞDAN GELEN] Buton Komutu Aktarıldı: {cmd}")
                
            elif msg.startswith("SLIDER:"):
                parts = msg.split(":")
                port = parts[1]
                aci = parts[2]
                mega_cmd = f"SERVO:{port}:{aci}"
                send_cmd(ser_mega, mega_cmd, "MEGA")
                print(f"[AĞDAN GELEN] Slider Komutu Aktarıldı: {mega_cmd}")
                
        except Exception as e:
            print(f"[UDP HATA] {e}")

# ==========================================
# MAIN EXECUTION
# ==========================================
if __name__ == "__main__":
    ser_uno = None
    ser_mega = None

    try:
        ser_uno = serial.Serial(UNO_PORT, BAUD_RATE, timeout=1)
        ser_mega = serial.Serial(MEGA_PORT, BAUD_RATE, timeout=1)
    except Exception as e:
        print(f"[SERIAL WARNING] Check Arduino connections: {e}")

    def mega_listener():
        while True:
            if ser_mega and ser_mega.in_waiting > 0:
                line = ser_mega.readline().decode('utf-8').strip()
                if line: print(f"[MEGA DEBUG] {line}")
            time.sleep(0.1)

    # UNO SENSÖR DİNLEYİCİSİ (Arayüzdeki nem/ozon ekranları için eklendi)
    def uno_listener():
        while True:
            if ser_uno and ser_uno.in_waiting > 0:
                try:
                    line = ser_uno.readline().decode('utf-8').strip()
                    if line: 
                        # Eğer gelen veri sensör verisiyse, SADECE websiteye gönder (Pi'ye yazdırma)
                        if line.startswith("SENSOR:"):
                            log_sock.sendto(line.encode('utf-8'), (LAPTOP_IP, 5006))
                        # Eğer sensör verisi değilse (başka bir hata/mesaj ise) Pi'ye yazdırabilir
                        else:
                            print(f"[UNO DEBUG] {line}")
                except Exception as e:
                    pass
            time.sleep(0.1)

    # Start all parallel background tasks
    threading.Thread(target=mega_listener, daemon=True).start()
    threading.Thread(target=uno_listener, daemon=True).start() 
    threading.Thread(target=rfid_listener, daemon=True).start()
    threading.Thread(target=udp_listener, daemon=True).start()

    # Turn LEDs Dim White to show the Pi is on, but system is locked
    leds.set_all(10, 10, 10)
    print("[STATUS] Waiting for RFID Scan OR Website (SYSTEM_ON) to boot processing...")

    try:
        # Halt here until EITHER the RFID or the Web flips system_active = True
        while not system_active:
            time.sleep(0.5)
            
        listener = ActiveListener(MODEL_PATH, SENSITIVITY)
        
        # while pygame.mixer.music.get_busy():
        #     time.sleep(0.5)
            
        print("[STATUS] Intro finished! Starting Voice Listener Loop.")
        listener.start()

        # Main Voice Processing Loop
        for command, score in listener.listen():
            cmd = command.lower()
            print(f">>> COMMAND DETECTED: {cmd} ({score:.1f})")

            # Ignore voice commands if system was turned off via Web
            if not system_active:
                continue

            if cmd in ["müzik aç", "müzik çal", "şarkı bir", "şarkı iki", "şarkı üç", "şarkı dört", "müzik sustur", "sustur", "durdur", "çıkış"]:
                play_music_routine(cmd, ser_uno)
                listener.pause(0.5) 

            elif cmd == "ekran göster":
                send_cmd(ser_uno, "ekran-6B7", "UNO") 
                listener.pause(1.0)
            
            elif cmd == "pompa çalış":
                send_cmd(ser_mega, "POMPAC", "MEGA")
                listener.pause(1.0)
                
            elif cmd == "pompa kapat":
                send_cmd(ser_mega, "POMPKAPAT", "MEGA")
                listener.pause(1.0)
                
            elif cmd == "steril yap":
                send_cmd(ser_mega, "LED_PURPLE", "MEGA")
                listener.pause(1.0)
                
            elif cmd == "oda hazırla":
                send_cmd(ser_mega, "LED_BLUE", "MEGA")
                listener.pause(1.0)
                
            elif "kol gel" in cmd or "kol git" in cmd:
                # Translate Turkish to safe ASCII for the Arduino Serial
                safe_cmd = cmd.replace("birinci", "ARM1").replace("ikinci", "ARM2").replace("üçüncü", "ARM3")
                send_cmd(ser_mega, safe_cmd.upper(), "MEGA")
                listener.pause(1.5)
                
            elif cmd in ("ac", "aç", "kapat", "kol"):
                send_cmd(ser_mega, cmd.upper(), "MEGA")
                listener.pause(1.5)
                
    except KeyboardInterrupt:
        print("\n[STATUS] Stopping System...")
    finally:
        leds.off()
        if ser_uno: ser_uno.close()
        if ser_mega: ser_mega.close()
        GPIO.cleanup() 
        print("[STATUS] System Cleaned. Exiting.")
