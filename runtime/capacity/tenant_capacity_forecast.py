class TenantCapacityForecast:

    def __init__(self):
        self.history = {}

    def record(self, tenant, workload):
        self.history.setdefault(tenant, []).append(workload)

    def forecast(self, tenant):
        if tenant not in self.history:
            return 0
        h = self.history[tenant]
        return sum(h) / len(h)
