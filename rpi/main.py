import pyaudio
import json
import sys
import time
import serial
import pygame
import os
from vosk import Model, KaldiRecognizer
from fuzzywuzzy import process



#####################
## Play Audio Class ##
#####################

# Initialize mixer once at the start
try:
    pygame.mixer.init()
except Exception as e:
    print(f"[AUDIO ERROR] Mixer start failed: {e}")

def play_audio(filename, folder_path):
    """
    Plays an audio file given a filename and a folder path.
    Example: play_audio("opening.mp3", "/home/pi/Music")
    """
    full_path = os.path.join(folder_path, filename)

    if not os.path.exists(full_path):
        print(f"[AUDIO ERROR] File not found: {full_path}")
        return

    try:
        # Check if audio is already playing and stop it (optional)
        if pygame.mixer.music.get_busy():
            pygame.mixer.music.stop()
            
        pygame.mixer.music.load(full_path)
        pygame.mixer.music.play()
        print(f"[AUDIO] Playing: {filename}")
    except Exception as e:
        print(f"[AUDIO FAILED] {e}")
        
# ==========================================
# QUICK CONFIGURATION
# ==========================================
MODEL_PATH = '/home/pi/Downloads/vosk-model-tr-0.18-robotarm' 
SERIAL_PORT = '/dev/ttyACM0'  # CHECK YOUR PORT
BAUD_RATE = 9600

# ADDED "left" AND "right" TO COMMANDS
COMMANDS = ["bir","iki", "üç", "sol","kapat","gel", "gaz aç", "aç", "light on", "left", "right","kumanda"]
SENSITIVITY = 70

# Ensure UTF-8 output
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

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
        self.p = None
        self.stream = None
        
        if not os.path.exists(self.model_path):
            raise FileNotFoundError(f"Model not found at {self.model_path}")

        print(f"[INIT] Loading Vosk Model...")
        model = Model(self.model_path)
        self.rec = KaldiRecognizer(model, self.sample_rate)
    def start(self):
        self.p = pyaudio.PyAudio()
        dev_idx = None
        # Auto-detect ReSpeaker or use default
        for i in range(self.p.get_device_count()):
            try:
                if "seeed" in self.p.get_device_info_by_index(i).get("name", "").lower():
                    dev_idx = i; break
            except: continue
            
        print(f"[INIT] Microphone Index: {dev_idx if dev_idx else 'Default'}")
        
        self.stream = self.p.open(format=pyaudio.paInt16, channels=1, rate=self.sample_rate,
                                  input=True, input_device_index=dev_idx, frames_per_buffer=self.chunk_size)
        self.stream.start_stream()

    def stop(self):
        if self.stream: self.stream.stop_stream(); self.stream.close()
        if self.p: self.p.terminate()
    def listen(self):
        print("[STATUS] Listening...")

        while True:
            try:
                data = self.stream.read(self.chunk_size, exception_on_overflow=False)

                # Only process when Vosk confirms a full waveform
                if self.rec.AcceptWaveform(data):

                    res = json.loads(self.rec.Result())
                    self.rec.Reset()

                    text = res.get("text", "").strip()

                    # Ignore empty recognitions
                    if not text:
                        time.sleep(0.)
                        continue

                    print("[STATUS] Processing... please wait")
                    print(f"[RAW] Vosk heard: {text}")

                    # First check exact match
                    if text in self.commands:
                        yield text, 100
                    else:
                        # Fuzzy match fallback
                        match, score = process.extractOne(text, self.commands)

                        if score >= self.sensitivity:
                            yield match, score
                        else:
                            print(f"[INFO] No strong match (score={score})")

                    print("[STATUS] Ready for next command in 2 seconds...")
                    time.sleep(0.35)

                    print("[STATUS] Listening again...")

                # Small throttle to prevent CPU overload
                time.sleep(0.01)

            except KeyboardInterrupt:
                break

            except Exception as e:
                print(f"[ERROR] Listener: {e}")
                break
# ==========================================
# Sending Serial Commandss:.
# ==========================================
def send_cmd(ser, cmd: str):
    if not ser:
        print("[SERIAL] Not connected")
        return

    msg = cmd.strip().upper() + "\n"
    ser.write(msg.encode("utf-8"))
    ser.flush()
    print(f"[SERIAL] Sent: {msg.strip()}")

# ==========================================
# MAIN EXECUTION
# ==========================================

if __name__ == "__main__":
    # CONFIG
    AUDIO_FOLDER_TR = "/home/pi/HospitalVC/Audios/TR" 

    ser = None
    listener = None
    play_audio("SistemHazir.mp3", AUDIO_FOLDER_TR)
    try:
        # 1. SETUP SERIAL
        try:
            ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
            time.sleep(2)
        except:
            print("[WARNING] Serial failed. Voice only.")

        # 2. START LISTENER
        listener = ActiveListener(MODEL_PATH, COMMANDS, SENSITIVITY)
        listener.start()

        # 3. LOOP
        for command, score in listener.listen():
            print(f"\n>>> MATCH: '{command}' ({score})")

            cmd = command.strip().lower()

            # "stop" was removed here because it's not in your COMMANDS list. 
            # If you want to use "stop", add it to the COMMANDS array at the top!
            if cmd in ("kapat"):  
                send_cmd(ser, cmd)  # send to Arduino
                play_audio("komutAlindi.mp3", AUDIO_FOLDER_TR)
            if cmd in ("aç"):  
                send_cmd(ser, cmd)  # send to Arduino
                play_audio("komutAlindi.mp3", AUDIO_FOLDER_TR)
            # Replaced "exit" and "close" with "kapat" which IS in your COMMANDS list
     

    except KeyboardInterrupt:
        print("\n[STOP] User interrupted.")
    finally:
        if listener: listener.stop()
        if ser: ser.close()
        pygame.mixer.quit() # Clean up audio
