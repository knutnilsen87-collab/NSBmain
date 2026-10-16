from dataclasses import dataclass
from typing import Any, Dict, Optional
import uuid

@dataclass
class WorkerJob:
    job_id: str
    tenant_id: str
    payload: Any
    model_id: str
    status: str = "QUEUED"

class JobDispatcher:
    def __init__(self):
        self.queue = []

    def create_job(self, tenant_id: str, payload: Any, model_id: str) -> WorkerJob:
        job = WorkerJob(
            job_id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            payload=payload,
            model_id=model_id,
        )
        self.queue.append(job)
        return job

    def dispatch(self) -> Optional[WorkerJob]:
        if not self.queue:
            return None
        job = self.queue.pop(0)
        job.status = "DISPATCHED"
        return job
