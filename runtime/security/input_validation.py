class InputValidator:

    def validate_audio(self, audio):
        if not isinstance(audio, list):
            raise ValueError("invalid format")

        if len(audio) == 0:
            raise ValueError("empty audio")

        if len(audio) > 160000:
            raise ValueError("audio too large")

        return True
