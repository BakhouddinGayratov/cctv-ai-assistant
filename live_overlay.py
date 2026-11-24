"""
Jonli ko'rish ustidagi belgilar: odam ramkasi, ismi (yoki "Notanish") va ish zonasida ekani.

Oqim sub-stream'da (yuzlar juda kichik), shuning uchun tahlil fon oqimlarida asosiy sifatli kadrda bajariladi,
natija nisbiy koordinatalarda saqlanib har kadrga chiziladi. Faqat hozir ko'rilayotgan kameralar tahlil qilinadi.
"""

from __future__ import annotations

import threading
import time
from typing import Dict, List, Optional, Set, Tuple

import cv2
import numpy as np
from PIL import Image, ImageDraw
from sqlmodel import select

from config import settings
from database import Employee, get_session
from face_engine import decode_jpeg, face_engine
from rtsp_manager import capture_snapshot
from workers import _box_at, box_in_zone, parse_zone, person_detector, worker_manager

_WANTED_SECONDS = 5.0     # shuncha vaqt ko'rilmasa kamera tahlildan chiqadi
_MAX_AGE = 8.0            # bundan eski natija chizilmaydi (ramka odamdan ajralib qolardi)
_WORKERS = 2

GREEN, RED, AMBER, GRAY = (52, 211, 153), (244, 63, 94), (251, 191, 36), (148, 163, 184)
IN_ZONE, OUT_ZONE = "ish zonasida", "ish zonasidan tashqarida"


def analyze_channel(channel: int) -> Optional[dict]:
    jpeg = capture_snapshot(channel, sub_stream=False, max_attempts=1, timeout_seconds=4.0)
    img = decode_jpeg(jpeg) if jpeg else None
    if img is None:
        return None
    h, w = img.shape[:2]
    street = channel in settings.street_channels
    faces = face_engine.analyze(img, channel=channel)
    boxes = [] if street else person_detector.person_boxes(img, conf=0.25, imgsz=1280)
    with get_session() as s:
        emps = {e.id: e for e in s.exec(select(Employee).where(Employee.active == True)).all()}  # noqa: E712
    here = [e for e in emps.values() if e.desk_channel == channel]
    zones = {e.id: z for e in here if (z := parse_zone(e.desk_zone))}
    recognized = {f.employee_id for f in faces if f.known}

    def zone_status(employee_id: Optional[int], box) -> str:
        if employee_id is not None:
            emp = emps.get(employee_id)
            if emp is None or emp.desk_channel != channel:
                return OUT_ZONE
            zone = zones.get(employee_id)
            return IN_ZONE if zone is None or box_in_zone(box, zone, w, h) else OUT_ZONE
        if not here:
            return ""
        return IN_ZONE if any(box_in_zone(box, z, w, h) for z in zones.values()) else OUT_ZONE

    def describe(box, face) -> Tuple[Tuple[int, int, int], str, str]:
        if face is not None and face.known:
            return GREEN, f"{face.name} {int(face.similarity * 100)}%", zone_status(face.employee_id, box)
        if face is not None and not face.too_small:
            return RED, "Notanish", zone_status(None, box)
        # Yuzi ko'rinmaydi: belgilangan joyda bo'lsa, o'sha joy egasi deb ko'rsatiladi
        owner = next((e for e in here if e.id in zones and e.id not in recognized and box_in_zone(box, zones[e.id], w, h)), None)
        if owner is not None:
            return GREEN, f"{owner.full_name} (joyi bo'yicha)", IN_ZONE
        return AMBER, "Yuzi ko'rinmaydi", zone_status(None, box)

    by_box: Dict[int, object] = {}
    loose = []
    for f in faces:
        i = _box_at(boxes, f.box[0] + f.box[2] / 2, f.box[1] + f.box[3] / 2)
        if i is None:
            loose.append(f)
        elif i not in by_box or f.known:
            by_box[i] = f

    people = [(*b, *describe(b, by_box.get(i))) for i, b in enumerate(boxes)]
    for f in loose:
        b = (f.box[0], f.box[1], f.box[0] + f.box[2], f.box[1] + f.box[3])
        people.append((*b, *describe(b, f)))

    now_state = worker_manager.desk.stats.get("now", {})
    seats = []
    for e in here:
        if e.id not in zones:
            continue
        state = now_state.get(e.id)
        color, text = (GRAY, "tekshirilmoqda") if state is None else (GREEN, "joyida") if state["present"] else (RED, "yo'q")
        seats.append((*zones[e.id], color, f"{e.full_name} · {text}"))
    return {
        "people": [(x1 / w, y1 / h, x2 / w, y2 / h, c, a, b) for x1, y1, x2, y2, c, a, b in people],
        "seats": seats,
    }


def render(frame: np.ndarray, result: dict) -> np.ndarray:
    if not result["people"] and not result["seats"]:
        return frame
    h, w = frame.shape[:2]
    pil = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(pil)
    font = face_engine._font(max(11, w // 52))

    def tag(x: float, y: float, text: str, color) -> float:
        l, t, r, b = draw.textbbox((0, 0), text, font=font)
        tw, th = r - l, b - t
        x = max(0, min(x, w - tw - 8))
        draw.rectangle([x, y, x + tw + 8, y + th + 7], fill=color)
        draw.text((x + 4, y + 2 - t), text, fill=(10, 10, 20), font=font)
        return th + 8

    for x1, y1, x2, y2, color, text in result["seats"]:
        draw.rectangle([x1 * w, y1 * h, x2 * w, y2 * h], outline=color, width=1)
        tag(x1 * w, max(0, y2 * h - font.size - 9), text, color)
    for x1, y1, x2, y2, color, name, status in result["people"]:
        draw.rectangle([x1 * w, y1 * h, x2 * w, y2 * h], outline=color, width=max(2, w // 400))
        lines = [name] + ([status] if status else [])
        y = max(0.0, y1 * h - (font.size + 9) * len(lines))
        for line in lines:
            y += tag(x1 * w, y, line, color)
    return cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)


class LiveOverlay:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._wanted: Dict[int, float] = {}
        self._done: Dict[int, float] = {}
        self._results: Dict[int, Tuple[float, dict]] = {}
        self._busy: Set[int] = set()
        self._started = False

    def draw(self, frame: np.ndarray, channel: int) -> np.ndarray:
        now = time.time()
        with self._lock:
            self._wanted[channel] = now
            if not self._started:
                self._started = True
                for _ in range(_WORKERS):
                    threading.Thread(target=self._loop, name="live-overlay", daemon=True).start()
            item = self._results.get(channel)
        if item is None or now - item[0] > _MAX_AGE:
            return frame
        return render(frame, item[1])

    def _next(self) -> Optional[int]:
        now = time.time()
        with self._lock:
            ready: List[int] = [ch for ch, t in self._wanted.items() if now - t <= _WANTED_SECONDS and ch not in self._busy
                                and now - self._done.get(ch, 0.0) >= 1.0]
            if not ready:
                return None
            ch = min(ready, key=lambda c: self._done.get(c, 0.0))
            self._busy.add(ch)
            return ch

    def _loop(self) -> None:
        while True:
            ch = self._next()
            if ch is None:
                time.sleep(0.2)
                continue
            try:
                result = analyze_channel(ch) if face_engine.available else None
                if result is not None:
                    with self._lock:
                        self._results[ch] = (time.time(), result)
            except Exception as e:
                print(f"[live_overlay ch{ch}] {e}")
            finally:
                with self._lock:
                    self._busy.discard(ch)
                    self._done[ch] = time.time()


live_overlay = LiveOverlay()
