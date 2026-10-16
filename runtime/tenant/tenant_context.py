class TenantContext:

    def __init__(self, tenant_id):
        self.tenant_id = tenant_id

    def propagate(self, request):
        request["tenant_id"] = self.tenant_id
        return request
