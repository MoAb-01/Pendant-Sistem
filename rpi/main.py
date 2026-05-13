import pyaudio
import json
import sys
import time
import serial
import pygame
import os
import threading
import RPi.GPIO as GPIO
from mfrc522 import SimpleMFRC522
from vosk import Model, KaldiRecognizer
from fuzzywuzzy import fuzz

# ==========================================
# CONFIG & INIT
# ==========================================
MODEL_PATH = '/home/pi/Downloads/vosk-model-tr-0.18-robotarm'
MEGA_PORT = '/dev/arduino_mega' 
UNO_PORT = '/dev/arduino_uno' 
BAUD_RATE = 9600 # Consider changing to 115200 
AUDIO_FOLDER = "/home/pi/HospitalVC/Audios/TR"

VALID_UID_HEX = "633A18F6B7"

MAIN_COMMANDS = [
    "birinci kol gel", "birinci kol git", 
    "ikinci kol gel", "ikinci kol git", 
    "üçüncü kol gel", "üçüncü kol git",
    "ekran göster", "pompayı aç", "pompayı kapat",
    "kol", "müzik aç", "müzik çal", "müzik sustur", "sustur", "durdur", "çıkış"
]
# YENİ: Kısa kelime halüsinasyonlarını engellemek için "şarkı" eklendi.
MUSIC_NUMBERS = ["şarkı bir", "şarkı iki", "şarkı üç", "şarkı dört"]

SENSITIVITY = 70

system_active = False 
is_music_menu_open = False  

try:
    pygame.mixer.init()
except Exception as e:
    print(f"[AUDIO ERROR] Mixer start failed: {e}")

def play_audio(filename):
    full_path = os.path.join(AUDIO_FOLDER, filename)
    if not os.path.exists(full_path):
        return
    try:
        if pygame.mixer.music.get_busy():
            pygame.mixer.music.stop()
        pygame.mixer.music.load(full_path)
        pygame.mixer.music.play()
    except Exception as e:
        print(f"[AUDIO FAILED] {e}")

# ==========================================
# PHONETIC INTERCEPTOR (THE BRAIN FIX)
# ==========================================
PHONETIC_MAP = {
    "com": "kol",
    "çoğun": "üçüncü",
    "çoğunun": "üçüncü",
    "oyuncu": "üçüncü",
    "icon": "ikinci",
    "diyetler": "gel",
    "diyet": "gel",
    "çocuk": "üçüncü",
    "ol": "kol",
    "ghoul": "kol",
    "concord": "üçüncü",
    "çoğu": "kol",
    "dev": "gel",
    "öncü": "üçüncü",
    "değerli": "gel",
    "konuk": "kol",
    "geldi": "gel",
    "count": "kol",
    "doğrudur": "durdur",
    "gol": "kol",
    "get": "git",
    "covent": "kol gel",
    "korgan": "kol gel",
    "cool": "kol",
    "giyip": "git",
    "ikram": "ekran",
    "goster": "göster"
}

def clean_text(raw_text):
    """Replaces known hallucinations with the correct words."""
    cleaned = raw_text.replace("i̇", "i")  # Fix weird Turkish i

    # --- PHRASE REPLACEMENTS (Context-Aware) ---
    cleaned = cleaned.replace("kol dört", "kol git")
    cleaned = cleaned.replace("kavramı", "kol git")
    cleaned = cleaned.replace("üç oyuncu", "üçüncü")
    cleaned = cleaned.replace("üç önce", "üçüncü")
    cleaned = cleaned.replace("count dört", "kol git")
    cleaned = cleaned.replace("concord çoğu dev", "üçüncü kol gel")
    cleaned = cleaned.replace("üç öncü çoğu değerli", "üçüncü kol gel")

    # --- WORD REPLACEMENTS ---
    words = cleaned.split()
    for i, word in enumerate(words):
        if word in PHONETIC_MAP:
            words[i] = PHONETIC_MAP[word]

    return " ".join(words)

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

    if cmd in ["müzik çal"]:
        is_music_menu_open = True 
        send_cmd(ser_uno, "MUZIK_AC", "UNO")
        print("[MUSIC] Müzik menüsü açıldı. (Sayı komutları aktif)")
        
    elif cmd in SONG_MAP:
        if not is_music_menu_open:
            return

        if pygame.mixer.music.get_busy():
            pygame.mixer.music.stop()
            pygame.mixer.music.unload()

        song_index = list(SONG_MAP.keys()).index(cmd) + 1
        send_cmd(ser_uno, str(song_index), "UNO")
        
        file_name = SONG_MAP[cmd]
        print(f"[MUSIC] Çalınıyor: {file_name}")
        play_audio(file_name)
        
    elif cmd in ["müzik sustur", "sustur", "durdur", "çıkış"]:
        is_music_menu_open = False 
        send_cmd(ser_uno, "MUZIK_KAPAT", "UNO") 
        
        if pygame.mixer.music.get_busy():
            pygame.mixer.music.stop()
            pygame.mixer.music.unload()
        print("[MUSIC] Müzik durduruldu. (Sayı komutları gizlendi)")

def send_cmd(ser, cmd, name):
    if not ser:
        print(f"[ERROR] The '{cmd}'. The {name} is not connected!")
        return
    msg = cmd.upper() + "\n"
    ser.write(msg.encode())
    ser.flush()
    print(f"[{name}] Sent: {msg.strip()}")

# ==========================================
# LISTENER CLASS
# ==========================================
class ActiveListener:
    def __init__(self, model_path, sensitivity=80):
        self.model_path = model_path
        self.sensitivity = sensitivity
        self.sample_rate = 16000
        self.chunk_size = 1024
        
        print("[INIT] Loading Vosk Model...")
        model = Model(self.model_path)
        self.rec = KaldiRecognizer(model, self.sample_rate)

    def start(self):
        self.p = pyaudio.PyAudio()
        dev_idx = None
        for i in range(self.p.get_device_count()):
            try:
                if "seeed" in self.p.get_device_info_by_index(i).get("name", "").lower():
                    dev_idx = i
                    break
            except:
                continue

        self.stream = self.p.open(format=pyaudio.paInt16, channels=1, rate=self.sample_rate,
                                  input=True, input_device_index=dev_idx,
                                  frames_per_buffer=self.chunk_size)
        self.stream.start_stream()
        print("[STATUS] Microphone Active. Listening for commands...")

    def validate_command(self, text):
        global is_music_menu_open
        
        active_commands = MAIN_COMMANDS.copy()
        if is_music_menu_open:
            active_commands.extend(MUSIC_NUMBERS)

        best_match = None
        best_score = 0
        heard_len = len(text)

        for cmd in active_commands:
            if text == cmd:
                return cmd, 100

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
        while True:
            try:
                data = self.stream.read(self.chunk_size, exception_on_overflow=False)
                if self.rec.AcceptWaveform(data):
                    res = json.loads(self.rec.Result())
                    raw_text = res.get("text", "").strip()
                    
                    if not raw_text:
                        continue
                        
                    # 1. Apply Interceptor mapping BEFORE validation
                    text = clean_text(raw_text)
                    
                    # 2. Print debug logs
                    print(f"\n[VOICE] Raw Heard : {raw_text}")
                    if raw_text != text:
                        print(f"[VOICE] Corrected : {text}")
                        
                    # 3. Validate
                    match, score = self.validate_command(text)
                    if match:
                        yield match, score
                    else:
                        print(f"[VOICE] No valid command (Confidence: {score:.1f})")
            except Exception as e:
                break

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
                if line:
                    print(f"[MEGA DEBUG] {line}")
            time.sleep(0.1)

    def rfid_listener():
        global system_active
        reader = SimpleMFRC522()
        print("[RFID] Scanner Active. Place your tag near the reader...")
        
        try:
            while True:
                if not system_active:
                    id, text = reader.read()
                    if id:
                        tag_hex = hex(id).upper().replace('0X', '')
                        print(f"[RFID] Scanned Tag: {tag_hex}")
                        if tag_hex == VALID_UID_HEX:
                            system_active = True
                            print("[SYSTEM] RFID Validated. Activating Voice Module...")                        
                            play_audio("Ekran.mp3")
                            send_cmd(ser_mega, "SYSTEM_READY", "MEGA") 
                        else:
                            print("[RFID] Unauthorized Card.")
                        
                        time.sleep(2) 
                else:
                    time.sleep(1) 
        except Exception as e:
            print(f"[RFID ERROR] {e}")

    threading.Thread(target=mega_listener, daemon=True).start()
    threading.Thread(target=rfid_listener, daemon=True).start()

    print("[STATUS] Waiting for RFID Verification to boot voice processing...")
    try:
        while not system_active:
            time.sleep(0.5)
            
        
        listener = ActiveListener(MODEL_PATH, SENSITIVITY)

        
        print("[STATUS] Intro (Ekran.mp3) is playing. Microphone is STANDBY...")
        while pygame.mixer.music.get_busy():
            time.sleep(0.5)
            
        
        print("[STATUS] Intro finished! Microphone is now ACTIVE.")
        listener.start()

        for command, score in listener.listen():
            cmd = command.lower()
            print(f">>> COMMAND DETECTED: {cmd} ({score:.1f})")

            if cmd in ["müzik aç", "müzik çal", "şarkı bir", "şarkı iki", "şarkı üç", "şarkı dört", "müzik sustur", "sustur", "durdur", "çıkış"]:
                play_music_routine(cmd, ser_uno)

            elif cmd == "ekran göster":
                send_cmd(ser_uno, "ekran-6B7", "UNO") 
            
            elif cmd == "pompayı aç":
                send_cmd(ser_mega, "POMPAC", "MEGA")
            elif cmd == "pompayı kapat":
                send_cmd(ser_mega, "POMPKAPAT", "MEGA")
            elif "kol gel" in cmd or "kol git" in cmd:
                send_cmd(ser_mega, cmd.upper(), "MEGA")
            elif cmd in ("ac", "aç", "kapat", "kol"):
                send_cmd(ser_mega, cmd.upper(), "MEGA")
                
    except KeyboardInterrupt:
        print("\n[STATUS] Stopping System...")
    finally:
        if ser_uno: ser_uno.close()
        if ser_mega: ser_mega.close()
        GPIO.cleanup() 
        print("[STATUS] GPIO Cleaned. Exiting.")
