import numpy as np

class StreamingDecodePipeline:
    def __init__(self, model):
        self.model = model
        self.buffer = []

    def push_audio_chunk(self, chunk):
        self.buffer.append(chunk)

    def process(self):
        if len(self.buffer) == 0:
            return None

        audio = np.concatenate(self.buffer)
        self.buffer = []

        # placeholder decode call
        result = self.model(audio)

        return result
