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
from fuzzywuzzy import process

# ==========================================
# CONFIG & INIT
# ==========================================
MODEL_PATH = '/home/pi/Downloads/vosk-model-tr-0.18-robotarm'
MEGA_PORT = '/dev/arduino_mega' # Update to actual Uno port
UNO_PORT = '/dev/arduino_icu' # Update to actual Mega port
BAUD_RATE = 9600
AUDIO_FOLDER = "/home/pi/HospitalVC/Audios/TR"

VALID_UID_HEX = "633A18F6B7"

# Commands based on system spec
COMMANDS = [
    "birinci kol gel", "birinci kol git", 
    "ikinci kol gel", "ikinci kol git", 
    "üçüncü kol gel", "üçüncü kol git",
    "ekran göster", "pompayı aç", "pompayı kapat",
    "kol"
]
SENSITIVITY = 70

system_active = False 

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
    def __init__(self, model_path, commands, sensitivity=60):
        self.model_path = model_path
        self.commands = commands
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

    def listen(self):
        while True:
            try:
                data = self.stream.read(self.chunk_size, exception_on_overflow=False)
                if self.rec.AcceptWaveform(data):
                    res = json.loads(self.rec.Result())
                    self.rec.Reset()
                    text = res.get("text", "").strip()
                    if not text:
                        continue
                    
                    if text in self.commands:
                        yield text, 100
                    else:
                        match, score = process.extractOne(text, self.commands)
                        if score >= self.sensitivity:
                            yield match, score
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

    # --- Thread 1: Mega Serial Listener ---
    def mega_listener():
        while True:
            if ser_mega and ser_mega.in_waiting > 0:
                line = ser_mega.readline().decode('utf-8').strip()
                if line:
                    print(f"[MEGA DEBUG] {line}")
            time.sleep(0.1)

    # --- Thread 2: RPi RFID Scanner ---
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

    # Start Background Threads
    threading.Thread(target=mega_listener, daemon=True).start()
    threading.Thread(target=rfid_listener, daemon=True).start()

    # Block main thread until RFID sets system_active to True
    print("[STATUS] Waiting for RFID Verification to boot voice processing...")
    try:
        while not system_active:
            time.sleep(0.5)
            
        # RFID Validated! Now load Vosk and open the microphone.
        listener = ActiveListener(MODEL_PATH, COMMANDS, SENSITIVITY)
        listener.start()

        for command, score in listener.listen():
            cmd = command.lower()
            print(f">>> {cmd} ({score})")

            # Route to UNO
            if cmd == "ekran göster":
                send_cmd(ser_uno, "ekran-8F6", "UNO") 
            
            # Route to MEGA
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
