from dataclasses import dataclass
from typing import Optional
import time

@dataclass
class WorkerJob:
    job_id: str
    payload: dict
    retries: int = 0
    status: str = "QUEUED"

class WorkerExecutor:

    def __init__(self, decoder, max_retries=3):
        self.decoder = decoder
        self.max_retries = max_retries

    def lease(self, job: WorkerJob):
        job.status = "LEASED"
        return job

    def execute(self, job: WorkerJob):
        try:
            result = self.decoder.decode(job.payload)
            job.status = "COMPLETED"
            return result
        except Exception:
            job.retries += 1
            if job.retries >= self.max_retries:
                job.status = "FAILED"
                raise
            job.status = "RETRY"
            return None

    def ack(self, job: WorkerJob):
        if job.status == "COMPLETED":
            return True
        return False
