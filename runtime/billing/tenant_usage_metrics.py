class TenantUsageMetrics:

    def __init__(self):
        self.usage = {}

    def record(self, tenant, audio_seconds):
        self.usage.setdefault(tenant,0)
        self.usage[tenant] += audio_seconds

    def usage_report(self):
        return self.usage

    def billing_estimate(self, price_per_minute):
        result = {}
        for tenant, seconds in self.usage.items():
            minutes = seconds / 60
            result[tenant] = minutes * price_per_minute
        return result
