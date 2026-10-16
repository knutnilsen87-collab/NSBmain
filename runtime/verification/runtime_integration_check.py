import sys
from pathlib import Path

def verify():
    required_modules = [
        "runtime.core.batch_inference",
        "runtime.streaming.session_runtime",
        "runtime.worker.worker_execution_flow",
        "runtime.scheduler.gpu_scheduler",
        "runtime.telemetry.runtime_metrics",
        "runtime.telemetry.runtime_tracing",
        "runtime.policy.tenant_quota_enforcement",
        "runtime.eval.evaluation_runner"
    ]

    for mod in required_modules:
        __import__(mod)

    return True

if __name__ == "__main__":
    assert verify() is True
    print("RUNTIME_INTEGRATION_OK")
