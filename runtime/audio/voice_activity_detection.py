import numpy as np

class VoiceActivityDetection:

    def detect(self, audio, threshold=0.02):
        audio = np.array(audio)
        energy = np.mean(np.abs(audio))
        return energy > threshold
