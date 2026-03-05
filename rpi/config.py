# config.py

# Path to your downloaded Vosk model
MODEL_PATH = '/home/pi/Downloads/vosk-model-small-en-us-0.15'

# The list of commands you want to listen for
COMMANDS = ["close", "exit", "stop", "open"]

# How strict the matching should be (0-100)
# Lower = easier to trigger (but more false positives)
# Higher = harder to trigger (needs exact pronunciation)
SENSITIVITY = 60
