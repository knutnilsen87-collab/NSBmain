class FailoverDrill:

    def __init__(self):
        self.events = []

    def simulate_failure(self, region):
        self.events.append(("fail", region))

    def activate_failover(self, backup_region):
        self.events.append(("failover", backup_region))
        return backup_region

    def drill_success(self):
        return any(e[0]=="failover" for e in self.events)
