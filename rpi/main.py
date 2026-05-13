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
BAUD_RATE = 9600 
AUDIO_FOLDER = "/home/pi/HospitalVC/Audios/TR"

VALID_UID_HEX = "633A18F6B7"

MAIN_COMMANDS = [
    "birinci kol gel", "birinci kol git", 
    "ikinci kol gel", "ikinci kol git", 
    "üçüncü kol gel", "üçüncü kol git",
    "ekran göster", "pompayı aç", "pompayı kapat",
    "kol", "müzik aç", "müzik çal", "müzik sustur", "sustur", "durdur", "çıkış",
    "mail gönder"
]

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
# PHONETIC INTERCEPTOR (THE 4-LAYER BRAIN)
# ==========================================
PHONETIC_MAP = {
    "brent": "birinci", "bence": "birinci", "öğrenci": "birinci",
    "direnci": "birinci", "verilecek": "birinci", "birincilik": "birinci",
    "grange": "birinci", "brc":"birinci", "bürümcük":"birinci", "derince'yi":"birinci",
    "ikincilik": "ikinci", "dikencik": "ikinci", "köktencilik": "ikinci",
    "gelişi": "ikinci", "icon": "ikinci",
    "çoğun": "üçüncü", "çoğunun": "üçüncü", "oyuncu": "üçüncü",
    "çocuk": "üçüncü", "concord": "üçüncü", "öncü": "üçüncü", "witcher":"üçüncü",
    "call": "kol", "khon": "kol", "khor": "kol", "ozgen": "kol",
    "on": "kol", "kalk": "kol", "kovana": "kol", "spor": "kol",
    "kongre": "kol", "com": "kol", "oğul": "kol", "koydu": "kol",
    "gor": "kol", "cool": "kol", "ol": "kol", "ghoul": "kol",
    "çoğu": "kol", "konuk": "kol", "count": "kol", "jorge":"kol", "igor":"kol",
    "oğur":"kol", "koung":"kol", "koordine":"kol", "çokol":"kol",
    "icom": "kol gel", "konka": "kol gel", "cordelia": "kol gel",
    "korka": "kol gel", "coogan": "kol gel", "koldan": "kol gel",
    "kongra-gel": "kol gel", "shoulder": "kol gel", "organ": "kol gel",
    "onbeş": "kol gel", "order": "kol gel", "covent": "kol gel",
    "korgan": "kol gel", "cougar": "kol gel", "kardemir": "kol gel",
    "kongar": "kol gel", "jorge ev": "kol gel", "coulter": "kol gel",
    "konya":"kol gel", "kolonun":"kol", "kongreler":"kol gel", "golgeler":"kol gel",
    "iyi": "git", "yedi": "git", "diet": "git", "get": "git",
    "giyip": "git", "değiliz": "git", "though it": "git", "yiğit": "git",
    "diyetler": "gel", "diyet": "gel", "dev": "gel", "değerli": "gel",
    "geldi": "gel", "gearbox": "gel", "göl":"gel", "da":"gel", "ev":"gel",
    "general":"gel", "el":"gel", "genel":"gel",
    "orkid": "kol git", "conceal": "kol git", "orbit": "kol git", 
    "brit": "kol git", "değil":"kol git",
    "ikram": "ekran", "idrar": "ekran", "yitiren":"ekran", "goster": "göster",
    "gösterildi":"göster", "doğrudur": "durdur",
    "meyil": "mail", "meyva": "mail", "mayhew": "mail", "mayın": "mail",
    "meio": "mail", "meyve": "mail", "mayalı": "mail", "meno": "mail",
    "meal": "mail", "meryem": "mail", "meğer": "mail", "memur": "mail",
    "mev": "mail", "cindy": "mail", "menkul": "mail",
    "gonderdi": "gönder", "gonder": "gönder", "bunda": "gönder",
    "değer": "gönder",
    "mujica": "müzik"
}

def clean_text(raw_text):
    cleaned = raw_text.lower().replace("i̇", "i").strip()
    phrases = {
        "on iyi": "kol git", "kol dört": "kol git", "üç oyuncu": "üçüncü",
        "concord çoğu dev": "üçüncü kol gel", "iç önce": "üçüncü",
        "üç üçüncü": "üçüncü", "kor quiet": "kol git", "koordine et": "kol git",
        "tolga düet": "kol git", "bu gönder": "gönder", "uygun değer": "gönder",
        "konuda": "gönder", "hakkında": "gönder", "mail gönder": "mail gönder",
        "mail gonder": "mail gönder", "menkuller": "mail gönder", 
        "blogunda": "mail gönder", "golden": "mail gönder", "medyagundem": "mail gönder"
    }
    for hall, corr in phrases.items():
        cleaned = cleaned.replace(hall, corr)

    words = cleaned.split()
    for i, word in enumerate(words):
        if word in PHONETIC_MAP:
            words[i] = PHONETIC_MAP[word]

    ordinals = {"birinci", "ikinci", "üçüncü"}
    final_words = []
    for i, word in enumerate(words):
        if i > 0 and word in ordinals and word == final_words[-1]:
            continue
        final_words.append(word)
    cleaned = " ".join(final_words)

    music_fixes = {
        "şarkı birinci": "şarkı bir", "şarkı ikinci": "şarkı iki",
        "şarkı üçüncü": "şarkı üç", "şarkı dördüncü": "şarkı dört"
    }
    for ordinal, simple in music_fixes.items():
        cleaned = cleaned.replace(ordinal, simple)
    return " ".join(cleaned.split())

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
    def __init__(self, model_path, sensitivity=70):
        self.model_path = model_path
        self.sensitivity = sensitivity
        self.sample_rate = 16000
        self.chunk_size = 1024
        
        # Mute state tracking
        self.is_muted = False
        self.mute_until = 0
        
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

    def pause(self, seconds):
        """Mutes the microphone for a specific duration to avoid hardware noise."""
        self.mute_until = time.time() + seconds
        self.is_muted = True
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
                
                # --- THE MUTE LOGIC ---
                if self.is_muted:
                    if time.time() < self.mute_until:
                        continue # Throw away the audio data while servos move
                    else:
                        self.is_muted = False
                        self.rec.Reset() # Clear Vosk's buffer of any partial noises
                        print("[STATUS] Mic READY. Listening for commands...")
                
                if self.rec.AcceptWaveform(data):
                    process_start_time = time.time() # Start stopwatch
                    res = json.loads(self.rec.Result())
                    raw_text = res.get("text", "").strip()
                    
                    if not raw_text:
                        continue
                        
                    # 1. Apply Interceptor mapping
                    text = clean_text(raw_text)
                    
                    # 2. Print detailed debug logs
                    print(f"\n[VOICE] Raw Heard : {raw_text}")
                    if raw_text != text:
                        print(f"[VOICE] Corrected : {text}")
                        
                    # 3. Validate
                    match, score = self.validate_command(text)
                    process_time_ms = (time.time() - process_start_time) * 1000 # End stopwatch
                    
                    if match:
                        print(f"[VOICE] Processing Time: {process_time_ms:.1f} ms")
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

            # Execute commands and trigger hardware mute
            if cmd in ["müzik aç", "müzik çal", "şarkı bir", "şarkı iki", "şarkı üç", "şarkı dört", "müzik sustur", "sustur", "durdur", "çıkış"]:
                play_music_routine(cmd, ser_uno)
                listener.pause(0.5) # Short pause for menu/music commands

            elif cmd == "ekran göster":
                send_cmd(ser_uno, "ekran-6B7", "UNO") 
                listener.pause(1.0)
            
            elif cmd == "pompayı aç":
                send_cmd(ser_mega, "POMPAC", "MEGA")
                listener.pause(1.0)
                
            elif cmd == "pompayı kapat":
                send_cmd(ser_mega, "POMPKAPAT", "MEGA")
                listener.pause(1.0)
                
            elif "kol gel" in cmd or "kol git" in cmd:
                send_cmd(ser_mega, cmd.upper(), "MEGA")
                listener.pause(1.5) # LONG pause for noisy servo movement
                
            elif cmd in ("ac", "aç", "kapat", "kol"):
                send_cmd(ser_mega, cmd.upper(), "MEGA")
                listener.pause(1.5)
                
    except KeyboardInterrupt:
        print("\n[STATUS] Stopping System...")
    finally:
        if ser_uno: ser_uno.close()
        if ser_mega: ser_mega.close()
        GPIO.cleanup() 
        print("[STATUS] GPIO Cleaned. Exiting.")
