class MultiRegionFailover:

    def __init__(self):
        self.regions = []

    def register(self, region):
        self.regions.append(region)

    def primary(self):
        return self.regions[0] if self.regions else None

    def failover(self):
        if len(self.regions) > 1:
            return self.regions[1]
        return None
