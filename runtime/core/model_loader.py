import torch

class ModelLoader:
    def __init__(self, model_path):
        self.model_path = model_path
        self.model = None

    def load(self):
        self.model = torch.jit.load(self.model_path, map_location="cuda")
        self.model.eval()
        return self.model
