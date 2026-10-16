class CanaryRelease:

    def __init__(self, percentage=5):
        self.percentage = percentage

    def route(self, request_id):
        return (hash(request_id) % 100) < self.percentage
