"""
Kamera faolligini yozib borish:
- ActivityMinute — har daqiqadagi maksimal harakat va odamlar soni (kun chizig'i uchun).
- Issiqlik xaritasi — kun davomida harakat maskalarining yig'indisi (90x160), diskka davriy saqlanadi.
"""

from __future__ import annotations

import threading
import time
from datetime import datetime
from typing import Dict, Optional, Tuple

import cv2
import numpy as np

from config import settings
from database import ActivityMinute, get_session

HEAT_DIR = settings.DATA_DIR / "heatmaps"
HEAT_SHAPE = (90, 160)


class ActivityRecorder:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        # channel -> (date, minute, max_motion, max_people)
        self._minute: Dict[int, Tuple[str, int, float, int]] = {}
        self._heat: Dict[Tuple[int, str], np.ndarray] = {}
        self._ref_saved: Dict[Tuple[int, str, int], bool] = {}
        self._last_flush = time.time()

    def record(self, channel: int, motion: float, mask: Optional[np.ndarray] = None,
               people: int = 0, frame: Optional[np.ndarray] = None) -> None:
        now = datetime.now()
        day, minute = now.strftime("%Y-%m-%d"), now.hour * 60 + now.minute
        flush_row = None
        with self._lock:
            cur = self._minute.get(channel)
            if cur and (cur[0], cur[1]) != (day, minute):
                flush_row = cur
                cur = None
            if cur is None:
                cur = (day, minute, 0.0, 0)
            self._minute[channel] = (day, minute, max(cur[2], motion), max(cur[3], people))
            if mask is not None:
                key = (channel, day)
                acc = self._heat.get(key)
                if acc is None:
                    acc = self._heat[key] = self._load_heat(channel, day)
                m = mask if mask.shape == HEAT_SHAPE else cv2.resize(mask, HEAT_SHAPE[::-1])
                acc += (m > 0).astype(np.float32)
            ref_key = (channel, day, now.hour)
            need_ref = frame is not None and not self._ref_saved.get(ref_key)
            if need_ref:
                self._ref_saved[ref_key] = True
        if flush_row and (flush_row[2] > 0.002 or flush_row[3] > 0):
            with get_session() as s:
                s.add(ActivityMinute(channel=channel, date=flush_row[0], minute=flush_row[1],
                                     motion=round(flush_row[2], 4), people=flush_row[3]))
                s.commit()
        if need_ref:
            d = HEAT_DIR / day
            d.mkdir(parents=True, exist_ok=True)
            cv2.imwrite(str(d / f"ch{channel:02d}_ref.jpg"), cv2.resize(frame, (640, 360)), [cv2.IMWRITE_JPEG_QUALITY, 80])
        if time.time() - self._last_flush > 300:
            self.flush_heat()

    def _load_heat(self, channel: int, day: str) -> np.ndarray:
        p = HEAT_DIR / day / f"ch{channel:02d}.npy"
        if p.exists():
            try:
                return np.load(p).astype(np.float32)
            except Exception:
                pass
        return np.zeros(HEAT_SHAPE, dtype=np.float32)

    def flush_heat(self) -> None:
        with self._lock:
            items = list(self._heat.items())
            self._last_flush = time.time()
            today = datetime.now().strftime("%Y-%m-%d")
            for k in [k for k in self._heat if k[1] != today]:
                self._heat.pop(k, None)
        for (ch, day), acc in items:
            d = HEAT_DIR / day
            d.mkdir(parents=True, exist_ok=True)
            np.save(d / f"ch{ch:02d}.npy", acc)

    def heat(self, channel: int, day: str) -> Optional[np.ndarray]:
        with self._lock:
            acc = self._heat.get((channel, day))
            if acc is not None:
                return acc.copy()
        p = HEAT_DIR / day / f"ch{channel:02d}.npy"
        return np.load(p) if p.exists() else None


recorder = ActivityRecorder()


def motion_mask(prev: np.ndarray, small: np.ndarray, thresh: int = 18) -> Tuple[float, np.ndarray]:
    """Kichik kulrang kadrlar orasidagi farq: (ulush 0..1, maska)."""
    diff = cv2.absdiff(small, prev)
    mask = (diff > thresh).astype(np.uint8)
    return float(np.count_nonzero(mask)) / mask.size, mask


def to_small(frame: np.ndarray) -> np.ndarray:
    return cv2.GaussianBlur(cv2.cvtColor(cv2.resize(frame, HEAT_SHAPE[::-1]), cv2.COLOR_BGR2GRAY), (5, 5), 0)


def render_heatmap(channel: int, day: str) -> Optional[bytes]:
    """Issiqlik xaritasini kamera kadri ustiga chizib JPEG qaytaradi."""
    acc = recorder.heat(channel, day)
    if acc is None or float(acc.max()) <= 0:
        return None
    ref_p = HEAT_DIR / day / f"ch{channel:02d}_ref.jpg"
    base = cv2.imread(str(ref_p)) if ref_p.exists() else None
    if base is None:
        base = np.full((360, 640, 3), 24, dtype=np.uint8)
    norm = acc / max(1e-6, float(np.percentile(acc[acc > 0], 98)) if np.any(acc > 0) else 1.0)
    norm = np.clip(norm, 0, 1)
    norm = cv2.GaussianBlur(cv2.resize(norm, (base.shape[1], base.shape[0]), interpolation=cv2.INTER_CUBIC), (0, 0), 9)
    color = cv2.applyColorMap((norm * 255).astype(np.uint8), cv2.COLORMAP_TURBO)
    alpha = np.where(norm < 0.04, 0.0, np.clip(0.25 + norm * 0.6, 0, 0.85))[..., None]
    out = (base * (1 - alpha) + color * alpha).astype(np.uint8)
    ok, buf = cv2.imencode(".jpg", out, [cv2.IMWRITE_JPEG_QUALITY, 85])
    return buf.tobytes() if ok else None

