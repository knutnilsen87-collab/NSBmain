import hashlib
from pathlib import Path

class ModelIntegrity:

    @staticmethod
    def sha256(path):
        h = hashlib.sha256()
        with open(path,"rb") as f:
            for chunk in iter(lambda: f.read(8192),b""):
                h.update(chunk)
        return h.hexdigest()

    @staticmethod
    def verify(path, expected_hash):
        return ModelIntegrity.sha256(path) == expected_hash
