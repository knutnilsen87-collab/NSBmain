class GPUResourceManager:

    def __init__(self, gpu_count=1):
        self.gpus = [{"id":i,"busy":False} for i in range(gpu_count)]

    def available(self):
        return [g for g in self.gpus if not g["busy"]]

    def allocate(self):
        for g in self.gpus:
            if not g["busy"]:
                g["busy"] = True
                return g["id"]
        return None

    def release(self, gpu_id):
        for g in self.gpus:
            if g["id"] == gpu_id:
                g["busy"] = False
