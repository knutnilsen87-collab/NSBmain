class QuotaManager:

    def __init__(self, limit=2):
        self.limit = limit
        self.active = 0

    def acquire(self):
        if self.active >= self.limit:
            return False
        self.active += 1
        return True

    def release(self):
        if self.active > 0:
            self.active -= 1
