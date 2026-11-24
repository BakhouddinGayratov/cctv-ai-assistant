"""Fon vazifalari (klip kesish, video xulosa) — progress bilan, brauzer so'rab turadi."""

from __future__ import annotations

import threading
import time
import uuid
from datetime import datetime
from typing import Callable, Dict, Optional


class Job:
    def __init__(self, kind: str, title: str) -> None:
        self.id = uuid.uuid4().hex[:12]
        self.kind = kind
        self.title = title
        self.status = "running"     # running | done | error
        self.progress = 0.0         # 0..1
        self.message = "Boshlanmoqda…"
        self.result: Optional[dict] = None
        self.started = time.time()
        self.finished: Optional[float] = None

    def update(self, progress: float, message: str) -> None:
        self.progress = max(self.progress, min(1.0, progress))
        self.message = message

    def to_dict(self) -> dict:
        return {
            "id": self.id, "kind": self.kind, "title": self.title, "status": self.status,
            "progress": round(self.progress, 3), "message": self.message, "result": self.result,
            "elapsed": round((self.finished or time.time()) - self.started, 1),
            "started_at": datetime.fromtimestamp(self.started).isoformat(timespec="seconds"),
        }


class JobManager:
    def __init__(self) -> None:
        self._jobs: Dict[str, Job] = {}
        self._lock = threading.Lock()
        self._sem = threading.Semaphore(2)  # NVR'ni ortiqcha yuklamaslik uchun bir vaqtda 2 tadan

    def submit(self, kind: str, title: str, fn: Callable[[Job], dict]) -> Job:
        job = Job(kind, title)
        with self._lock:
            self._jobs[job.id] = job
            for jid in [k for k, j in self._jobs.items() if j.finished and time.time() - j.finished > 3600]:
                self._jobs.pop(jid, None)

        def _run():
            with self._sem:
                try:
                    job.result = fn(job)
                    job.status, job.progress = "done", 1.0
                    job.message = job.message if job.message and job.message != "Boshlanmoqda…" else "Tayyor"
                except Exception as e:
                    job.status, job.message = "error", str(e)[:200]
                finally:
                    job.finished = time.time()

        threading.Thread(target=_run, name=f"job-{job.id}", daemon=True).start()
        return job

    def get(self, job_id: str) -> Optional[Job]:
        with self._lock:
            return self._jobs.get(job_id)

    def list(self) -> list:
        with self._lock:
            return [j.to_dict() for j in sorted(self._jobs.values(), key=lambda j: -j.started)][:30]


jobs = JobManager()
