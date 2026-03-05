# ==========================================
# LISTENER CLASS (UPDATED)
# ==========================================
class ActiveListener:
    def __init__(self, model_path, commands, sensitivity=60):
        self.model_path = model_path
        self.commands = commands
        self.sensitivity = sensitivity
        self.sample_rate = 16000
        self.chunk_size = 4096
        self.p = None
        self.stream = None
        
        # --- AUDIO OUTPUT INIT ---
        try:
            pygame.mixer.init()
            print("[INIT] Audio Mixer Started")
        except Exception as e:
            print(f"[ERROR] Audio Mixer failed: {e}")

        # --- VOSK INIT ---
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
                info = self.p.get_device_info_by_index(i)
                if "seeed" in info.get("name", "").lower():
                    dev_idx = i
                    print(f"[INIT] ReSpeaker found at index {dev_idx}")
                    break
            except: continue
            
        if dev_idx is None:
            print("[INIT] Using Default Microphone")

        self.stream = self.p.open(format=pyaudio.paInt16, channels=1, rate=self.sample_rate,
                                  input=True, input_device_index=dev_idx, frames_per_buffer=self.chunk_size)
        self.stream.start_stream()

    def play_audio(self, file_path):
        """
        Plays an audio file if it exists.
        Use .mp3 or .wav for best compatibility.
        """
        if not file_path: return
            
        if os.path.exists(file_path):
            try:
                if pygame.mixer.music.get_busy():
                    pygame.mixer.music.stop() # Optional: Stop current sound to play new one
                pygame.mixer.music.load(file_path)
                pygame.mixer.music.play()
                print(f"[AUDIO] Playing: {os.path.basename(file_path)}")
            except Exception as e:
                print(f"[AUDIO ERROR] Could not play file: {e}")
        else:
            print(f"[AUDIO WARNING] File not found: {file_path}")

    def stop(self):
        if self.stream: self.stream.stop_stream(); self.stream.close()
        if self.p: self.p.terminate()
        pygame.mixer.quit() # Cleanup audio

    def _match_command(self, text): ##Matching Commands by fuzzy matcher
    if not text:
        return None, 0
    words = text.lower().split()
    # 1. Direct match (best and fastest)
    for w in words:
        if w in self.commands:
            return w, 100
    # 2. Fuzzy match per word (fallback)
    best_cmd, best_score = None, 0
    for w in words:
        cmd, score = process.extractOne(w, self.commands)
        if score > best_score:
            best_cmd, best_score = cmd, score
    if best_score >= self.sensitivity:
        return best_cmd, best_score
    return None, 0

    def listen(self):
        print("[STATUS] Listening...")
        while True:
            try:
                data = self.stream.read(self.chunk_size, exception_on_overflow=False)
                if self.rec.AcceptWaveform(data):
                    res = json.loads(self.rec.Result())
                    text = res.get("text", "").strip()
                    
                    if text:
                        print(f"Heard: '{text}'")
                        cmd, score = self._match_command(text)
                        if cmd:
                            yield cmd, score
            except KeyboardInterrupt: break
            except Exception as e: print(f"[ERROR] Listener: {e}"); break
