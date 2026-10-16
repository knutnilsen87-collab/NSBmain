class RuntimePolicy:

    def __init__(self):
        pass

    def handle_error(self, error_type):
        if error_type == "GPU_UNAVAILABLE":
            return "QUEUE_RETRY"

        if error_type == "DECODE_FAILURE":
            return "FAIL_REQUEST"

        if error_type == "WORKER_TIMEOUT":
            return "RETRY"

        return "UNKNOWN_ERROR"
