"""
Bosqich 2–5 API'lari: ogohlantirishlar (SSE), sozlamalar, analitika, hisobotlar, issiqlik xaritasi,
kun chizig'i, PTZ, fon vazifalari (klip / video xulosa), semantik qidiruv, agent.
"""

from __future__ import annotations

import asyncio
import json
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel
from sqlmodel import select

import analytics
import nvr_isapi
from activity import recorder, render_heatmap
from alerts import alert_to_dict, bus
from config import settings
from database import ActivityMinute, Alert, Coverage, Employee, Sighting, get_session
from jobs import jobs
from rtsp_manager import record_playback_clip
from security import security_manager
from settings_store import store

router = APIRouter(prefix="/api")


def _day(d: Optional[str]) -> str:
    try:
        return date.fromisoformat(d).isoformat() if d else date.today().isoformat()
    except ValueError:
        raise HTTPException(status_code=400, detail="Sana formati: YYYY-MM-DD")


def _channel(ch: int) -> int:
    if ch not in settings.channel_ids:
        raise HTTPException(status_code=404, detail="Bunday kamera yo'q")
    return ch


# =============================================================================
# REAL-VAQT HODISALAR (SSE)
# =============================================================================

@router.get("/events/stream")
async def events_stream(request: Request):
    q = bus.subscribe()

    async def gen():
        try:
            yield "retry: 3000\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    ev = await asyncio.wait_for(q.get(), timeout=15)
                    yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
        finally:
            bus.unsubscribe(q)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# =============================================================================
# OGOHLANTIRISHLAR
# =============================================================================

@router.get("/alerts")
def list_alerts(date_from: Optional[str] = None, date_to: Optional[str] = None, kind: Optional[str] = None,
                unacked: bool = False, limit: int = 200, after_id: Optional[int] = None):
    d0, d1 = _day(date_from or (date.today() - timedelta(days=6)).isoformat()), _day(date_to)
    with get_session() as s:
        q = select(Alert).where(Alert.date >= d0, Alert.date <= d1)
        if after_id is not None:  # Telegram bot yangi hodisalarni shu bilan oladi
            q = q.where(Alert.id > after_id)
        if kind:
            q = q.where(Alert.kind.in_(kind.split(",")))
        if unacked:
            q = q.where(Alert.acknowledged == False)  # noqa: E712
        rows = s.exec(q.order_by(Alert.ts.desc()).limit(min(500, limit))).all()
        unread = len(s.exec(select(Alert.id).where(Alert.acknowledged == False,  # noqa: E712
                                                   Alert.kind.in_(["unknown_face", "after_hours", "camera_offline", "agent"]))).all())
    return {"items": [alert_to_dict(a) for a in rows], "unread": unread}


@router.post("/alerts/{alert_id}/ack")
def ack_alert(alert_id: int):
    with get_session() as s:
        a = s.get(Alert, alert_id)
        if not a:
            raise HTTPException(status_code=404, detail="Topilmadi")
        a.acknowledged = True
        s.add(a)
        s.commit()
    return {"status": "ok"}


@router.post("/alerts/ack-all")
def ack_all():
    with get_session() as s:
        for a in s.exec(select(Alert).where(Alert.acknowledged == False)).all():  # noqa: E712
            a.acknowledged = True
            s.add(a)
        s.commit()
    return {"status": "ok"}


@router.post("/alerts/test")
def test_alert():
    a = bus.create("test", "Sinov ogohlantirishi", "Tizim ishlayapti — bu sinov xabari.", severity="warning")
    return alert_to_dict(a)


# =============================================================================
# SOZLAMALAR
# =============================================================================

@router.get("/settings")
def get_settings():
    from telegram_notifier import configured
    return {**store.public(), "telegram_configured": configured()}


@router.put("/settings")
def put_settings(body: Dict[str, Any]):
    changed = store.update(body)
    if "security_cameras" in changed:
        security_manager.start()
    if {"daily_summary_time", "indexer_interval_min"} & changed.keys():
        import scheduler
        scheduler.apply_schedule()
    return get_settings()


class TelegramTestIn(BaseModel):
    token: Optional[str] = None
    chat_id: Optional[str] = None


@router.post("/settings/telegram-test")
def telegram_test(body: TelegramTestIn):
    from telegram_notifier import send_message
    try:
        send_message("✅ CCTV AI: Telegram ulanishi ishlayapti.", chat_id=body.chat_id or None, token=body.token or None)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Telegram: {e}")
    return {"status": "ok"}


@router.get("/system")
def system_info():
    import scheduler
    return {"security": security_manager.status(), "scheduler": scheduler.jobs_info()}


# =============================================================================
# ANALITIKA VA HISOBOTLAR
# =============================================================================

@router.get("/analytics")
def get_analytics(date_from: str, date_to: str):
    return analytics.build(_day(date_from), _day(date_to))


@router.get("/reports/attendance.{fmt}")
def report_file(fmt: str, date_from: str, date_to: str):
    from reports import build_excel, build_pdf
    d0, d1 = _day(date_from), _day(date_to)
    if fmt == "xlsx":
        return Response(build_excel(d0, d1), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={"Content-Disposition": f'attachment; filename="davomat_{d0}_{d1}.xlsx"'})
    if fmt == "pdf":
        return Response(build_pdf(d0, d1), media_type="application/pdf",
                        headers={"Content-Disposition": f'attachment; filename="davomat_{d0}_{d1}.pdf"'})
    raise HTTPException(status_code=404, detail="Format: xlsx yoki pdf")


@router.post("/reports/daily-summary")
def run_daily_summary(day: Optional[str] = None, notify: bool = False):
    from agent import daily_summary
    return alert_to_dict(daily_summary(_day(day), notify=notify))


@router.post("/reports/weekly")
def run_weekly(send: bool = True):
    from agent import weekly_report
    return weekly_report(send=send)


@router.get("/heatmap/{channel}")
def heatmap(channel: int, day: Optional[str] = None):
    img = render_heatmap(_channel(channel), _day(day))
    if img is None:
        raise HTTPException(status_code=404, detail="Bu kamera uchun hali faollik ma'lumoti yo'q")
    return Response(img, media_type="image/jpeg", headers={"Cache-Control": "no-cache"})


@router.get("/heatmap")
def heatmap_channels(day: Optional[str] = None):
    from activity import HEAT_DIR
    d = HEAT_DIR / _day(day)
    chs = sorted(int(p.stem[2:4]) for p in d.glob("ch??.npy")) if d.exists() else []
    live = sorted({ch for ch, dd in recorder._heat if dd == _day(day)})
    return {"channels": sorted(set(chs) | set(live))}


# =============================================================================
# KUN CHIZIG'I (NVR yozuvlari + faollik + hodisalar)
# =============================================================================

@router.get("/timeline")
def timeline(channel: int, day: Optional[str] = None):
    ch, d = _channel(channel), _day(day)
    recordings = nvr_isapi.search_recordings(ch, d)
    with get_session() as s:
        acts = s.exec(select(ActivityMinute).where(ActivityMinute.channel == ch, ActivityMinute.date == d)).all()
        sights = s.exec(select(Sighting).where(Sighting.channel == ch, Sighting.date == d)).all()
        alerts = s.exec(select(Alert).where(Alert.channel == ch, Alert.date == d)).all()
        cov = s.exec(select(Coverage).where(Coverage.channel == ch, Coverage.date == d)).all()
        names = {e.id: e.full_name for e in s.exec(select(Employee)).all()}
    return {
        "channel": ch, "date": d, "camera": settings.get_camera(ch)["name"],
        "recordings": recordings, "recordings_available": recordings is not None,
        "activity": [{"minute": a.minute, "motion": a.motion, "people": a.people} for a in acts],
        "sightings": [{"ts": r.ts.isoformat(timespec="seconds"), "name": names.get(r.employee_id, "Notanish") if r.employee_id else "Notanish",
                       "known": r.employee_id is not None, "face_url": f"/media/{r.face_path}"} for r in sights],
        "alerts": [alert_to_dict(a) for a in alerts],
        "coverage": [{"start": c.start_ts.isoformat(timespec="seconds"), "end": c.end_ts.isoformat(timespec="seconds")} for c in cov],
    }


# =============================================================================
# PTZ
# =============================================================================

class PtzMoveIn(BaseModel):
    pan: int = 0
    tilt: int = 0
    zoom: int = 0


@router.get("/ptz/{channel}")
def ptz_caps(channel: int):
    ch = _channel(channel)
    ok = nvr_isapi.ptz_supported(ch)
    return {"channel": ch, "supported": ok, "presets": nvr_isapi.ptz_presets(ch) if ok else []}


@router.post("/ptz/{channel}/move")
def ptz_move(channel: int, body: PtzMoveIn):
    if not nvr_isapi.ptz_move(_channel(channel), body.pan, body.tilt, body.zoom):
        raise HTTPException(status_code=502, detail="PTZ buyrug'i bajarilmadi (kamera PTZ emas yoki NVR javob bermadi)")
    return {"status": "ok"}


@router.post("/ptz/{channel}/stop")
def ptz_stop(channel: int):
    nvr_isapi.ptz_stop(_channel(channel))
    return {"status": "ok"}


@router.post("/ptz/{channel}/preset/{preset_id}")
def ptz_goto(channel: int, preset_id: int):
    if not nvr_isapi.ptz_goto(_channel(channel), preset_id):
        raise HTTPException(status_code=502, detail="Presetga o'tib bo'lmadi")
    return {"status": "ok"}


# =============================================================================
# FON VAZIFALARI: klip va video xulosa
# =============================================================================

class ClipJobIn(BaseModel):
    channel: int
    start: str
    seconds: int = 30


@router.post("/jobs/clip")
def job_clip(body: ClipJobIn):
    ch = _channel(body.channel)
    try:
        start = datetime.fromisoformat(body.start)
    except ValueError:
        raise HTTPException(status_code=400, detail="Vaqt formati noto'g'ri")
    secs = max(3, min(30, body.seconds))
    end = min(start + timedelta(seconds=secs), datetime.now())
    if end <= start:
        raise HTTPException(status_code=400, detail="Kelajakdagi vaqt")

    def run(job):
        job.update(0.05, "NVR arxividan qidirilmoqda…")
        name = record_playback_clip(ch, start, end, max_seconds=secs)
        if not name:
            raise RuntimeError("NVR arxividan klip olinmadi (yozuv yo'q yoki kameralar ulanmagan)")
        job.update(1.0, f"Tayyor · {int((end - start).total_seconds())} s")
        return {"url": f"/clips/{name}", "channel": ch, "start": start.isoformat(timespec="seconds")}

    job = jobs.submit("clip", f"{settings.get_camera(ch)['name']} · {start:%H:%M:%S}", run)
    return job.to_dict()


class SummaryJobIn(BaseModel):
    day: Optional[str] = None
    channel: Optional[int] = None


@router.post("/jobs/summary")
def job_summary(body: SummaryJobIn):
    from video_summary import build_summary
    d = _day(body.day)
    ch = _channel(body.channel) if body.channel else None
    title = f"Video xulosa · {d}" + (f" · CH-{ch:02d}" if ch else " · barcha kameralar")
    return jobs.submit("summary", title, lambda job: build_summary(job, d, ch)).to_dict()


@router.get("/jobs")
def list_jobs():
    return jobs.list()


@router.get("/jobs/{job_id}")
def get_job(job_id: str):
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Vazifa topilmadi")
    return job.to_dict()


# =============================================================================
# SEMANTIK QIDIRUV VA AGENT
# =============================================================================

@router.get("/search")
def semantic_search(q: str, days: int = 7, channel: Optional[int] = None):
    import indexer
    day_list = [(date.today() - timedelta(days=i)).isoformat() for i in range(max(1, min(31, days)))]
    answer, hits = indexer.search(q, day_list, channel)
    return {"answer": answer, "results": hits}


@router.post("/index/run")
def run_index():
    import indexer
    return {"written": indexer.index_once()}


@router.get("/index/stats")
def index_stats():
    from database import FrameIndex
    from sqlmodel import func
    with get_session() as s:
        total = s.exec(select(func.count()).select_from(FrameIndex)).one()
        last = s.exec(select(FrameIndex.ts).order_by(FrameIndex.ts.desc()).limit(1)).first()
    return {"frames": total, "last": last.isoformat(timespec="minutes") if last else None}


class RoomIn(BaseModel):
    id: Optional[int] = None
    name: str
    kind: str = "work"
    channels: List[int] = []
    neighbors: List[int] = []


class RoomsIn(BaseModel):
    rooms: List[RoomIn]


def _rooms_out() -> dict:
    import presence
    return {"rooms": [{"id": r.id, "name": r.name, "kind": r.kind, "channels": r.channels, "neighbors": r.neighbors}
                      for r in sorted(presence.load_rooms().values(), key=lambda r: r.id)],
            "kinds": presence.KINDS}


@router.get("/rooms")
def get_rooms():
    return _rooms_out()


@router.put("/rooms")
def save_rooms(body: RoomsIn):
    """Xaritani to'liq almashtiradi. Tutashlik ikki tomonlama saqlanadi."""
    import presence
    from database import Employee, Room
    for r in body.rooms:
        if not r.name.strip() or r.kind not in presence.KINDS:
            raise HTTPException(status_code=400, detail=f"Xona nomi yoki turi noto'g'ri: {r.name!r}")
        if any(ch not in settings.channel_ids for ch in r.channels):
            raise HTTPException(status_code=400, detail=f"{r.name}: bunday kamera yo'q")
    with get_session() as s:
        existing = {r.id: r for r in s.exec(select(Room)).all()}
        keep = {r.id for r in body.rooms if r.id in existing}
        for rid, row in existing.items():
            if rid not in keep:
                s.delete(row)
                for e in s.exec(select(Employee).where(Employee.room_id == rid)).all():
                    e.room_id = None
                    s.add(e)
        rows = []
        for r in body.rooms:
            row = existing.get(r.id) or Room(name="")
            row.name, row.kind, row.channels = r.name.strip(), r.kind, ",".join(map(str, sorted(set(r.channels))))
            s.add(row)
            rows.append((row, r))
        s.flush()
        valid = {row.id for row, _ in rows}
        links = {row.id: {n for n in r.neighbors if n in valid and n != row.id} for row, r in rows}
        for rid, ns in list(links.items()):
            for n in ns:
                links[n].add(rid)
        for row, _ in rows:
            row.neighbors = ",".join(map(str, sorted(links[row.id])))
            s.add(row)
        s.commit()
    return _rooms_out()


class AwayIn(BaseModel):
    employee_id: int
    date: Optional[str] = None
    start: str
    end: str
    reason: str = ""


@router.post("/presence/away")
def add_away(body: AwayIn):
    from database import AwayPeriod
    try:
        start, end = (settings.parse_hhmm(v).strftime("%H:%M") for v in (body.start, body.end))
    except Exception:
        raise HTTPException(status_code=400, detail="Vaqt formati: HH:MM")
    if end <= start:
        raise HTTPException(status_code=400, detail="Tugash vaqti boshlanishdan keyin bo'lishi kerak")
    row = AwayPeriod(employee_id=body.employee_id, date=_day(body.date), start=start, end=end, reason=body.reason.strip()[:200])
    with get_session() as s:
        s.add(row)
        s.commit()
        s.refresh(row)
    return {"id": row.id}


@router.delete("/presence/away/{away_id}")
def delete_away(away_id: int):
    from database import AwayPeriod
    with get_session() as s:
        row = s.get(AwayPeriod, away_id)
        if row:
            s.delete(row)
            s.commit()
    return {"status": "ok"}


@router.get("/bot/attendance")
def bot_attendance(date: Optional[str] = None):
    """Telegram bot uchun tayyor davomat matni."""
    import staff_service
    day = _day(date)
    facts = staff_service.daily_attendance(day)
    return {"date": day, "summary": facts.get("summary"), "text": staff_service.attendance_text({"days": [facts]})}


@router.get("/bot/last-alert-id")
def bot_last_alert_id():
    with get_session() as s:
        last = s.exec(select(Alert.id).order_by(Alert.id.desc()).limit(1)).first()
    return {"id": last or 0}


@router.post("/agent/run")
def run_agent():
    from agent import run_agent_checks
    return {"messages": run_agent_checks()}

