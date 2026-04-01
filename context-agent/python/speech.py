import pyttsx3


class SpeechActuator:
    def __init__(self):
        self.engine = pyttsx3.init()
        self.engine.setProperty("rate", 175)

    def speak(self, text: str):
        print(f"[VOICE] {text}")
        self.engine.say(text)
        self.engine.runAndWait()