import numpy as np

class FeatureExtractor:

    def normalize(self, audio):
        audio = np.array(audio, dtype=float)
        if np.max(np.abs(audio)) == 0:
            return audio
        return audio / np.max(np.abs(audio))

    def extract(self, audio):
        audio = self.normalize(audio)
        return np.mean(audio)
