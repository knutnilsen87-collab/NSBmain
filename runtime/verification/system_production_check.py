import sys
from pathlib import Path

def verify_system():

    modules = [
        "runtime.core.batch_inference",
        "runtime.streaming.session_runtime",
        "runtime.worker.worker_execution_flow",
        "runtime.scheduler.gpu_scheduler",
        "runtime.policy.runtime_error_policy",
        "runtime.policy.tenant_quota_enforcement",
        "runtime.telemetry.runtime_metrics",
        "runtime.telemetry.runtime_tracing",
        "runtime.eval.evaluation_runner"
    ]

    for m in modules:
        __import__(m)

    return True

if __name__ == "__main__":
    assert verify_system()
    print("SYSTEM_READY")
