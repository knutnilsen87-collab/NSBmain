class WorkerAutoscaler:

    def __init__(self, scale_up=10, scale_down=2):
        self.scale_up = scale_up
        self.scale_down = scale_down

    def decision(self, queue_depth):
        if queue_depth > self.scale_up:
            return "scale_up"
        if queue_depth < self.scale_down:
            return "scale_down"
        return "stable"
