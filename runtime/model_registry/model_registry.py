class ModelRegistry:

    def __init__(self):
        self.models = {}

    def register(self, name, version, path):
        key = f"{name}:{version}"
        self.models[key] = path

    def resolve(self, name, version):
        key = f"{name}:{version}"
        return self.models.get(key)
