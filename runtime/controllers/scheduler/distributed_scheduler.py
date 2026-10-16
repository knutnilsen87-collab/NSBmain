class DistributedScheduler:

    def __init__(self):
        self.nodes = []

    def register_node(self, node):
        self.nodes.append(node)

    def leader(self):
        if not self.nodes:
            return None
        return sorted(self.nodes)[0]
