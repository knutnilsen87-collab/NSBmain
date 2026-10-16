class TenantQuotaManager:

    def __init__(self):
        self.usage = {}
        self.quotas = {}

    def set_quota(self, tenant, limit):
        self.quotas[tenant] = limit
        self.usage[tenant] = 0

    def check_and_consume(self, tenant):
        if tenant not in self.quotas:
            return False

        if self.usage[tenant] >= self.quotas[tenant]:
            return False

        self.usage[tenant] += 1
        return True
