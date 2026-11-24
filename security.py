"""
Bosqich 2 — xavfsizlik kuzatuvi (yengil sub-stream, ~1 kadr/s):

- Ish vaqtidan tashqari harakat: harakat 2 kadr ketma-ket → YOLO odam/mashina tasdig'i → alert + 10 s klip.
- Kamera aloqasi: NVR ishlayotgan bo'lsa-yu, kamera 3 daqiqa javob bermasa → alert.
- Har kadr faollik yozuvchisiga (kun chizig'i + issiqlik xaritasi) uzatiladi.
"""

from __future__ import annotations

import os
import threading
import time
from datetime import datetime
from typing import Dict, List, Optional

import cv2
import numpy as np

from activity import motion_mask, recorder, to_small
from alerts import bus
from config import settings
from rtsp_manager import nvr_online, publish_frame, record_live_clip
from settings_store import store


def in_after_hours(now: Optional[datetime] = None) -> bool:
    now = now or datetime.now()
    if store.get("after_hours_weekends") and now.weekday() not in settings.work_days:
        return True
    start = settings.parse_hhmm(store.get("after_hours_start"))
    end = settings.parse_hhmm(store.get("after_hours_end"))
    t = now.time()
    return (t >= start or t < end) if start > end else (start <= t < end)


# ----------------------------------------------------------------------------- YOLO
class _Yolo:
    def __init__(self) -> None:
        self._model = None
        self._tried = False
        self._lock = threading.Lock()

    def detect(self, img: np.ndarray, classes=(0, 2, 3, 7), conf: float = 0.4) -> List[dict]:
        with self._lock:
            if not self._tried:
                self._tried = True
                from pathlib import Path
                path = Path(settings.YOLO_MODEL_PATH) if settings.YOLO_MODEL_PATH else settings.BASE_DIR.parent / "yolov8n.pt"
                if path.exists():
                    try:
                        from ultralytics import YOLO
                        self._model = YOLO(str(path))
                    except Exception as e:
                        print(f"[security] YOLO yuklanmadi: {e}")
            if self._model is None:
                return []
            res = self._model(img, classes=list(classes), conf=conf, verbose=False)
        out = []
        names = {0: "odam", 2: "mashina", 3: "mototsikl", 7: "yuk mashinasi"}
        for r in res:
            for box, cls, c in zip(r.boxes.xyxy.cpu().numpy(), r.boxes.cls.cpu().numpy(), r.boxes.conf.cpu().numpy()):
                out.append({"box": [int(v) for v in box], "label": names.get(int(cls), "obyekt"), "conf": float(c)})
        return out


yolo = _Yolo()


def draw_boxes(img: np.ndarray, dets: List[dict]) -> np.ndarray:
    out = img.copy()
    for d in dets:
        x1, y1, x2, y2 = d["box"]
        cv2.rectangle(out, (x1, y1), (x2, y2), (60, 60, 240), 2)
        cv2.putText(out, f"{d['label']} {int(d['conf'] * 100)}%", (x1, max(14, y1 - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (60, 60, 240), 2)
    return out


# ----------------------------------------------------------------------------- kuzatuvchi
class SecurityWatcher:
    def __init__(self, channel: int, manager: "SecurityManager") -> None:
        self.channel = channel
        self.manager = manager
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._prev: Optional[np.ndarray] = None
        self._motion_streak = 0
        self.latest: Optional[np.ndarray] = None
        self.last_ok = time.time()
        self.stats = {"channel": channel, "state": "to'xtatilgan", "connected": False, "motion": 0.0,
                      "last_frame_at": None, "alerts": 0}

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name=f"sec-ch{self.channel:02d}", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _open(self) -> Optional[cv2.VideoCapture]:
        os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp")
        cap = cv2.VideoCapture(settings.get_live_rtsp(self.channel, sub_stream=True), cv2.CAP_FFMPEG)
        if not cap.isOpened():
            cap.release()
            return None
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        return cap

    def _after_hours(self, frame: np.ndarray, motion: float) -> None:
        if not store.get("alert_after_hours") or self.channel not in store.get("security_cameras"):
            return
        if not in_after_hours():
            self._motion_streak = 0
            return
        self._motion_streak = self._motion_streak + 1 if motion > 0.01 else 0
        if self._motion_streak < 2:
            return
        self._motion_streak = 0
        cooldown = store.get("after_hours_cooldown_min")
        if not bus.allow(f"ah-check-{self.channel}", 0.5):
            return
        dets = yolo.detect(frame)
        if not dets:
            return
        if not bus.allow(f"ah-{self.channel}", cooldown):
            return
        what = ", ".join(sorted({d["label"] for d in dets}))
        cam = settings.get_camera(self.channel)["name"]
        alert = bus.create("after_hours", f"Ish vaqtidan tashqari: {what} aniqlandi",
                           f"{datetime.now():%H:%M} — {cam}", severity="critical",
                           channel=self.channel, frame=draw_boxes(frame, dets))
        self.stats["alerts"] += 1

        def _clip():
            name = record_live_clip(self.channel, 10)
            if name:
                bus.update_clip(alert.id, name)

        threading.Thread(target=_clip, daemon=True).start()

    def _run(self) -> None:
        cap: Optional[cv2.VideoCapture] = None
        last_proc = 0.0
        while not self._stop.is_set():
            if not nvr_online():
                self.stats.update(state="NVR ulanmagan", connected=False)
                if cap is not None:
                    cap.release()
                    cap = None
                self.last_ok = time.time()  # NVR o'zi o'chiq — kamera aybi emas
                time.sleep(15)
                continue
            if cap is None:
                cap = self._open()
                if cap is None:
                    self.stats.update(state="ulanmadi", connected=False)
                    self.manager.check_offline(self)
                    time.sleep(10)
                    continue
                self.stats.update(state="kuzatmoqda", connected=True)
            if not cap.grab():
                cap.release()
                cap = None
                continue
            now = time.time()
            if now - last_proc < 1.0:
                continue
            last_proc = now
            ok, frame = cap.retrieve()
            if not ok or frame is None:
                continue
            self.last_ok = now
            self.latest = frame
            publish_frame(self.channel, frame, sub_stream=True)
            small = to_small(frame)
            if self._prev is None:
                self._prev = small
                continue
            motion, mask = motion_mask(self._prev, small)
            self._prev = small
            self.stats.update(motion=round(motion, 4), last_frame_at=datetime.now().isoformat(timespec="seconds"))
            try:
                recorder.record(self.channel, motion, mask if motion > 0.002 else None, frame=frame)
                self._after_hours(frame, motion)
            except Exception as e:
                print(f"[security ch{self.channel}] {e}")
        if cap is not None:
            cap.release()
        self.stats.update(state="to'xtatilgan", connected=False)


class SecurityManager:
    def __init__(self) -> None:
        self.watchers: Dict[int, SecurityWatcher] = {}

    def channels(self) -> List[int]:
        return sorted(set(store.get("security_cameras")))

    def start(self) -> None:
        wanted = set(self.channels())
        for ch, w in list(self.watchers.items()):
            if ch not in wanted:
                w.stop()
                self.watchers.pop(ch)
        for ch in wanted:
            if ch not in self.watchers:
                self.watchers[ch] = SecurityWatcher(ch, self)
            self.watchers[ch].start()

    def stop(self) -> None:
        for w in self.watchers.values():
            w.stop()

    def check_offline(self, w: SecurityWatcher) -> None:
        if store.get("alert_camera_offline") and time.time() - w.last_ok > 180 and nvr_online():
            if bus.allow(f"offline-{w.channel}", 60):
                bus.create("camera_offline", f"{settings.get_camera(w.channel)['name']} javob bermayapti",
                           "Kamera 3 daqiqadan beri oqim bermayapti — kabel yoki elektrni tekshiring.",
                           severity="warning", channel=w.channel)

    def status(self) -> dict:
        return {"after_hours_now": in_after_hours(), "watchers": [w.stats for w in self.watchers.values()]}


security_manager = SecurityManager()
