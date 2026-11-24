"""
Xodimlar davomati va effektivlik hisob-kitoblari + chat uchun faktlar yig'ish.

Kelish/ketish yo'nalishi:
- Ikkala kirish kamerasi (tashqi → ichki) bir o'tishda ko'rsa — kameralar tartibidan aniqlanadi.
- Aks holda o'tishlar navbatma-navbat (KIRDI, CHIQDI, KIRDI...) deb olinadi.
"""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import date as date_cls, datetime, timedelta
from typing import Dict, List, Optional, Tuple

import numpy as np
from sqlmodel import select

from config import settings
import presence
from database import AwayPeriod, Coverage, DeskSample, Employee, Sighting, get_session
from settings_store import store
from face_engine import bytes_to_emb, decode_jpeg, encode_jpeg, face_engine
from rtsp_manager import capture_snapshot


def _norm(text: str) -> str:
    t = text.lower()
    for ch in "‘’ʻʼ`´":
        t = t.replace(ch, "'")
    return t


def _combine(day: str, hhmm: str) -> datetime:
    return datetime.combine(datetime.strptime(day, "%Y-%m-%d").date(), settings.parse_hhmm(hhmm))


def employees_all(active_only: bool = False) -> Dict[int, Employee]:
    with get_session() as s:
        q = select(Employee)
        if active_only:
            q = q.where(Employee.active == True)  # noqa: E712
        return {e.id: e for e in s.exec(q).all()}


# =============================================================================
# O'TISHLAR (passages) VA DAVOMAT
# =============================================================================

@dataclass
class Passage:
    start: datetime
    end: datetime
    channels: List[int]
    direction: Optional[str] = None  # "IN" | "OUT"
    sighting_ids: List[int] = field(default_factory=list)
    face_path: str = ""
    frame_path: str = ""


def _cluster_passages(rows: List[Sighting]) -> List[Passage]:
    window = timedelta(minutes=settings.PASSAGE_WINDOW_MINUTES)
    out: List[Passage] = []
    for r in rows:
        if out and r.ts - out[-1].end <= window:
            p = out[-1]
            p.end = r.ts
            p.channels.append(r.channel)
            p.sighting_ids.append(r.id)
        else:
            out.append(Passage(start=r.ts, end=r.ts, channels=[r.channel], sighting_ids=[r.id],
                               face_path=r.face_path, frame_path=r.frame_path))
    order = settings.attendance_channels
    if len(order) >= 2:
        outer, inner = order[0], order[-1]
        for p in out:
            if outer in p.channels and inner in p.channels:
                p.direction = "IN" if p.channels.index(outer) < p.channels.index(inner) else "OUT"
    prev = None
    for p in out:
        if p.direction is None:
            p.direction = "IN" if prev in (None, "OUT") else "OUT"
        prev = p.direction
    return out


def daily_attendance(day: Optional[str] = None) -> dict:
    day = day or date_cls.today().isoformat()
    is_today = day == date_cls.today().isoformat()
    now = datetime.now()
    emps = employees_all(active_only=True)
    att = settings.attendance_channels
    with get_session() as s:
        sightings = s.exec(select(Sighting).where(Sighting.date == day).order_by(Sighting.ts)).all()
        desk = s.exec(select(DeskSample).where(DeskSample.date == day).order_by(DeskSample.ts)).all()

    by_emp: Dict[int, List[Sighting]] = {}
    unknown = []
    for r in sightings:
        if r.employee_id is None:
            unknown.append(r)
        elif r.channel in att:
            by_emp.setdefault(r.employee_id, []).append(r)
    desk_by_emp: Dict[int, List[DeskSample]] = {}
    for d in desk:
        desk_by_emp.setdefault(d.employee_id, []).append(d)

    rooms = presence.load_rooms()
    psamples = presence.samples_for(day)
    with get_session() as s:
        aways = s.exec(select(AwayPeriod).where(AwayPeriod.date == day)).all()
    lunch = (store.get("lunch_start"), store.get("lunch_end"))
    entrance_unknown = [u.ts for u in unknown if u.channel == att[-1]] if att else []

    rows, events = [], []
    late_n = early_n = present_n = 0
    total_office = 0.0
    for eid, emp in sorted(emps.items(), key=lambda kv: kv[1].full_name):
        passages = _cluster_passages(by_emp.get(eid, []))
        dsamples = desk_by_emp.get(eid, [])
        present_desk = [d for d in dsamples if d.present]

        office_min = 0.0
        in_since: Optional[datetime] = None
        for p in passages:
            if p.direction == "IN" and in_since is None:
                in_since = p.start
            elif p.direction == "OUT" and in_since is not None:
                office_min += (p.end - in_since).total_seconds() / 60
                in_since = None
        exit_unknown = False
        if in_since is not None:
            if is_today:
                office_min += (now - in_since).total_seconds() / 60
            else:
                last_seen = max([d.ts for d in present_desk], default=in_since)
                office_min += max(0.0, (last_seen - in_since).total_seconds() / 60)
                exit_unknown = True

        arrived = next((p.start for p in passages if p.direction == "IN"), None)
        arrived_approx = False
        if arrived is None and present_desk:
            arrived, arrived_approx = present_desk[0].ts, True
            end_ref = now if is_today else present_desk[-1].ts
            office_min = (end_ref - arrived).total_seconds() / 60
        left = passages[-1].end if passages and passages[-1].direction == "OUT" else None
        work_end = _combine(day, emp.work_end)
        pb = presence.breakdown(psamples[eid], rooms, work_end, lunch, store.get("yard_max_min")) if eid in psamples else None
        if pb and pb["first_seen"] and arrived is None:
            # kirishda tanilmagan, keyin xonasida tanildi: undan oldingi 15 daqiqada kirgan notanish odam — o'sha
            before = [t for t in entrance_unknown if pb["first_seen"] - timedelta(minutes=15) <= t <= pb["first_seen"]]
            arrived, arrived_approx = (before[0] if before else pb["first_seen"]), True
        if pb and pb["last_seen"] and left is None and (not is_today or now > work_end):
            left, exit_unknown = pb["last_seen"], True

        if arrived is None:
            status = "kelmagan"
        elif left is None and is_today:
            status = "ofisda"
        elif exit_unknown:
            status = "chiqish qayd etilmagan"
        else:
            status = "ketgan"

        late_min = 0
        if arrived is not None:
            start_dt = _combine(day, emp.work_start)
            if arrived > start_dt + timedelta(minutes=settings.LATE_GRACE_MINUTES):
                late_min = int((arrived - start_dt).total_seconds() // 60)
        early_min = 0
        if left is not None:
            end_dt = _combine(day, emp.work_end)
            if left < end_dt:
                early_min = int((end_dt - left).total_seconds() // 60)

        desk_min = sum(d.interval_seconds for d in present_desk) / 60
        eff = min(100, round(desk_min / office_min * 100)) if office_min > 0 and dsamples else None
        if pb:
            t = pb["time"]
            tracked = sum(t.values()) - t["tushlik"]
            desk_min = sum(t[k] for k in presence.WORK_CATEGORIES)
            office_min = max(office_min, tracked - t["tashqarida"] - t["safar"])
            eff = min(100, round(desk_min / tracked * 100)) if tracked > 0 else None
        cur = presence.tracker.current(eid) if is_today else None
        now_place = None
        if cur:
            name, kind = presence.place_name(cur.place, rooms)
            now_place = {"name": name, "kind": kind, "conf": cur.conf,
                         "since": datetime.fromtimestamp(cur.last_seen).isoformat(timespec="minutes")}

        if arrived is not None:
            present_n += 1
        late_n += 1 if late_min else 0
        early_n += 1 if early_min else 0
        total_office += office_min

        rows.append({
            "id": eid, "name": emp.full_name, "position": emp.position,
            "work_start": emp.work_start, "work_end": emp.work_end,
            "arrived": arrived.isoformat(timespec="minutes") if arrived else None,
            "arrived_approx": arrived_approx,
            "left": left.isoformat(timespec="minutes") if left else None,
            "status": status, "late_minutes": late_min, "early_minutes": early_min,
            "office_minutes": round(office_min), "desk_minutes": round(desk_min),
            "away_minutes": round(max(0.0, office_min - desk_min)) if dsamples else None,
            "efficiency": eff,
            "time": pb["time"] if pb else None,
            "places": pb["places"] if pb else [],
            "now_place": now_place,
            "room": rooms[emp.room_id].name if emp.room_id in rooms else None,
            "away": [{"id": a.id, "start": a.start, "end": a.end, "reason": a.reason} for a in aways if a.employee_id == eid],
            "confirmed_minutes": round(sum(d.interval_seconds for d in present_desk if d.method == "face") / 60),
            "workplace": {"channel": emp.desk_channel, "camera": settings.get_camera(emp.desk_channel)["name"],
                          "mode": "zone" if emp.desk_zone else "room"} if emp.desk_channel else None,
            "passages": [{"ts": p.start.isoformat(timespec="seconds"), "direction": p.direction,
                          "channels": sorted(set(p.channels))} for p in passages],
            "desk_timeline": [{"ts": d.ts.isoformat(timespec="minutes"), "present": d.present}
                              for d in dsamples],
        })
        for p in passages:
            events.append({"ts": p.start.isoformat(timespec="seconds"), "employee_id": eid,
                           "name": emp.full_name, "direction": p.direction,
                           "channel": p.channels[0], "face_url": f"/media/{p.face_path}",
                           "frame_url": f"/media/{p.frame_path}"})
    for u in unknown:
        events.append({"ts": u.ts.isoformat(timespec="seconds"), "employee_id": None, "name": "Notanish",
                       "direction": None, "channel": u.channel, "sighting_id": u.id,
                       "face_url": f"/media/{u.face_path}", "frame_url": f"/media/{u.frame_path}"})
    events.sort(key=lambda e: e["ts"], reverse=True)

    return {
        "date": day,
        "summary": {
            "total_employees": len(emps), "present": present_n, "late": late_n,
            "early_leave": early_n, "total_office_hours": round(total_office / 60, 1),
            "unknown_faces": len(unknown),
        },
        "employees": rows,
        "events": events,
    }


# =============================================================================
# KAMERA BO'YICHA ODAMLAR SONI (DB dan) VA QAMROV
# =============================================================================

def coverage_ratio(channel: int, start: datetime, end: datetime) -> float:
    total = (end - start).total_seconds()
    if total <= 0:
        return 0.0
    with get_session() as s:
        segs = s.exec(select(Coverage).where(Coverage.channel == channel,
                                             Coverage.end_ts >= start, Coverage.start_ts <= end)).all()
    covered = 0.0
    for c in segs:
        a, b = max(c.start_ts, start), min(c.end_ts + timedelta(seconds=60), end)
        covered += max(0.0, (b - a).total_seconds())
    return min(1.0, covered / total)


def _cluster_unknown(embs: List[np.ndarray]) -> int:
    reps: List[np.ndarray] = []
    for e in embs:
        if not any(float(r @ e) >= settings.FACE_MATCH_THRESHOLD for r in reps):
            reps.append(e)
    return len(reps)


def people_on_camera(channel: int, start: datetime, end: datetime) -> dict:
    emps = employees_all()
    with get_session() as s:
        rows = s.exec(select(Sighting).where(Sighting.channel == channel, Sighting.ts >= start,
                                             Sighting.ts <= end).order_by(Sighting.ts)).all()
    known: Dict[int, List[str]] = {}
    unknown_embs = []
    for r in rows:
        if r.employee_id is not None:
            known.setdefault(r.employee_id, []).append(r.ts.strftime("%H:%M"))
        else:
            v = bytes_to_emb(r.embedding)
            if v.shape[0] == face_engine.dim:
                unknown_embs.append(v)
    return {
        "channel": channel, "camera": settings.get_camera(channel)["name"],
        "from": start.isoformat(timespec="minutes"), "to": end.isoformat(timespec="minutes"),
        "coverage": round(coverage_ratio(channel, start, end), 2),
        "known": [{"name": emps[e].full_name if e in emps else f"#{e}", "times": t} for e, t in known.items()],
        "unknown_people_estimate": _cluster_unknown(unknown_embs),
        "unknown_sightings": len(unknown_embs),
        "total_people_estimate": len(known) + _cluster_unknown(unknown_embs),
    }


# =============================================================================
# XODIMNI TOPISH ("X qayerda?")
# =============================================================================

def last_seen(employee_id: int) -> Optional[dict]:
    with get_session() as s:
        r = s.exec(select(Sighting).where(Sighting.employee_id == employee_id)
                   .order_by(Sighting.ts.desc()).limit(1)).first()
        d = s.exec(select(DeskSample).where(DeskSample.employee_id == employee_id, DeskSample.present == True)  # noqa: E712
                   .order_by(DeskSample.ts.desc()).limit(1)).first()
    best = None
    if r:
        best = {"ts": r.ts, "channel": r.channel, "source": "kirish kamerasi", "face_url": f"/media/{r.face_path}"}
    if d and (best is None or d.ts > best["ts"]):
        best = {"ts": d.ts, "channel": d.channel, "source": "ish joyi", "face_url": None}
    if best:
        best["ts"] = best["ts"].isoformat(timespec="minutes")
        best["camera"] = settings.get_camera(best["channel"])["name"]
    return best


def scan_all_cameras(target_ids: Optional[List[int]] = None, workers: int = 6) -> List[dict]:
    """Barcha kameralardan jonli kadr olib, yuzlarni taniydi. Topilganlarni qaytaradi."""
    def _one(ch: int):
        jpeg = capture_snapshot(ch, sub_stream=False, timeout_seconds=6.0, max_attempts=1)
        img = decode_jpeg(jpeg) if jpeg else None
        if img is None:
            return ch, None, []
        return ch, img, face_engine.analyze(img, channel=ch)

    found = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for ch, img, faces in pool.map(_one, settings.channel_ids):
            hits = [f for f in faces if f.known and (target_ids is None or f.employee_id in target_ids)]
            if hits:
                found.append({
                    "channel": ch, "camera": settings.get_camera(ch)["name"],
                    "people": [{"employee_id": f.employee_id, "name": f.name,
                                "similarity": round(f.similarity, 2)} for f in hits],
                    "image_jpeg": encode_jpeg(face_engine.annotate(img, faces), 80, max_side=1280),
                })
    return found


# =============================================================================
# CHAT: savolni aniqlash va faktlar yig'ish
# =============================================================================

_STAFF_WORDS = ("keldi", "kelgan", "kelmadi", "kelmagan", "ketdi", "ketgan", "kechik", "ishladi",
                "ishlagan", "davomat", "xodim", "effektiv", "samarador", "tanaffus", "ish stoli",
                "qayerda", "qaerda", "qani", "erta ket", "ishda", "ofisda")
_LOCATE_WORDS = ("qayerda", "qaerda", "qani", "qaysi kamerada", "ko'rinyaptimi", "topib ber")
_COUNT_WORDS = ("nechta odam", "necha kishi", "nechta kishi", "kim kirdi", "kim keldi", "kimlar", "nechta")


def match_employees(text: str) -> List[Employee]:
    t = _norm(text)
    tokens = re.findall(r"[a-zа-яё'ʻ]+", t)
    out = []
    for emp in employees_all(active_only=True).values():
        names = [n for n in (_norm(emp.first_name), _norm(emp.last_name)) if len(n) >= 3]
        if any(tok.startswith(n) for n in names for tok in tokens):
            out.append(emp)
    return out


def parse_days(text: str) -> List[str]:
    t = _norm(text)
    today = date_cls.today()
    m = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", t)
    if m:
        return [date_cls(int(m.group(1)), int(m.group(2)), int(m.group(3))).isoformat()]
    m = re.search(r"\b(\d{1,2})\.(\d{1,2})(?:\.(\d{4}))?\b", t)
    if m:
        y = int(m.group(3)) if m.group(3) else today.year
        try:
            return [date_cls(y, int(m.group(2)), int(m.group(1))).isoformat()]
        except ValueError:
            pass
    if "o'tgan hafta" in t:
        start = today - timedelta(days=today.weekday() + 7)
        return [(start + timedelta(days=i)).isoformat() for i in range(7)]
    if "hafta" in t:
        return [(today - timedelta(days=i)).isoformat() for i in range(6, -1, -1)]
    if "oy" in t.split() or "bu oy" in t:
        return [(today - timedelta(days=i)).isoformat() for i in range(29, -1, -1)]
    if "kecha" in t:
        return [(today - timedelta(days=1)).isoformat()]
    return [today.isoformat()]


@dataclass
class StaffQuery:
    kind: str                      # locate | attendance | camera_count
    employees: List[Employee]
    days: List[str]


def detect_staff_query(query: str, channel: Optional[int], has_time_range: bool) -> Optional[StaffQuery]:
    t = _norm(query)
    emps = match_employees(query)
    if emps and any(w in t for w in _LOCATE_WORDS):
        return StaffQuery("locate", emps, [date_cls.today().isoformat()])
    if channel is not None and channel in settings.attendance_channels and any(w in t for w in _COUNT_WORDS):
        return StaffQuery("camera_count", emps, parse_days(query))
    if has_time_range:
        return None
    has_staff_word = any(w in t for w in _STAFF_WORDS)
    if channel is not None and not has_staff_word:
        return None  # masalan "5-kamerada Aliyev bormi?" — jonli tahlil (yuz tanish bilan)
    if has_staff_word or emps:
        return StaffQuery("attendance", emps, parse_days(query))
    return None


def attendance_facts(sq: StaffQuery) -> dict:
    days = sq.days[-31:]
    ids = {e.id for e in sq.employees}
    per_day = []
    for d in days:
        rep = daily_attendance(d)
        emps = [r for r in rep["employees"] if not ids or r["id"] in ids]
        for r in emps:
            r.pop("desk_timeline", None)
        per_day.append({"date": d, "summary": rep["summary"], "employees": emps})
    return {"days": per_day, "focus_employees": [e.full_name for e in sq.employees],
            "late_grace_minutes": settings.LATE_GRACE_MINUTES, "now": datetime.now().isoformat(timespec="minutes")}


def _fmt_min(m: Optional[float]) -> str:
    if m is None:
        return "—"
    m = int(m)
    return f"{m // 60} soat {m % 60} daq" if m >= 60 else f"{m} daq"


def attendance_text(facts: dict) -> str:
    """AI ishlamasa ham aniq javob beradigan deterministik matn."""
    lines = []
    for day in facts["days"]:
        s = day["summary"]
        lines.append(f"**{day['date']}** — kelganlar {s['present']}/{s['total_employees']}, "
                     f"kechikkanlar {s['late']}, erta ketganlar {s['early_leave']}")
        for e in day["employees"]:
            if e["status"] == "kelmagan":
                lines.append(f"• {e['name']}: kelmagan")
                continue
            parts = [f"keldi {e['arrived'][11:16]}{' (taxminan)' if e['arrived_approx'] else ''}"]
            if e["late_minutes"]:
                parts.append(f"{e['late_minutes']} daq kechikdi")
            parts.append(f"ketdi {e['left'][11:16]}" if e["left"] else e["status"])
            parts.append(f"ofisda {_fmt_min(e['office_minutes'])}")
            if e.get("time"):
                t = e["time"]
                parts.append(", ".join(f"{presence.CATEGORIES[k].lower()} {_fmt_min(v)}" for k, v in t.items() if v))
            if e["efficiency"] is not None:
                parts.append(f"ish joyida {_fmt_min(e['desk_minutes'])} (yuz bilan tasdiqlangan {_fmt_min(e['confirmed_minutes'])}), effektivlik {e['efficiency']}%")
            lines.append(f"• {e['name']}: " + ", ".join(parts))
    return "\n".join(lines) if lines else "Ma'lumot topilmadi."
