"""
Fon kuzatuv ishchilari (faqat ish vaqti oynasida ishlaydi):

1) CameraWatcher — kirish kameralari (ATTENDANCE_CAMERAS). Doimiy RTSP ulanish,
   sekundiga ~2 kadr yuz aniqlash → xodim yoki notanish "ko'rinish" (Sighting) yoziladi.
2) DeskMonitor — xodimlarga biriktirilgan xona yoki joylar. Har daqiqada 1 kadr:
   xodim o'z joyida bormi (yuz yoki belgilangan zona orqali) → DeskSample.
3) Kunlik tozalash — eski rasm fayllari o'chiriladi.
"""

from __future__ import annotations

import os
import threading
import time
import uuid
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path
from typing import Deque, Dict, List, Optional, Tuple

import cv2
import numpy as np
from sqlmodel import select

from config import settings
from database import Coverage, DeskSample, Employee, Sighting, get_session
from face_engine import FaceResult, crop_face, decode_jpeg, emb_to_bytes, encode_jpeg, face_engine
from activity import motion_mask, recorder, to_small
from alerts import bus
from database import Alert
from rtsp_manager import capture_snapshot, nvr_online, publish_frame
from settings_store import store

SIGHTINGS_DIR = settings.DATA_DIR / "sightings"
_arrivals: Dict[str, set] = {}
_arrivals_lock = threading.Lock()


def announce_arrival(employee_id: int, name: str, channel: int, sighting: Sighting) -> None:
    """Xodimning bugungi birinchi ko'rinishi — "keldi" xabari (kechikish bilan)."""
    day = sighting.date
    with _arrivals_lock:
        seen = _arrivals.setdefault(day, set())
        if employee_id in seen:
            return
        seen.add(employee_id)
        for d in [d for d in _arrivals if d != day]:
            _arrivals.pop(d, None)
    with get_session() as s:
        exists = s.exec(select(Alert).where(Alert.date == day, Alert.kind == "arrival",
                                            Alert.employee_id == employee_id)).first()
        emp = s.get(Employee, employee_id)
    if exists or not emp:
        return
    start = datetime.combine(sighting.ts.date(), settings.parse_hhmm(emp.work_start))
    late = int((sighting.ts - start).total_seconds() // 60)
    late_txt = f" — {late} daqiqa kechikdi" if late > settings.LATE_GRACE_MINUTES else ""
    bus.create("arrival", f"{name} keldi ({sighting.ts:%H:%M}){late_txt}", emp.position or "",
               severity="warning" if late_txt else "info", channel=channel, employee_id=employee_id,
               snapshot_path=sighting.face_path, notify=bool(store.get("announce_arrivals")))


def _rel(p: Path) -> str:
    return p.relative_to(settings.DATA_DIR).as_posix()


def save_sighting(channel: int, frame: np.ndarray, face: FaceResult, ts: datetime,
                  annotated: Optional[np.ndarray] = None) -> Sighting:
    day_dir = SIGHTINGS_DIR / ts.strftime("%Y-%m-%d")
    day_dir.mkdir(parents=True, exist_ok=True)
    stem = f"ch{channel:02d}_{ts:%H%M%S}_{uuid.uuid4().hex[:6]}"
    face_p = day_dir / f"{stem}_face.jpg"
    frame_p = day_dir / f"{stem}_frame.jpg"
    face_p.write_bytes(encode_jpeg(crop_face(frame, face), 90))
    frame_p.write_bytes(encode_jpeg(annotated if annotated is not None else frame, 70, max_side=960))
    row = Sighting(
        ts=ts, date=ts.strftime("%Y-%m-%d"), channel=channel,
        employee_id=face.employee_id, similarity=face.similarity,
        face_path=_rel(face_p), frame_path=_rel(frame_p),
        embedding=emb_to_bytes(face.embedding),
    )
    with get_session() as s:
        s.add(row)
        s.commit()
        s.refresh(row)
    return row


# =============================================================================
# 1. KIRISH KAMERASI KUZATUVCHISI
# =============================================================================

class CameraWatcher:
    def __init__(self, channel: int, manager: "WorkerManager") -> None:
        self.channel = channel
        self.manager = manager
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._last_known: Dict[int, float] = {}
        self._recent_unknown: Deque[Tuple[float, np.ndarray]] = deque(maxlen=50)
        self._coverage_id: Optional[int] = None
        self._coverage_touch = 0.0
        self._prev_small: Optional[np.ndarray] = None
        self._last_forced = 0.0
        self._weak_hit: Dict[int, float] = {}
        self.stats = {
            "channel": channel, "state": "to'xtatilgan", "connected": False,
            "last_frame_at": None, "frames_processed": 0, "skipped_static": 0, "faces_detected": 0,
            "sightings": 0, "resolution": None, "last_error": None,
        }

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name=f"watch-ch{self.channel:02d}", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _open(self) -> Optional[cv2.VideoCapture]:
        url = settings.get_live_rtsp(self.channel, sub_stream=not settings.ATTENDANCE_USE_MAIN_STREAM)
        os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp")
        cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
        if not cap.isOpened():
            cap.release()
            return None
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        return cap

    def _touch_coverage(self, now: datetime) -> None:
        if time.time() - self._coverage_touch < 60:
            return
        self._coverage_touch = time.time()
        with get_session() as s:
            cov = s.get(Coverage, self._coverage_id) if self._coverage_id else None
            if cov and cov.date == now.strftime("%Y-%m-%d") and (now - cov.end_ts).total_seconds() < 180:
                cov.end_ts = now
            else:
                cov = Coverage(channel=self.channel, date=now.strftime("%Y-%m-%d"), start_ts=now, end_ts=now)
            s.add(cov)
            s.commit()
            s.refresh(cov)
            self._coverage_id = cov.id

    def _is_duplicate_unknown(self, emb: np.ndarray, now: float) -> bool:
        window = settings.SIGHTING_COOLDOWN_SECONDS * 3
        for ts, e in self._recent_unknown:
            if now - ts < window and float(e @ emb) >= settings.FACE_MATCH_THRESHOLD:
                return True
        return False

    def _has_motion(self, frame: np.ndarray) -> bool:
        """Arzon harakat filtri: harakat yo'q bo'lsa yuz aniqlash (~200 ms) o'tkazib yuboriladi."""
        small = to_small(frame)
        prev, self._prev_small = self._prev_small, small
        if prev is None:
            return True
        changed, mask = motion_mask(prev, small)
        recorder.record(self.channel, changed, mask if changed > 0.002 else None, frame=frame)
        now = time.time()
        if changed > 0.002 or now - self._last_forced > 10:
            self._last_forced = now
            return True
        return False

    def _process(self, frame: np.ndarray) -> None:
        if not self._has_motion(frame):
            self.stats["skipped_static"] += 1
            return
        faces = face_engine.analyze(frame, channel=self.channel)
        self.stats["frames_processed"] += 1
        usable = [f for f in faces if not f.too_small and f.embedding is not None]
        self.stats["faces_detected"] += len(usable)
        if not usable:
            return
        now_t = time.time()
        now = datetime.now()
        annotated = None
        for f in usable:
            if f.known and f.similarity < settings.FACE_STRONG_MATCH:
                previous = self._weak_hit.get(f.employee_id, 0.0)
                self._weak_hit[f.employee_id] = now_t
                if now_t - previous > settings.FACE_CONFIRM_SECONDS:
                    continue  # kuchsiz moslik — ikkinchi kadr tasdiqlamaguncha yozilmaydi
            if f.known:
                if now_t - self._last_known.get(f.employee_id, 0) < settings.SIGHTING_COOLDOWN_SECONDS:
                    self._last_known[f.employee_id] = now_t
                    continue
                self._last_known[f.employee_id] = now_t
            else:
                if self._is_duplicate_unknown(f.embedding, now_t):
                    continue
                self._recent_unknown.append((now_t, f.embedding))
            if annotated is None:
                annotated = face_engine.annotate(frame, faces)
            row = save_sighting(self.channel, frame, f, now, annotated)
            self.stats["sightings"] += 1
            self.manager.push_event(row, f.name)
            try:
                if f.known:
                    announce_arrival(f.employee_id, f.name or "", self.channel, row)
                elif store.get("alert_unknown_face") and bus.allow(f"unk-{self.channel}", store.get("alert_unknown_cooldown_min")):
                    bus.create("unknown_face", "Notanish odam aniqlandi",
                               "Tizim bu yuzni tanimadi. Xodim bo'lsa — «Xodimlar» sahifasida biriktiring.",
                               severity="warning", channel=self.channel, frame=annotated, notify=False)  # faqat saytda
            except Exception as e:
                print(f"[watcher] alert xatosi: {e}")

    def _run(self) -> None:
        cap: Optional[cv2.VideoCapture] = None
        interval = 1.0 / max(0.2, settings.ATTENDANCE_PROCESS_FPS)
        last_proc = 0.0
        fails = 0
        while not self._stop.is_set():
            if not face_engine.available:
                self.stats["state"] = "model kutilmoqda"
                time.sleep(10)
                continue
            if not (self.manager.force_on or settings.in_monitor_window()):
                if cap is not None:
                    cap.release()
                    cap = None
                self.stats.update(state="ish vaqti emas (kutish)", connected=False)
                time.sleep(20)
                continue
            if cap is None:
                if not nvr_online():
                    self.stats.update(state="NVR ulanmagan", connected=False)
                    time.sleep(15)
                    continue
                self.stats["state"] = "ulanmoqda..."
                cap = self._open()
                if cap is None:
                    self.stats.update(state="ulanmadi", connected=False,
                                      last_error=f"{datetime.now():%H:%M:%S} RTSP ochilmadi")
                    time.sleep(10)
                    continue
                self.stats.update(state="kuzatmoqda", connected=True, last_error=None)
                fails = 0
            if not cap.grab():
                fails += 1
                if fails > 50:
                    cap.release()
                    cap = None
                    self.stats.update(connected=False, last_error=f"{datetime.now():%H:%M:%S} oqim uzildi")
                time.sleep(0.05)
                continue
            fails = 0
            now_t = time.time()
            if now_t - last_proc < interval:
                continue
            last_proc = now_t
            ok, frame = cap.retrieve()
            if not ok or frame is None:
                continue
            now = datetime.now()
            self.stats["last_frame_at"] = now.isoformat(timespec="seconds")
            self.stats["resolution"] = f"{frame.shape[1]}x{frame.shape[0]}"
            publish_frame(self.channel, frame, sub_stream=not settings.ATTENDANCE_USE_MAIN_STREAM)
            try:
                self._touch_coverage(now)
                self._process(frame)
            except Exception as e:
                self.stats["last_error"] = f"{now:%H:%M:%S} {str(e)[:120]}"
        if cap is not None:
            cap.release()
        self.stats.update(state="to'xtatilgan", connected=False)


# =============================================================================
# 2. ISH STOLI MONITORI
# =============================================================================

class _PersonDetector:
    """Ish joyida odam bormi — YOLOv8n."""

    def __init__(self) -> None:
        self._model = None
        self._tried = False
        self._lock = threading.Lock()

    def _load(self):
        if self._tried:
            return self._model
        self._tried = True
        path = Path(settings.YOLO_MODEL_PATH) if settings.YOLO_MODEL_PATH else settings.BASE_DIR.parent / "yolov8n.pt"
        if not path.exists():
            print(f"[DeskMonitor] YOLO modeli topilmadi: {path} — zona tekshiruvi o'chirilgan")
            return None
        try:
            from ultralytics import YOLO
            self._model = YOLO(str(path))
        except Exception as e:
            print(f"[DeskMonitor] YOLO yuklanmadi: {e}")
        return self._model

    def person_boxes(self, img: np.ndarray, conf: float = 0.35, imgsz: int = 1280) -> List[Tuple[float, float, float, float]]:
        with self._lock:
            model = self._load()
            if model is None:
                return []
            res = model(img, classes=[0], conf=conf, imgsz=imgsz, verbose=False)
        boxes = []
        for r in res:
            for b in r.boxes.xyxy.cpu().numpy().tolist():
                boxes.append(tuple(b))
        return boxes


person_detector = _PersonDetector()


def parse_zone(zone: Optional[str]) -> Optional[Tuple[float, float, float, float]]:
    if not zone:
        return None
    try:
        x1, y1, x2, y2 = (float(v) for v in zone.split(","))
        return min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)
    except ValueError:
        return None


def box_in_zone(box, zone, w: int, h: int) -> bool:
    zx1, zy1, zx2, zy2 = zone[0] * w, zone[1] * h, zone[2] * w, zone[3] * h
    bx1, by1, bx2, by2 = box
    ix = max(0.0, min(bx2, zx2) - max(bx1, zx1))
    iy = max(0.0, min(by2, zy2) - max(by1, zy1))
    return ix * iy / max(1.0, (bx2 - bx1) * (by2 - by1)) >= 0.4


def assigned_workplace_channels() -> List[int]:
    with get_session() as s:
        rows = s.exec(select(Employee.desk_channel).where(Employee.active == True, Employee.desk_channel != None)).all()  # noqa: E711,E712
    return sorted(set(rows))


def _box_at(boxes, x: float, y: float) -> Optional[int]:
    inside = [i for i, b in enumerate(boxes) if b[0] <= x <= b[2] and b[1] <= y <= b[3]]
    return min(inside, key=lambda i: (boxes[i][2] - boxes[i][0]) * (boxes[i][3] - boxes[i][1])) if inside else None


_last_face_at: Dict[int, float] = {}  # xonadagi odamlarni xodimlarga taqsimlashda oxirgi ko'ringani ustun
_seat_prev: Dict[int, np.ndarray] = {}
_seat_active_at: Dict[int, float] = {}
_room_prev: Dict[int, np.ndarray] = {}
_room_active_at: Dict[int, float] = {}


def _seat_gray(crop: np.ndarray) -> np.ndarray:
    gray = cv2.GaussianBlur(cv2.cvtColor(cv2.resize(crop, (320, 180)), cv2.COLOR_BGR2GRAY), (5, 5), 0).astype(np.int16)
    return gray - int(np.median(gray))  # umumiy yorug'lik o'zgarishini chiqarib tashlaydi


def _room_live_boxes(channel: int, img: np.ndarray, boxes) -> List[int]:
    """Butun xona rejimi: harakatsiz "odam" ramkalari (bo'sh stul) hisobga olinmaydi."""
    h, w = img.shape[:2]
    gray = _seat_gray(img)
    prev = _room_prev.get(channel)
    _room_prev[channel] = gray
    now = time.time()
    if prev is not None:
        changed = np.abs(gray - prev) > 14
        sx, sy = gray.shape[1] / w, gray.shape[0] / h
        for b in boxes:
            part = changed[int(b[1] * sy):max(int(b[3] * sy), int(b[1] * sy) + 1), int(b[0] * sx):max(int(b[2] * sx), int(b[0] * sx) + 1)]
            if float(np.mean(part)) * 100 >= settings.SEAT_CHANGE_PERCENT:
                _room_active_at[channel] = now
                break
    active = now - _room_active_at.get(channel, 0.0) <= settings.SEAT_HOLD_CHECKS * settings.DESK_INTERVAL_SECONDS
    return list(range(len(boxes))) if active else []


def seat_occupied(employee_id: int, img: np.ndarray, zone, w: int, h: int) -> bool:
    """Orqasi o'girilgan yoki stul to'sib turgan odam: joyning kesimida odam izlanadi va joydagi harakat o'lchanadi.

    Oxirgi harakatdan keyin bir necha tekshiruv davomida joyida deb hisoblanadi (kitob o'qib qimirlamay o'tirishi mumkin).
    """
    crop = img[int(zone[1] * h):max(int(zone[3] * h), int(zone[1] * h) + 2), int(zone[0] * w):max(int(zone[2] * w), int(zone[0] * w) + 2)]
    now = time.time()
    gray = _seat_gray(crop)
    prev = _seat_prev.get(employee_id)
    _seat_prev[employee_id] = gray
    moved = prev is not None and float(np.mean(np.abs(gray - prev) > 14)) * 100 >= settings.SEAT_CHANGE_PERCENT
    if moved or person_detector.person_boxes(crop, conf=0.25, imgsz=640):
        _seat_active_at[employee_id] = now
    return now - _seat_active_at.get(employee_id, 0.0) <= settings.SEAT_HOLD_CHECKS * settings.DESK_INTERVAL_SECONDS


def check_desks_once(channel: int, scan=None) -> Dict[int, Tuple[bool, str]]:
    """Bitta xonani tekshiradi. Qaytaradi: {employee_id: (present, method)}, faqat shu xonaga biriktirilganlar.

    method: face — yuzi tanildi; seat — belgilangan joyda odam yoki harakat bor (orqasi o'girilgan bo'lsa ham);
    room — xonada odam bor (yuzi ko'rinmadi).
    Boshqa xodim sifatida tanilgan odam birovning joyini band qilmaydi.
    """
    with get_session() as s:
        assigned = s.exec(select(Employee).where(Employee.active == True, Employee.desk_channel == channel)).all()  # noqa: E712
    if not assigned:
        return {}
    if scan is None:
        jpeg = capture_snapshot(channel, sub_stream=False, timeout_seconds=8.0)
        img = decode_jpeg(jpeg) if jpeg else None
        if img is None:
            return {}
        boxes = person_detector.person_boxes(img)
        scan = (img, face_engine.analyze(img, channel=channel), boxes, None)
    img, faces, boxes, live = scan
    h, w = img.shape[:2]
    taken: Dict[int, int] = {}
    by_face: Dict[int, Tuple[float, float]] = {}
    for f in faces:
        if not f.known or f.similarity < settings.FACE_STRONG_MATCH:
            continue  # bitta kadrda kuchsiz moslikka ishonib bo'lmaydi
        cx, cy = f.box[0] + f.box[2] / 2, f.box[1] + f.box[3] / 2
        by_face[f.employee_id] = (cx, cy)
        _last_face_at[f.employee_id] = time.time()
        i = _box_at(boxes, cx, cy)
        if i is not None:
            taken[i] = f.employee_id

    result: Dict[int, Tuple[bool, str]] = {}
    in_room: List[Employee] = []
    for emp in assigned:
        zone = parse_zone(emp.desk_zone)
        if zone is None:
            in_room.append(emp)
        elif emp.id in by_face:
            x, y = by_face[emp.id]
            result[emp.id] = (zone[0] * w <= x <= zone[2] * w and zone[1] * h <= y <= zone[3] * h, "face")
        else:
            # Butun kadrdagi ramkaga ishonilmaydi: bo'sh stulni ham odam deb ko'rsatadi (CH-04 da tekshirilgan).
            occupied_by_other = any(i in taken and box_in_zone(b, zone, w, h) for i, b in enumerate(boxes))
            seat = seat_occupied(emp.id, img, zone, w, h) and not occupied_by_other
            if seat:
                taken.update({i: emp.id for i, b in enumerate(boxes) if i not in taken and box_in_zone(b, zone, w, h)})
            result[emp.id] = (seat, "seat")

    if live is None:
        live = _room_live_boxes(channel, img, boxes)
    free = [i for i in live if i not in taken]
    for emp in sorted(in_room, key=lambda e: (e.id not in by_face, -_last_face_at.get(e.id, 0.0))):
        if emp.id in by_face:
            result[emp.id] = (True, "face")
        elif free:
            free.pop(0)
            result[emp.id] = (True, "room")
        else:
            result[emp.id] = (False, "room")
    return result


class DeskMonitor:
    def __init__(self, manager: "WorkerManager") -> None:
        self.manager = manager
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.stats = {"state": "to'xtatilgan", "last_check_at": None, "channels": [],
                      "last_result": {}, "now": {}, "last_error": None}
        self._last_tick: Optional[float] = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="desk-monitor", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def run_once(self) -> Dict[int, Dict[int, Tuple[bool, str]]]:
        import presence

        now = datetime.now()
        day = now.strftime("%Y-%m-%d")
        t_now = now.timestamp()
        since = self._last_tick or t_now - settings.DESK_INTERVAL_SECONDS
        # bir necha kamera skanlansa tekshiruv minutdan uzoq cho'ziladi — yozuv haqiqiy oraliqni oladi
        interval = int(min(3 * settings.DESK_INTERVAL_SECONDS, max(settings.DESK_INTERVAL_SECONDS, t_now - since)))
        self._last_tick = t_now
        rooms = presence.load_rooms()
        room_ch = presence.room_of_channel(rooms)
        desk_channels = set(assigned_workplace_channels())
        channels = sorted(set(room_ch) | desk_channels)
        online = nvr_online()
        with ThreadPoolExecutor(max_workers=4) as pool:
            jpegs = list(pool.map(lambda c: capture_snapshot(c, sub_stream=False, timeout_seconds=8.0) if online else None, channels))
        ev = presence.Evidence(nvr_online=online)
        seen_rooms: set = set()
        out = {}
        rows = []
        for ch, jpeg in zip(channels, jpegs):
            img = decode_jpeg(jpeg) if jpeg else None
            room = room_ch.get(ch)
            if img is None:
                if room is not None:
                    ev.failed_rooms.add(room)
                continue
            seen_rooms.add(room)
            faces = face_engine.analyze(img, channel=ch)
            boxes = person_detector.person_boxes(img)
            live = _room_live_boxes(ch, img, boxes)
            if room is not None:
                ev.live_people[room] = ev.live_people.get(room, 0) + len(live)
                for f in faces:  # bir kadrda ikki joyda ko'rinsa — kuchliroq moslik qoladi
                    if f.known and f.similarity >= settings.FACE_STRONG_MATCH and f.similarity > ev.faces.get(f.employee_id, (0, 0.0))[1]:
                        ev.faces[f.employee_id] = (room, f.similarity)
            if ch not in desk_channels:
                continue
            res = check_desks_once(ch, (img, faces, boxes, live))
            out[ch] = res
            for eid, (present, method) in res.items():
                rows.append(DeskSample(ts=now, date=day, channel=ch, employee_id=eid,
                                       present=present, method=method, interval_seconds=interval))
                self.stats["now"][eid] = {"channel": ch, "present": present, "method": method,
                                          "at": now.isoformat(timespec="seconds")}
                if room is not None:
                    ev.occupied[eid] = (room, present)
        ev.failed_rooms -= seen_rooms  # xonaning boshqa kamerasi ishlagan bo'lsa, xona ko'rindi
        self._presence(presence, now, day, since, interval, ev, rooms, rows)
        if rows:
            with get_session() as s:
                s.add_all(rows)
                s.commit()
        self.stats.update(last_check_at=now.isoformat(timespec="seconds"), channels=channels,
                          last_result={ch: {eid: p for eid, (p, _) in r.items()} for ch, r in out.items()})
        return out

    @staticmethod
    def _presence(presence, now: datetime, day: str, since: float, interval: int, ev, rooms, rows: list) -> None:
        from database import PresenceSample
        import staff_service

        att = settings.attendance_channels
        with get_session() as s:
            sightings = s.exec(select(Sighting).where(Sighting.date == day, Sighting.channel.in_(att)).order_by(Sighting.ts)).all()
            emps = {e.id: e for e in s.exec(select(Employee).where(Employee.active == True)).all()}  # noqa: E712
        by_emp: Dict[int, list] = {}
        for r in sightings:
            if r.employee_id is not None:
                by_emp.setdefault(r.employee_id, []).append(r)
            elif r.channel == att[-1] and r.ts.timestamp() > since:
                ev.unknown_entrance.append(r.ts.timestamp())
        for eid, rs in by_emp.items():
            fresh = [p for p in staff_service._cluster_passages(rs) if p.end.timestamp() > since]
            if fresh:
                ev.passages[eid] = (fresh[-1].direction, fresh[-1].end.timestamp())
        ev.away = presence.away_now(day, now)
        if presence.tracker.day != day:
            presence.tracker.reset(day)
        limits = presence.Limits(store.get("yard_max_min") * 60, store.get("blind_max_min") * 60, store.get("room_grace_min") * 60)
        places, blind = presence.tracker.step(now.timestamp(), ev, rooms, {e.id: e.room_id for e in emps.values()}, limits)
        for eid, (place, conf) in places.items():
            end = datetime.combine(now.date(), settings.parse_hhmm(emps[eid].work_end))
            if place == presence.OUT and now > end:
                continue  # ishdan keyin ketganlar yozilmaydi
            rows.append(PresenceSample(ts=now, date=day, employee_id=eid, place=place, conf=conf, interval_seconds=interval))
        for eid in blind:
            name = presence.place_name(presence.tracker.state[eid].place, rooms)[0]
            bus.create("agent", f"{emps[eid].full_name} uzoq vaqt ko'rinmayapti",
                       f"{store.get('blind_max_min')} daqiqadan beri kamerasiz joyda ({name}).",
                       severity="warning", employee_id=eid)

    def _run(self) -> None:
        next_at = 0.0
        while not self._stop.is_set():
            if not face_engine.available:
                self.stats["state"] = "model kutilmoqda"
                self._stop.wait(15)
                continue
            if not (self.manager.force_on or settings.in_monitor_window()):
                self.stats["state"] = "ish vaqti emas (kutish)"
                self._stop.wait(30)
                continue
            self.stats["state"] = "faol"
            if time.time() >= next_at:
                next_at = time.time() + settings.DESK_INTERVAL_SECONDS
                try:
                    self.run_once()
                    self.stats["last_error"] = None
                except Exception as e:
                    self.stats["last_error"] = f"{datetime.now():%H:%M:%S} {str(e)[:120]}"
            self._stop.wait(5)
        self.stats["state"] = "to'xtatilgan"


# =============================================================================
# 3. MENEJER
# =============================================================================

class WorkerManager:
    def __init__(self) -> None:
        self.watchers: Dict[int, CameraWatcher] = {}
        self.desk = DeskMonitor(self)
        self.force_on = False
        self.running = False
        self._events: Deque[dict] = deque(maxlen=100)
        self._events_lock = threading.Lock()
        self._cleanup_thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self.running:
            return
        self.running = True
        if settings.ATTENDANCE_ENABLED:
            for ch in settings.attendance_channels:
                w = self.watchers.get(ch) or CameraWatcher(ch, self)
                self.watchers[ch] = w
                w.start()
        if settings.DESK_ENABLED and settings.desk_channels:
            self.desk.start()
        if self._cleanup_thread is None:
            self._cleanup_thread = threading.Thread(target=self._cleanup_loop, name="sighting-cleanup", daemon=True)
            self._cleanup_thread.start()

    def stop(self) -> None:
        self.running = False
        for w in self.watchers.values():
            w.stop()
        self.desk.stop()

    def push_event(self, row: Sighting, name: Optional[str]) -> None:
        with self._events_lock:
            self._events.appendleft({
                "id": row.id, "ts": row.ts.isoformat(timespec="seconds"), "channel": row.channel,
                "employee_id": row.employee_id, "name": name or "Notanish",
                "similarity": round(row.similarity, 3), "face_url": f"/media/{row.face_path}",
            })

    def recent_events(self, limit: int = 30) -> List[dict]:
        with self._events_lock:
            return list(self._events)[:limit]

    def status(self) -> dict:
        return {
            "running": self.running,
            "nvr_online": nvr_online(),
            "force_on": self.force_on,
            "in_monitor_window": settings.in_monitor_window(),
            "monitor_window": f"{settings.MONITOR_START}–{settings.MONITOR_END}",
            "face_engine": face_engine.status(),
            "watchers": [w.stats for w in self.watchers.values()],
            "desk": self.desk.stats,
        }

    def _cleanup_loop(self) -> None:
        while True:
            try:
                cutoff = datetime.now() - timedelta(days=settings.SIGHTING_RETENTION_DAYS)
                if SIGHTINGS_DIR.exists():
                    for d in SIGHTINGS_DIR.iterdir():
                        try:
                            if d.is_dir() and datetime.strptime(d.name, "%Y-%m-%d") < cutoff:
                                for f in d.iterdir():
                                    f.unlink(missing_ok=True)
                                d.rmdir()
                        except ValueError:
                            continue
                with get_session() as s:
                    old = s.exec(select(Sighting).where(Sighting.ts < cutoff, Sighting.employee_id == None)).all()  # noqa: E711
                    for r in old:
                        s.delete(r)
                    s.commit()
            except Exception as e:
                print(f"[cleanup] xato: {e}")
            time.sleep(6 * 3600)


worker_manager = WorkerManager()
