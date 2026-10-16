"""Måler høyeste minnebruk under en kjøring: RAM for prosessen og GPU-minne.

RAM leses med psutil når det er installert, ellers med ``resource`` (Linux og
macOS). GPU-minne leses med ``nvidia-smi`` for hele kortet, fordi
CTranslate2 ikke rapporterer eget forbruk; tallet inkluderer derfor andre
programmer som bruker GPU-en samtidig, og en måling uten nvidia-smi gir
``None``.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading


def _rss_mb() -> float | None:
    try:
        import psutil  # type: ignore

        return psutil.Process(os.getpid()).memory_info().rss / 2**20
    except Exception:  # noqa: BLE001
        pass
    try:
        import resource

        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return peak / 2**20 if sys.platform == "darwin" else peak / 1024
    except Exception:  # noqa: BLE001
        return None


def _gpu_used_mb() -> float | None:
    exe = shutil.which("nvidia-smi")
    if not exe:
        return None
    try:
        out = subprocess.run(
            [exe, "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5,
        ).stdout
        values = [float(x) for x in out.split() if x.strip()]
        return max(values) if values else None
    except Exception:  # noqa: BLE001
        return None


class PeakMemory:
    """Kontekst som måler høyeste RAM og GPU-minne mens den er aktiv.

    >>> with PeakMemory(interval=0.5) as pm:
    ...     work()
    >>> pm.result()
    {'peak_rss_mb': 2310.4, 'peak_gpu_mb': 5120.0, 'gpu_baseline_mb': 410.0, 'sampler': 'psutil'}
    """

    def __init__(self, interval: float = 1.0, gpu: bool = True):
        self.interval = interval
        self.gpu = gpu
        self.peak_rss = None
        self.peak_gpu = None
        self.gpu_baseline = None
        self._stop = threading.Event()
        self._thread = None

    def _sample(self):
        rss = _rss_mb()
        if rss is not None:
            self.peak_rss = rss if self.peak_rss is None else max(self.peak_rss, rss)
        if self.gpu:
            g = _gpu_used_mb()
            if g is not None:
                self.peak_gpu = g if self.peak_gpu is None else max(self.peak_gpu, g)

    def _run(self):
        while not self._stop.wait(self.interval):
            self._sample()

    def __enter__(self):
        if self.gpu:
            self.gpu_baseline = _gpu_used_mb()
        self._sample()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)
        self._sample()
        return False

    def result(self) -> dict:
        try:
            import psutil  # type: ignore  # noqa: F401

            sampler = "psutil"
        except Exception:  # noqa: BLE001
            sampler = "resource"
        r = lambda v: None if v is None else round(v, 1)  # noqa: E731
        return {
            "peak_rss_mb": r(self.peak_rss),
            "peak_gpu_mb": r(self.peak_gpu),
            "gpu_baseline_mb": r(self.gpu_baseline),
            "sampler": sampler,
        }
