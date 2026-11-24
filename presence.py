"""
Xodim qayerda: ofis xaritasi (xonalar) va "oxirgi ma'lum joy" qoidasi.

Joy faqat dalil bo'lganda o'zgaradi: yuz tanildi, kirish/chiqish o'tishi, ish joyida odam bor, xona bo'shab qoldi.
Dalil bo'lmasa xodim oxirgi ko'ringan xonasida qoladi (kamera ko'rmaydigan xona ham), lekin xona turiga qarab
chegaralar bor: yo'lakdan o'z xonasiga o'tadi, hovlidan uzoq qolsa "tashqarida", kamerali xona bo'shasa "noma'lum".

Har daqiqada bitta PresenceSample yoziladi: joy + ishonch (seen — kamera tasdiqladi, inferred — taxmin, unknown).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Set, Tuple

from sqlmodel import select

from config import settings
from database import AwayPeriod, Employee, PresenceSample, Room, get_session

OUT, AWAY, UNKNOWN = "out", "away", "unknown"
KINDS = {"work": "Ish xonasi", "meeting": "Majlis zali", "rest": "Dam olish", "corridor": "Yo'lak",
         "yard": "Hovli / ko'cha", "blind": "Kamerasiz joy"}
CORRIDOR_SECONDS = 120   # yo'lakda shuncha ko'rinmasa — yo'lakdagi xonaga (o'z xonasiga) kirgan


def _ints(raw: str) -> List[int]:
    return [int(x) for x in (raw or "").split(",") if x.strip().isdigit()]


@dataclass
class RoomInfo:
    id: int
    name: str
    kind: str
    channels: List[int]
    neighbors: List[int]


def load_rooms() -> Dict[int, RoomInfo]:
    with get_session() as s:
        rows = s.exec(select(Room)).all()
    return {r.id: RoomInfo(r.id, r.name, r.kind, _ints(r.channels), _ints(r.neighbors)) for r in rows}


def room_of_channel(rooms: Dict[int, RoomInfo]) -> Dict[int, int]:
    return {ch: r.id for r in rooms.values() for ch in r.channels}


def place_name(place: str, rooms: Dict[int, RoomInfo]) -> Tuple[str, str]:
    """(nomi, turi) — UI va hisobot uchun."""
    if place == OUT:
        return "Ofisdan tashqarida", "out"
    if place == AWAY:
        return "Tashqarida ishda", "away"
    if place.isdigit() and int(place) in rooms:
        r = rooms[int(place)]
        return r.name, r.kind
    return "Noma'lum", "unknown"


@dataclass
class Evidence:
    faces: Dict[int, Tuple[int, float]] = field(default_factory=dict)     # xodim -> (xona, o'xshashlik), eng kuchlisi
    occupied: Dict[int, Tuple[int, bool]] = field(default_factory=dict)   # xodim -> (xona, ish joyida odam bormi)
    live_people: Dict[int, int] = field(default_factory=dict)             # tekshirilgan xona -> harakatdagi odamlar
    failed_rooms: Set[int] = field(default_factory=set)                   # kamerasi kadr bermagan xonalar
    passages: Dict[int, Tuple[str, float]] = field(default_factory=dict)  # xodim -> (IN/OUT, vaqt) shu davrda
    unknown_entrance: List[float] = field(default_factory=list)          # kirishda tanilmagan odam vaqtlari
    away: Set[int] = field(default_factory=set)                          # "tashqarida ishda" belgilanganlar
    nvr_online: bool = True


@dataclass
class State:
    place: str
    conf: str
    last_seen: float
    active_at: float = 0.0       # xonada oxirgi marta odam/harakat bo'lgan vaqt
    blind_alerted: bool = False


@dataclass
class Limits:
    yard_seconds: float
    blind_seconds: float
    room_grace_seconds: float


class PresenceTracker:
    def __init__(self) -> None:
        self.day: Optional[str] = None
        self.state: Dict[int, State] = {}

    def reset(self, day: str, restore: bool = True) -> None:
        self.day, self.state = day, {}
        if not restore:
            return
        with get_session() as s:
            rows = s.exec(select(PresenceSample).where(PresenceSample.date == day).order_by(PresenceSample.ts)).all()
        for r in rows:  # server qayta ishga tushsa, xodimlar oxirgi joyidan davom etadi
            t = r.ts.timestamp()
            st = self.state.get(r.employee_id)
            seen = t if r.conf == "seen" else (st.last_seen if st else t)
            self.state[r.employee_id] = State(r.place, r.conf, seen, t)

    def current(self, employee_id: int) -> Optional[State]:
        return self.state.get(employee_id) if self.day == datetime.now().strftime("%Y-%m-%d") else None

    def step(self, now: float, ev: Evidence, rooms: Dict[int, RoomInfo], home: Dict[int, Optional[int]],
             limits: Limits) -> Tuple[Dict[int, Tuple[str, str]], List[int]]:
        """Bitta qadam. Qaytaradi: ({xodim: (joy, ishonch)}, [uzoq vaqt kamerasiz joyda qolgan xodimlar])."""
        out: Dict[int, Tuple[str, str]] = {}
        blind_alerts: List[int] = []
        for eid, home_room in home.items():
            st = self.state.get(eid)
            passage = ev.passages.get(eid)
            face = ev.faces.get(eid)
            if face and passage and rooms.get(face[0]) and rooms[face[0]].kind == "yard":
                face = None  # kirish kamerasidagi o'tish ko'cha kamerasidagi kadrdan aniqroq
            if eid in ev.away:
                st = State(AWAY, "seen", now, now)
            elif face:
                st = State(str(face[0]), "seen", now, now)
            elif passage:
                direction, t = passage
                if direction == "OUT":
                    st = State(OUT, "seen", t, t)
                else:  # kirdi: boshqa kamera ko'rmaguncha o'z xonasida
                    st = State(str(home_room) if home_room in rooms else UNKNOWN, "inferred", t, t)
            elif eid in ev.occupied and ev.occupied[eid][1]:
                room = ev.occupied[eid][0]
                st = State(str(room), "inferred", st.last_seen if st else now, now)
            elif st is None:
                continue  # hali kelmagan
            else:
                self._no_evidence(eid, st, now, ev, rooms, home_room, limits, blind_alerts)
            self.state[eid] = st
            out[eid] = (st.place, st.conf)
        return out, blind_alerts

    @staticmethod
    def _no_evidence(eid: int, st: State, now: float, ev: Evidence, rooms: Dict[int, RoomInfo],
                     home_room: Optional[int], limits: Limits, blind_alerts: List[int]) -> None:
        if st.place in (OUT, AWAY):
            st.conf = "inferred" if st.place == OUT else st.conf
            return
        if st.place == UNKNOWN:
            if any(t > st.last_seen for t in ev.unknown_entrance):
                st.place, st.conf = OUT, "inferred"  # yo'qolgan paytda kirishdan tanilmagan odam chiqdi
            return
        room = rooms.get(int(st.place)) if st.place.isdigit() else None
        if room is None:
            st.place, st.conf = UNKNOWN, "unknown"
            return
        if not ev.nvr_online or (room.id in ev.failed_rooms):
            st.conf = "unknown"  # kamera ko'rmayapti — na bor, na yo'q deb bo'lmaydi
            return
        st.conf = "inferred"
        quiet = now - max(st.last_seen, st.active_at)
        if room.kind == "corridor":
            if quiet > CORRIDOR_SECONDS:
                home = rooms.get(home_room) if home_room else None
                linked = home is not None and (room.id in home.neighbors or home.id in room.neighbors
                                               or not (home.neighbors or room.neighbors))
                st.place, st.conf = (str(home.id), "inferred") if linked else (UNKNOWN, "unknown")
            return
        if room.kind == "yard":
            if quiet > limits.yard_seconds:
                st.place = OUT
            return
        if room.kind == "blind":
            if quiet > limits.blind_seconds and not st.blind_alerted:
                st.blind_alerted = True
                blind_alerts.append(eid)
            return
        if room.channels and room.id in ev.live_people:
            busy = ev.occupied[eid][1] if eid in ev.occupied else ev.live_people[room.id] > 0
            if busy:
                st.active_at = now
            elif quiet > limits.room_grace_seconds:
                st.place, st.conf = UNKNOWN, "unknown"  # xonadan chiqdi, qayerga — kamera ko'rmadi
        # kamerasi yo'q xona: boshqa dalil bo'lmaguncha shu yerda


tracker = PresenceTracker()


# ----------------------------------------------------------------------------- hisobot
CATEGORIES = {"ish": "Ish xonasida", "majlis": "Majlisda", "safar": "Tashqarida ishda", "tushlik": "Tushlik",
              "tanaffus": "Tanaffus", "dam": "Dam olish xonasi", "tashqarida": "Ofisdan tashqarida",
              "nomalum": "Ma'lum emas", "qoshimcha": "Qo'shimcha ish"}
WORK_CATEGORIES = ("ish", "majlis", "safar", "qoshimcha")


def _in_window(t: datetime, start: str, end: str) -> bool:
    return settings.parse_hhmm(start) <= t.time() < settings.parse_hhmm(end)


def breakdown(samples: List[PresenceSample], rooms: Dict[int, RoomInfo], work_end: datetime,
              lunch: Tuple[str, str], yard_minutes: float) -> dict:
    """Kunlik vaqt taqsimoti (daqiqa). Ish tugagandan keyingi taxminiy yozuvlar hisobga olinmaydi."""
    rows = [r for r in sorted(samples, key=lambda r: r.ts) if r.conf == "seen" or r.ts <= work_end]
    totals = {k: 0.0 for k in CATEGORIES}
    places: Dict[str, dict] = {}
    yard_run: List[PresenceSample] = []

    def flush_yard() -> None:
        minutes = sum(r.interval_seconds for r in yard_run) / 60
        for r in yard_run:
            totals["tushlik" if _in_window(r.ts, *lunch) else "tanaffus" if minutes <= yard_minutes else "tashqarida"] \
                += r.interval_seconds / 60
        yard_run.clear()

    for r in rows:
        name, kind = place_name(r.place, rooms)
        minutes = r.interval_seconds / 60
        p = places.setdefault(name, {"name": name, "kind": kind, "minutes": 0.0, "seen_minutes": 0.0})
        p["minutes"] += minutes
        p["seen_minutes"] += minutes if r.conf == "seen" else 0
        if kind == "yard":
            yard_run.append(r)
            continue
        flush_yard()
        lunch_time = _in_window(r.ts, *lunch)
        if r.conf == "unknown" or kind == "unknown":
            cat = "nomalum"
        elif kind == "away":
            cat = "safar"
        elif kind == "out":
            cat = "tushlik" if lunch_time else "tashqarida"
        elif kind == "rest":
            cat = "tushlik" if lunch_time else "dam"
        elif kind == "blind":
            cat = "tanaffus"
        elif r.ts > work_end:
            cat = "qoshimcha"
        else:
            cat = "majlis" if kind == "meeting" else "ish"
        totals[cat] += minutes
    flush_yard()
    seen = [r for r in rows if r.conf == "seen" and r.place != OUT]
    return {
        "time": {k: round(v) for k, v in totals.items()},
        "places": sorted(({**p, "minutes": round(p["minutes"]), "seen_minutes": round(p["seen_minutes"])}
                          for p in places.values()), key=lambda p: -p["minutes"]),
        "first_seen": seen[0].ts if seen else None,
        "last_seen": seen[-1].ts if seen else None,
    }


def away_now(day: str, now: datetime) -> Set[int]:
    hhmm = now.strftime("%H:%M")
    with get_session() as s:
        rows = s.exec(select(AwayPeriod).where(AwayPeriod.date == day)).all()
    return {r.employee_id for r in rows if r.start <= hhmm < r.end}


def homes() -> Dict[int, Optional[int]]:
    with get_session() as s:
        return {e.id: e.room_id for e in s.exec(select(Employee).where(Employee.active == True)).all()}  # noqa: E712


def seed_rooms() -> None:
    """Birinchi ishga tushishda har kameradan bitta xona; admin keyin nomi, turi va qo'shnilarini to'g'rilaydi."""
    with get_session() as s:
        if s.exec(select(Room)).first() is not None:
            return
        for cam in settings.list_cameras():
            ch = cam["channel"]
            s.add(Room(name=cam["name"], kind="yard" if ch in settings.street_channels else "work", channels=str(ch)))
        s.commit()
        by_ch = {int(r.channels): r.id for r in s.exec(select(Room)).all()}
        for e in s.exec(select(Employee)).all():
            if e.room_id is None and e.desk_channel in by_ch:
                e.room_id = by_ch[e.desk_channel]
                s.add(e)
        s.commit()


def samples_for(day: str) -> Dict[int, List[PresenceSample]]:
    with get_session() as s:
        rows = s.exec(select(PresenceSample).where(PresenceSample.date == day)).all()
    out: Dict[int, List[PresenceSample]] = {}
    for r in rows:
        out.setdefault(r.employee_id, []).append(r)
    return out
