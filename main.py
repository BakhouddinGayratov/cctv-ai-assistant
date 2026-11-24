"""
CCTV AI Assistant — FastAPI Server.

Sahifalar:  /  (dashboard + chat) · /admin/employees (xodimlar) · /attendance (davomat)
Asosiy API: /api/chat · /api/stream · /api/snapshot · /api/archive/* ·
            /api/employees/* · /api/faces/* · /api/sightings/* · /api/attendance · /api/workers/*
"""

from __future__ import annotations

import base64
import re
import shutil
from contextlib import asynccontextmanager
import threading
import time
import uuid
from datetime import date as date_cls, datetime, timedelta
from typing import Dict, List, Optional, Tuple

import numpy as np
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlmodel import select

from config import settings
from database import DeskSample, Employee, FaceSample, Sighting, get_session, init_db
from face_engine import (
    FaceResult, bytes_to_emb, crop_face, decode_jpeg, emb_to_bytes, encode_jpeg,
    ensure_models_async, face_engine,
)
from rtsp_manager import (
    CLIPS_DIR,
    capture_live_burst,
    capture_playback_frames,
    capture_snapshot,
    generate_mjpeg,
    generate_mosaic,
    nvr_online,
    record_live_clip,
    record_playback_clip,
    sample_playback_range,
    stream_guard,
)
from ai_service import (
    _extract_time_range, analyze_live, analyze_long_range, analyze_playback, chat_memory,
    general_reply, model_status, parse_intent, staff_answer,
)
import scheduler
import staff_service
from api_ext import router as ext_router
from jobs import jobs
from security import security_manager
from auth import AuthMiddleware, router as auth_router
from presence import seed_rooms
from workers import assigned_workplace_channels, worker_manager


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    seed_rooms()
    ensure_models_async()
    if face_engine.available:
        face_engine.reload_gallery()
    worker_manager.start()
    security_manager.start()
    scheduler.start()
    yield
    worker_manager.stop()
    security_manager.stop()
    from activity import recorder
    recorder.flush_heat()


app = FastAPI(title="CCTV AI Assistant", version="3.0.0", lifespan=lifespan)
app.add_middleware(AuthMiddleware)
app.include_router(auth_router)
app.include_router(ext_router)  # SPA catch-all'dan oldin bo'lishi shart

FRONTEND_DIST = settings.BASE_DIR / "frontend" / "dist"

app.mount("/clips", StaticFiles(directory=CLIPS_DIR), name="clips")
app.mount("/media", StaticFiles(directory=settings.DATA_DIR), name="media")
if (FRONTEND_DIST / "assets").exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

FACES_DIR = settings.DATA_DIR / "faces"


def _b64(b: bytes) -> str:
    return base64.b64encode(b).decode("ascii")


# =============================================================================
# 1. KAMERALAR VA KONFIGURATSIYA
# =============================================================================

def _cameras_with_roles() -> List[dict]:
    att, desk = set(settings.attendance_channels), set(assigned_workplace_channels())
    out = []
    for cam in settings.list_cameras():
        roles = (["entrance"] if cam["channel"] in att else []) + (["desk"] if cam["channel"] in desk else [])
        out.append({**cam, "roles": roles})
    return out


@app.get("/api/config")
def app_config():
    return {
        "nvr_ip": settings.NVR_IP,
        "channels": len(settings.channel_ids),
        "cameras": _cameras_with_roles(),
        "attendance_channels": settings.attendance_channels,
        "desk_channels": assigned_workplace_channels() or settings.desk_channels,
        "monitor_window": f"{settings.MONITOR_START}–{settings.MONITOR_END}",
        "default_work_start": settings.DEFAULT_WORK_START,
        "default_work_end": settings.DEFAULT_WORK_END,
        "version": app.version,
    }


@app.get("/api/cameras")
def list_cameras():
    return _cameras_with_roles()


@app.get("/api/stream/status")
def stream_status():
    return {"active_channel": stream_guard.active_channel(), "slots": stream_guard.active()}


@app.get("/api/model/status")
def model_status_endpoint():
    return model_status.snapshot()


@app.post("/api/stream/stop")
def stop_stream(prefix: str = "main"):
    """prefix='main' — asosiy pleer, 'grid' — setka, '' — hammasi."""
    stream_guard.stop(prefix)
    return {"status": "stopped"}


@app.get("/api/mosaic")
def mosaic(channels: str, cols: int = 2, faces: bool = False, fps: float = 5.0):
    """Ko'p kamerani bitta MJPEG setkada uzatadi (brauzerning 6 ulanish chegarasi uchun)."""
    chs = [int(c) for c in channels.split(",") if c.strip().isdigit() and int(c) in settings.channel_ids][:16]
    if not chs:
        raise HTTPException(status_code=400, detail="Kamera ro'yxati bo'sh")
    return StreamingResponse(generate_mosaic(chs, max(1, min(4, cols)), faces=faces, fps=max(1.0, min(8.0, fps))),
                             media_type="multipart/x-mixed-replace; boundary=frame")


@app.get("/api/stream/{channel}")
def stream_camera(channel: int, slot: str = "main", faces: bool = False, fps: float = 14.0):
    if channel not in settings.channel_ids:
        raise HTTPException(status_code=404, detail="Bunday kamera yo'q")
    if not (slot == "main" or (slot.startswith("grid-") and slot[5:].isdigit())):
        raise HTTPException(status_code=400, detail="Noto'g'ri slot")
    return StreamingResponse(generate_mjpeg(channel, slot=slot, faces=faces, fps=max(2.0, min(15.0, fps))),
                             media_type="multipart/x-mixed-replace; boundary=frame")


@app.get("/api/snapshot/{channel}")
def snapshot(channel: int, hq: bool = False):
    if channel not in settings.channel_ids:
        raise HTTPException(status_code=404, detail="Bunday kamera yo'q")
    frame = capture_snapshot(channel, sub_stream=not hq)
    if frame is None:
        raise HTTPException(status_code=502, detail=f"Kamera #{channel:02d} oqimidan kadr olib bo'lmadi")
    return Response(content=frame, media_type="image/jpeg")


# =============================================================================
# 3. NVR ARXIV
# =============================================================================

def _parse_range(start_iso: str, end_iso: str) -> Tuple[datetime, datetime]:
    try:
        start, end = datetime.fromisoformat(start_iso), datetime.fromisoformat(end_iso)
    except ValueError:
        raise HTTPException(status_code=400, detail="Vaqt formati noto'g'ri (YYYY-MM-DDTHH:MM:SS)")
    if end <= start or end > datetime.now():
        raise HTTPException(status_code=400, detail="Vaqt oralig'i noto'g'ri")
    return start, end


@app.post("/api/archive/clip")
def archive_clip(channel: int, start_iso: str, end_iso: str, max_seconds: int = 30):
    if channel not in settings.channel_ids:
        raise HTTPException(status_code=404, detail="Bunday kamera yo'q")
    start, end = _parse_range(start_iso, end_iso)
    secs = min(30, max(3, max_seconds))
    if (end - start).total_seconds() > secs:
        end = start + timedelta(seconds=secs)
    fname = record_playback_clip(channel, start, end, max_seconds=secs)
    if not fname:
        raise HTTPException(status_code=502, detail="NVR arxividan klip olinmadi (ushbu vaqtda yozuv yo'q yoki NVR band)")
    return {"url": f"/clips/{fname}", "camera_name": settings.get_camera(channel)["name"], "channel": channel,
            "start": start.isoformat(), "end": end.isoformat(), "seconds": int((end - start).total_seconds())}


@app.get("/api/archive/quick-snapshots")
def archive_quick_snapshots(channel: int, start_iso: str, end_iso: str, count: int = 3):
    if channel not in settings.channel_ids:
        raise HTTPException(status_code=404, detail="Bunday kamera yo'q")
    start, end = _parse_range(start_iso, end_iso)
    frames = capture_playback_frames(channel, start, end, frames_wanted=max(1, min(5, count)))
    return {"channel": channel, "camera_name": settings.get_camera(channel)["name"],
            "frames_b64": [_b64(f) for f in frames], "found": len(frames)}


# =============================================================================
# 4. XODIMLAR
# =============================================================================

class EmployeeIn(BaseModel):
    first_name: str
    last_name: str = ""
    position: str = ""
    phone: str = ""
    work_start: str = settings.DEFAULT_WORK_START
    work_end: str = settings.DEFAULT_WORK_END
    active: bool = True
    desk_channel: Optional[int] = None
    room_id: Optional[int] = None


class DeskIn(BaseModel):
    desk_channel: Optional[int] = None
    zone: Optional[List[float]] = None


def _validate_hhmm(v: str) -> str:
    try:
        return settings.parse_hhmm(v).strftime("%H:%M")
    except Exception:
        raise HTTPException(status_code=400, detail=f"Vaqt formati noto'g'ri: {v} (HH:MM)")


def _employee_out(e: Employee, samples: List[FaceSample]) -> dict:
    return {
        "id": e.id, "first_name": e.first_name, "last_name": e.last_name, "full_name": e.full_name,
        "position": e.position, "phone": e.phone, "work_start": e.work_start, "work_end": e.work_end,
        "active": e.active, "desk_channel": e.desk_channel, "room_id": e.room_id,
        "desk_zone": [float(v) for v in e.desk_zone.split(",")] if e.desk_zone else None,
        "samples": len(samples),
        "avatar": f"/media/{samples[-1].image_path}" if samples else None,
    }


def _get_employee(s, employee_id: int) -> Employee:
    emp = s.get(Employee, employee_id)
    if not emp:
        raise HTTPException(status_code=404, detail="Xodim topilmadi")
    return emp


@app.get("/api/employees")
def list_employees():
    with get_session() as s:
        emps = s.exec(select(Employee).order_by(Employee.first_name)).all()
        samples = s.exec(select(FaceSample)).all()
    by_emp: Dict[int, List[FaceSample]] = {}
    for fs in samples:
        by_emp.setdefault(fs.employee_id, []).append(fs)
    return [_employee_out(e, by_emp.get(e.id, [])) for e in emps]


@app.post("/api/employees")
def create_employee(body: EmployeeIn):
    if not body.first_name.strip():
        raise HTTPException(status_code=400, detail="Ism kiritilishi shart")
    data = body.model_dump()
    data["work_start"], data["work_end"] = _validate_hhmm(body.work_start), _validate_hhmm(body.work_end)
    emp = Employee(**data)
    with get_session() as s:
        s.add(emp)
        s.commit()
        s.refresh(emp)
    return _employee_out(emp, [])


@app.put("/api/employees/{employee_id}")
def update_employee(employee_id: int, body: EmployeeIn):
    with get_session() as s:
        emp = _get_employee(s, employee_id)
        for k, v in body.model_dump().items():
            setattr(emp, k, v)
        emp.work_start, emp.work_end = _validate_hhmm(body.work_start), _validate_hhmm(body.work_end)
        s.add(emp)
        s.commit()
        s.refresh(emp)
        samples = s.exec(select(FaceSample).where(FaceSample.employee_id == employee_id)).all()
    face_engine.reload_gallery()
    return _employee_out(emp, samples)


@app.delete("/api/employees/{employee_id}")
def delete_employee(employee_id: int):
    with get_session() as s:
        emp = _get_employee(s, employee_id)
        for fs in s.exec(select(FaceSample).where(FaceSample.employee_id == employee_id)).all():
            s.delete(fs)
        for r in s.exec(select(Sighting).where(Sighting.employee_id == employee_id)).all():
            r.employee_id = None
            s.add(r)
        for d in s.exec(select(DeskSample).where(DeskSample.employee_id == employee_id)).all():
            s.delete(d)
        s.delete(emp)
        s.commit()
    shutil.rmtree(FACES_DIR / str(employee_id), ignore_errors=True)
    face_engine.reload_gallery()
    return {"status": "deleted"}


@app.put("/api/employees/{employee_id}/desk")
def set_desk(employee_id: int, body: DeskIn):
    zone = None
    if body.zone:
        if len(body.zone) != 4 or not all(0 <= v <= 1 for v in body.zone):
            raise HTTPException(status_code=400, detail="Zona 4 ta 0..1 oralig'idagi son bo'lishi kerak")
        zone = ",".join(f"{v:.4f}" for v in body.zone)
    with get_session() as s:
        emp = _get_employee(s, employee_id)
        emp.desk_channel = body.desk_channel
        emp.desk_zone = zone
        s.add(emp)
        s.commit()
    return {"status": "ok", "desk_channel": body.desk_channel, "zone": body.zone}


# =============================================================================
# 5. YUZ NAMUNALARI (o'rgatish)
# =============================================================================

_capture_cache: Dict[str, Tuple[float, np.ndarray, List[FaceResult]]] = {}
_capture_lock = threading.Lock()


def _require_engine() -> None:
    if not face_engine.available:
        raise HTTPException(status_code=503, detail=face_engine.status().get("error") or "Yuz tanish tayyor emas")


def _save_sample(employee_id: int, img: np.ndarray, face: FaceResult, source: str) -> FaceSample:
    d = FACES_DIR / str(employee_id)
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{uuid.uuid4().hex[:10]}.jpg"
    p.write_bytes(encode_jpeg(crop_face(img, face), 92))
    fs = FaceSample(employee_id=employee_id, embedding=emb_to_bytes(face.embedding),
                    image_path=p.relative_to(settings.DATA_DIR).as_posix(), source=source)
    with get_session() as s:
        s.add(fs)
        s.commit()
        s.refresh(fs)
    return fs


def retro_identify(days: int = 14) -> int:
    """Yangi namunalardan so'ng oxirgi kunlardagi notanish ko'rinishlarni qayta taniydi."""
    face_engine.reload_gallery()
    since = datetime.now() - timedelta(days=days)
    updated = 0
    with get_session() as s:
        rows = s.exec(select(Sighting).where(Sighting.employee_id == None, Sighting.ts >= since)).all()  # noqa: E711
        for r in rows:
            eid, sim = face_engine.identify(bytes_to_emb(r.embedding))
            if eid is not None:
                r.employee_id, r.similarity = eid, sim
                s.add(r)
                updated += 1
        s.commit()
    return updated


@app.get("/api/faces/status")
def faces_status():
    return face_engine.status()


@app.get("/api/employees/{employee_id}/faces")
def list_faces(employee_id: int):
    with get_session() as s:
        rows = s.exec(select(FaceSample).where(FaceSample.employee_id == employee_id)
                      .order_by(FaceSample.created_at.desc())).all()
    return [{"id": r.id, "url": f"/media/{r.image_path}", "source": r.source,
             "created_at": r.created_at.isoformat(timespec="minutes")} for r in rows]


@app.post("/api/employees/{employee_id}/faces/upload")
async def upload_faces(employee_id: int, files: List[UploadFile] = File(...)):
    _require_engine()
    with get_session() as s:
        _get_employee(s, employee_id)
    results = []
    for f in files:
        img = decode_jpeg(await f.read())
        if img is None:
            results.append({"file": f.filename, "ok": False, "reason": "rasm o'qilmadi"})
            continue
        faces = [x for x in face_engine.analyze(img, identify=False) if not x.too_small and x.embedding is not None]
        if not faces:
            results.append({"file": f.filename, "ok": False, "reason": "yuz topilmadi (yoki juda kichik)"})
            continue
        face = max(faces, key=lambda x: x.box[2] * x.box[3])
        _save_sample(employee_id, img, face, "upload")
        results.append({"file": f.filename, "ok": True,
                        "note": f"{len(faces)} ta yuzdan eng kattasi olindi" if len(faces) > 1 else None})
    updated = retro_identify() if any(r["ok"] for r in results) else 0
    return {"results": results, "retro_identified": updated}


@app.post("/api/faces/capture")
def capture_faces(channel: int):
    _require_engine()
    jpeg = capture_snapshot(channel, sub_stream=False, timeout_seconds=8.0)
    img = decode_jpeg(jpeg) if jpeg else None
    if img is None:
        raise HTTPException(status_code=502, detail=f"CH-{channel:02d} kamerasidan kadr olinmadi")
    faces = face_engine.analyze(img)
    token = uuid.uuid4().hex
    now = time.time()
    with _capture_lock:
        for k in [k for k, v in _capture_cache.items() if now - v[0] > 600]:
            _capture_cache.pop(k, None)
        _capture_cache[token] = (now, img, faces)
    return {
        "token": token,
        "image_b64": _b64(encode_jpeg(face_engine.annotate(img, faces), 80, max_side=1280)),
        "faces": [{"index": i, "crop_b64": _b64(encode_jpeg(crop_face(img, f), 88)),
                   "name": f.name, "similarity": round(f.similarity, 2), "too_small": f.too_small,
                   "size": f"{f.box[2]}x{f.box[3]}"} for i, f in enumerate(faces)],
    }


class FromCaptureIn(BaseModel):
    token: str
    index: int


@app.post("/api/employees/{employee_id}/faces/from-capture")
def face_from_capture(employee_id: int, body: FromCaptureIn):
    with _capture_lock:
        item = _capture_cache.get(body.token)
    if not item:
        raise HTTPException(status_code=410, detail="Kadr eskirgan, qaytadan oling")
    _, img, faces = item
    if not (0 <= body.index < len(faces)):
        raise HTTPException(status_code=400, detail="Noto'g'ri yuz indeksi")
    face = faces[body.index]
    if face.too_small or face.embedding is None:
        raise HTTPException(status_code=400, detail="Yuz juda kichik — kameraga yaqinroq turing")
    with get_session() as s:
        _get_employee(s, employee_id)
    fs = _save_sample(employee_id, img, face, "camera")
    return {"id": fs.id, "retro_identified": retro_identify()}


@app.delete("/api/faces/{sample_id}")
def delete_face(sample_id: int):
    with get_session() as s:
        fs = s.get(FaceSample, sample_id)
        if not fs:
            raise HTTPException(status_code=404, detail="Namuna topilmadi")
        (settings.DATA_DIR / fs.image_path).unlink(missing_ok=True)
        s.delete(fs)
        s.commit()
    face_engine.reload_gallery()
    return {"status": "deleted"}


# =============================================================================
# 6. KO'RINISHLAR (notanish yuzlarni biriktirish)
# =============================================================================

@app.get("/api/sightings/unknown")
def unknown_sightings(days: int = 7, limit: int = 60):
    since = datetime.now() - timedelta(days=days)
    with get_session() as s:
        rows = s.exec(select(Sighting).where(Sighting.employee_id == None, Sighting.ts >= since)  # noqa: E711
                      .order_by(Sighting.ts.desc()).limit(limit)).all()
    return [{"id": r.id, "ts": r.ts.isoformat(timespec="seconds"), "channel": r.channel,
             "camera": settings.get_camera(r.channel)["name"],
             "face_url": f"/media/{r.face_path}", "frame_url": f"/media/{r.frame_path}"} for r in rows]


class AssignIn(BaseModel):
    employee_id: int


@app.post("/api/sightings/{sighting_id}/assign")
def assign_sighting(sighting_id: int, body: AssignIn):
    with get_session() as s:
        r = s.get(Sighting, sighting_id)
        if not r:
            raise HTTPException(status_code=404, detail="Ko'rinish topilmadi")
        _get_employee(s, body.employee_id)
        d = FACES_DIR / str(body.employee_id)
        d.mkdir(parents=True, exist_ok=True)
        dst = d / f"s{r.id}_{uuid.uuid4().hex[:6]}.jpg"
        src = settings.DATA_DIR / r.face_path
        if src.exists():
            shutil.copy(src, dst)
        embedding = r.embedding
        if len(embedding) != face_engine.dim * 4:  # eski modelda yozilgan ko'rinish
            crop = decode_jpeg(src.read_bytes()) if src.exists() else None
            v = face_engine.embed_crop(crop) if crop is not None else None
            if v is None:
                raise HTTPException(status_code=400, detail="Bu rasmdan yuzni ajratib bo'lmadi")
            embedding = emb_to_bytes(v)
        s.add(FaceSample(employee_id=body.employee_id, embedding=embedding,
                         image_path=dst.relative_to(settings.DATA_DIR).as_posix(), source="sighting"))
        r.employee_id, r.similarity = body.employee_id, 1.0
        s.add(r)
        s.commit()
    return {"status": "ok", "retro_identified": retro_identify()}


@app.delete("/api/sightings/{sighting_id}")
def delete_sighting(sighting_id: int):
    with get_session() as s:
        r = s.get(Sighting, sighting_id)
        if not r:
            raise HTTPException(status_code=404, detail="Ko'rinish topilmadi")
        for p in (r.face_path, r.frame_path):
            if p:
                (settings.DATA_DIR / p).unlink(missing_ok=True)
        s.delete(r)
        s.commit()
    return {"status": "deleted"}


# =============================================================================
# 7. DAVOMAT VA FON ISHCHILARI
# =============================================================================

@app.get("/api/attendance")
def attendance(date: Optional[str] = None):
    day = date or date_cls.today().isoformat()
    try:
        datetime.strptime(day, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="Sana formati: YYYY-MM-DD")
    return staff_service.daily_attendance(day)


@app.get("/api/attendance/live-events")
def live_events(limit: int = 30):
    return worker_manager.recent_events(limit)


@app.get("/api/workers/status")
def workers_status():
    return worker_manager.status()


class ForceIn(BaseModel):
    on: bool


@app.post("/api/workers/force")
def workers_force(body: ForceIn):
    worker_manager.force_on = body.on
    return worker_manager.status()


@app.post("/api/desk/check-now")
def desk_check_now():
    _require_engine()
    res = worker_manager.desk.run_once()
    emps = staff_service.employees_all()
    return {str(ch): [{"employee_id": eid, "name": emps[eid].full_name if eid in emps else eid,
                       "present": p, "method": m} for eid, (p, m) in r.items()] for ch, r in res.items()}


# =============================================================================
# 8. CHAT
# =============================================================================

class ChatRequest(BaseModel):
    query: str
    session_id: str = "default"
    force_channel: Optional[int] = None
    want_clip: bool = False
    want_gallery: bool = True
    live_clip_seconds: int = 8


class ChatResponse(BaseModel):
    query: str
    answer: str
    mode: str  # live | playback | staff | general
    channel: Optional[int] = None
    camera_name: Optional[str] = None
    snapshot_b64: Optional[str] = None
    frames_b64: Optional[List[str]] = None
    video_url: Optional[str] = None
    time_start: Optional[str] = None
    time_end: Optional[str] = None
    job: Optional[dict] = None              # fon vazifasi (klip / video xulosa) — brauzer progressni so'raydi
    results: Optional[List[dict]] = None    # semantik qidiruv natijalari


_RE_SUMMARY = re.compile(r"(xulosa|qisqacha)\s*(klip|video|montaj)|video\s*xulosa|montaj|sekundlik\s*(xulosa|klip)", re.I)
_RE_CLIP = re.compile(r"\bklip|video(ni|sini)?\s*(yoz|kes|ber|tayyorla|chiqar)", re.I)
_RE_SEARCH = re.compile(r"\bqachon\b|qidir|izla|\btop(ib|ing|gin|ish)?\b|bo'lganmi|bo'ldimi|qaysi\s*kun|tunda|kechasi|kim\s+kirdi|ochiq\s*qol", re.I)
_PTZ_WORDS = {
    "chapga": (-50, 0, 0), "o'ngga": (50, 0, 0), "ongga": (50, 0, 0), "tepaga": (0, 50, 0), "yuqoriga": (0, 50, 0),
    "pastga": (0, -50, 0), "yaqinlashtir": (0, 0, 50), "kattalashtir": (0, 0, 50), "zoom": (0, 0, 50),
    "uzoqlashtir": (0, 0, -50), "kichraytir": (0, 0, -50),
}


def _ext_chat(query: str, intent, explicit_range, history) -> Optional[ChatResponse]:
    """Bosqich 4–5 niyatlari: PTZ, video xulosa, klip (fon vazifasi), semantik qidiruv."""
    q = query.lower().replace("’", "'").replace("ʻ", "'")
    ch = intent.channel

    # PTZ: "6-kamerani chapga bur", "3-kamera preset 2"
    preset = re.search(r"preset\s*(\d+)", q)
    move = next((v for k, v in _PTZ_WORDS.items() if k in q), None)
    if ch and (preset or (move and re.search(r"bur|sur|yaqin|uzoq|zoom|kattalash|kichray", q))):
        import nvr_isapi
        if not nvr_isapi.ptz_supported(ch):
            return ChatResponse(query=query, mode="general", channel=ch,
                                answer=f"⚠️ CH-{ch:02d} PTZ (buriluvchi) kamera emas yoki NVR javob bermadi.")
        if preset:
            ok = nvr_isapi.ptz_goto(ch, int(preset.group(1)))
            msg = f"🎯 CH-{ch:02d} preset {preset.group(1)} ga o'tkazildi." if ok else "Presetga o'tib bo'lmadi."
        else:
            ok = nvr_isapi.ptz_move(ch, *move)
            threading.Timer(1.2, nvr_isapi.ptz_stop, args=(ch,)).start()
            msg = f"🎮 CH-{ch:02d} kamerasi burildi." if ok else "PTZ buyrug'i bajarilmadi."
        return ChatResponse(query=query, mode="general", channel=ch, answer=msg)

    # Video xulosa (montaj)
    if _RE_SUMMARY.search(q):
        from video_summary import build_summary
        day = staff_service.parse_days(query)[-1]
        title = f"Video xulosa · {day}" + (f" · CH-{ch:02d}" if ch else "")
        job = jobs.submit("summary", title, lambda j: build_summary(j, day, ch))
        return ChatResponse(query=query, mode="job", channel=ch, job=job.to_dict(),
                            answer=f"🎬 **{day}** kuni uchun ~30 soniyalik xulosa montaj tayyorlanmoqda. "
                                   "Eng muhim lahzalar (ogohlantirishlar, yuzlar, kuchli harakat) NVR arxividan kesiladi — progress quyida.")

    # Aniq vaqtli klip (fon vazifasi)
    if _RE_CLIP.search(q) and ch and explicit_range:
        start, end = explicit_range
        secs = int(min(30, max(3, (end - start).total_seconds())))

        def run(job):
            job.update(0.05, "NVR arxividan qidirilmoqda…")
            name = record_playback_clip(ch, start, start + timedelta(seconds=secs), max_seconds=secs)
            if not name:
                raise RuntimeError("NVR arxividan klip olinmadi")
            return {"url": f"/clips/{name}", "channel": ch, "start": start.isoformat(timespec="seconds")}

        job = jobs.submit("clip", f"CH-{ch:02d} · {start:%H:%M:%S}", run)
        return ChatResponse(query=query, mode="job", channel=ch, job=job.to_dict(),
                            answer=f"🎞️ CH-{ch:02d} · {start:%Y-%m-%d %H:%M:%S} dan {secs} soniyalik klip kesilmoqda…")

    # Semantik qidiruv (arxiv indeksi + ogohlantirishlar)
    if _RE_SEARCH.search(q) and not explicit_range and not re.search(r"keldi|ketdi|kechik|ishladi|davomat", q):
        import indexer
        days = staff_service.parse_days(query)
        if len(days) == 1 and days[0] == date_cls.today().isoformat() and "bugun" not in q:
            days = [(date_cls.today() - timedelta(days=i)).isoformat() for i in range(7)]
        answer, hits = indexer.search(query, days, ch)
        return ChatResponse(query=query, mode="search", channel=ch, answer=answer, results=hits)
    return None


def _read_media(rel: str) -> Optional[bytes]:
    p = settings.DATA_DIR / rel
    return p.read_bytes() if rel and p.exists() else None


def _staff_chat(sq: staff_service.StaffQuery, query: str, explicit_range, channel, history) -> Optional[ChatResponse]:
    if sq.kind == "locate":
        if not face_engine.available:
            return ChatResponse(query=query, mode="staff",
                                answer="⚠️ Yuz tanish modellari hali tayyor emas, xodimni kameralardan qidira olmayman.")
        online = nvr_online()
        found = staff_service.scan_all_cameras([e.id for e in sq.employees]) if online else []
        lines = [] if online else ["⚠️ Kameralar ulanmagan — kameralardan jonli qidirib bo'lmadi. Bazadagi oxirgi ma'lumot:"]
        for emp in sq.employees:
            hits = [f for f in found if any(p["employee_id"] == emp.id for p in f["people"])]
            if hits:
                where = ", ".join(f"**{h['camera']}** (CH-{h['channel']:02d})" for h in hits)
                lines.append(f"📍 **{emp.full_name}** hozir {where} da ko'rinmoqda.")
            else:
                ls = staff_service.last_seen(emp.id)
                tail = (f"oxirgi marta {ls['ts'][11:16]} ({ls['ts'][:10]}) da **{ls['camera']}** "
                        f"(CH-{ls['channel']:02d}, {ls['source']}) da ko'rilgan.") if ls else "bazada ko'rinish qayd etilmagan."
                head = f"❔ **{emp.full_name}** hozir hech bir kamerada yuzi ko'rinmadi; " if online else f"• **{emp.full_name}** — "
                lines.append(head + tail)
        imgs = [_b64(f["image_jpeg"]) for f in found]
        return ChatResponse(query=query, answer="\n".join(lines), mode="staff",
                            channel=found[0]["channel"] if found else None,
                            snapshot_b64=imgs[0] if imgs else None, frames_b64=imgs if len(imgs) > 1 else None)

    if sq.kind == "camera_count":
        if explicit_range:
            start, end = explicit_range
        else:
            d0 = datetime.strptime(sq.days[0], "%Y-%m-%d")
            d1 = datetime.strptime(sq.days[-1], "%Y-%m-%d")
            start, end = d0, min(datetime.now(), d1 + timedelta(days=1))
        facts = staff_service.people_on_camera(channel, start, end)
        if facts["coverage"] < 0.5 and explicit_range:
            return None  # aniq oraliq va kuzatuv qamrovi past — NVR arxividan namuna tahliliga o'tamiz
        answer = staff_answer(query, facts, history)
        if not answer:
            known = ", ".join(f"{k['name']} ({', '.join(k['times'][:3])})" for k in facts["known"]) or "yo'q"
            answer = (f"**{facts['camera']}** — {facts['from'][11:]}–{facts['to'][11:]}: taxminan "
                      f"**{facts['total_people_estimate']} kishi** (tanilganlar: {known}; notanish: "
                      f"~{facts['unknown_people_estimate']}). Qamrov: {int(facts['coverage'] * 100)}%.")
        with get_session() as s:
            rows = s.exec(select(Sighting).where(Sighting.channel == channel, Sighting.ts >= start,
                                                 Sighting.ts <= end).order_by(Sighting.ts.desc()).limit(9)).all()
        faces = [_b64(b) for b in (_read_media(r.face_path) for r in rows) if b]
        return ChatResponse(query=query, answer=answer, mode="staff", channel=channel,
                            camera_name=facts["camera"], frames_b64=faces or None,
                            time_start=start.isoformat(), time_end=end.isoformat())

    facts = staff_service.attendance_facts(sq)
    answer = staff_answer(query, facts, history) or staff_service.attendance_text(facts)
    return ChatResponse(query=query, answer=answer, mode="staff")


@app.post("/api/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    query = (req.query or "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="Bo'sh so'rov")

    chat_memory.append(req.session_id, "user", query)
    history = chat_memory.get(req.session_id)

    intent = parse_intent(query)
    explicit_range = _extract_time_range(query)

    # === PTZ / VIDEO XULOSA / KLIP / QIDIRUV ===
    ext = _ext_chat(query, intent, explicit_range, history[:-1])
    if ext:
        chat_memory.append(req.session_id, "assistant", ext.answer)
        return ext

    # === XODIMLAR / DAVOMAT ===
    sq = staff_service.detect_staff_query(query, intent.channel, explicit_range is not None)
    if sq:
        resp = _staff_chat(sq, query, explicit_range, intent.channel, history[:-1])
        if resp:
            chat_memory.append(req.session_id, "assistant", resp.answer)
            return resp

    if intent.channel is None and req.force_channel is not None:
        intent.channel = req.force_channel

    # === LIVE ===
    if intent.kind == "live" and intent.channel is not None:
        cam = settings.get_camera(intent.channel)
        frames = capture_live_burst(intent.channel, count=3, spacing_seconds=1.0) if req.want_gallery else []
        if not frames:
            one = capture_snapshot(intent.channel)
            frames = [one] if one else []
        if not frames:
            answer = f"⚠️ {cam['name']} (CH-{intent.channel:02d}) oqimidan kadr olib bo'lmadi. NVR ulanishini tekshiring."
            chat_memory.append(req.session_id, "assistant", answer)
            return ChatResponse(query=query, answer=answer, mode="live", channel=intent.channel, camera_name=cam["name"])

        main_frame = frames[-1]
        face_context = ""
        if face_engine.available:
            hq = capture_snapshot(intent.channel, sub_stream=False, max_attempts=1)
            img = decode_jpeg(hq or main_frame)
            faces = face_engine.analyze(img, channel=intent.channel) if img is not None else []
            if faces:
                known = [f"{f.name} ({int(f.similarity * 100)}%)" for f in faces if f.known]
                unknown = sum(1 for f in faces if not f.known and not f.too_small)
                parts = known + ([f"{unknown} ta notanish odam"] if unknown else [])
                face_context = ", ".join(parts)
                main_frame = encode_jpeg(face_engine.annotate(img, faces), 85, max_side=1600)
            elif hq:
                main_frame = hq

        answer = analyze_live(image_bytes=main_frame, query=query, camera_name=cam["name"],
                              channel=intent.channel, history=history[:-1], face_context=face_context)
        chat_memory.append(req.session_id, "assistant", answer)

        video_url: Optional[str] = None
        if req.want_clip:
            clip = record_live_clip(intent.channel, duration_seconds=max(3, min(30, req.live_clip_seconds)))
            if clip:
                video_url = f"/clips/{clip}"
        gallery = frames[:-1] + [main_frame]
        return ChatResponse(query=query, answer=answer, mode="live", channel=intent.channel, camera_name=cam["name"],
                            snapshot_b64=_b64(main_frame),
                            frames_b64=[_b64(f) for f in gallery] if len(gallery) > 1 else None,
                            video_url=video_url)

    # === PLAYBACK ===
    if intent.kind == "playback" and intent.channel is not None and intent.time_start and intent.time_end:
        cam = settings.get_camera(intent.channel)
        pb_start, pb_end = intent.time_start, intent.time_end
        span_seconds = (pb_end - pb_start).total_seconds()

        if span_seconds > 3 * 60:
            span_hours = span_seconds / 3600
            sample_count = max(4, int(span_seconds / 60)) if span_hours < 0.5 else int(max(8, min(25, span_hours * 5)))
            samples = sample_playback_range(intent.channel, pb_start, pb_end, sample_count=sample_count, max_workers=6)
            answer = analyze_long_range(samples=samples, query=query, camera_name=cam["name"],
                                        channel=intent.channel, start=pb_start, end=pb_end, history=history[:-1])
            chat_memory.append(req.session_id, "assistant", answer)
            return ChatResponse(query=query, answer=answer, mode="playback", channel=intent.channel,
                                camera_name=cam["name"],
                                snapshot_b64=_b64(samples[0][1]) if samples else None,
                                frames_b64=[_b64(b) for _, b in samples] if samples else None,
                                time_start=pb_start.isoformat(), time_end=pb_end.isoformat())

        clip_start, clip_end = pb_start, min(pb_end, pb_start + timedelta(seconds=30))
        frames = capture_playback_frames(intent.channel, pb_start, pb_end, frames_wanted=3)
        answer = analyze_playback(frames=frames, query=query, camera_name=cam["name"], channel=intent.channel,
                                  start=pb_start, end=pb_end, history=history[:-1])
        chat_memory.append(req.session_id, "assistant", answer)
        video_url = None
        if req.want_clip:
            clip = record_playback_clip(intent.channel, clip_start, clip_end, max_seconds=30)
            if clip:
                video_url = f"/clips/{clip}"
        return ChatResponse(query=query, answer=answer, mode="playback", channel=intent.channel,
                            camera_name=cam["name"],
                            snapshot_b64=_b64(frames[0]) if frames else None,
                            frames_b64=[_b64(f) for f in frames] if len(frames) > 1 else None,
                            video_url=video_url, time_start=pb_start.isoformat(), time_end=pb_end.isoformat())

    # === UMUMIY ===
    answer = general_reply(query=query, history=history[:-1])
    chat_memory.append(req.session_id, "assistant", answer)
    return ChatResponse(query=query, answer=answer, mode="general", channel=intent.channel)


@app.get("/api/chat/history")
def get_history(session_id: str = "default", limit: int = 30):
    turns = chat_memory.get(session_id, limit=limit)
    return [{"role": t.role, "content": t.content, "ts": t.ts.isoformat()} for t in turns]


@app.delete("/api/chat/history")
def clear_history(session_id: str = "default"):
    chat_memory.clear(session_id)
    return {"status": "cleared"}


# =============================================================================
# 9. FRONTEND (React SPA) — barcha API marshrutlaridan keyin turishi shart
# =============================================================================

@app.get("/{full_path:path}", include_in_schema=False)
def spa(full_path: str):
    if full_path.startswith(("api/", "media/", "clips/", "assets/")):
        raise HTTPException(status_code=404, detail="Topilmadi")
    if full_path:
        f = (FRONTEND_DIST / full_path).resolve()
        if f.is_file() and FRONTEND_DIST.resolve() in f.parents:
            return FileResponse(f)
    index = FRONTEND_DIST / "index.html"
    if not index.exists():
        return HTMLResponse("<h3>Frontend build topilmadi.</h3><p>cd frontend &amp;&amp; npm install &amp;&amp; npm run build</p>", status_code=503)
    return FileResponse(index, headers={"Cache-Control": "no-cache"})


if __name__ == "__main__":
    import uvicorn
    print("=" * 70)
    print("  CCTV AI Assistant — xodimlar boshqaruvi + AI kuzatuv")
    print(f"  NVR: {settings.NVR_IP} | Kanallar: {len(settings.channel_ids)}")
    print(f"  Davomat kameralari: {settings.attendance_channels} ")
    print(f"  Web: http://127.0.0.1:{settings.PORT}")
    print("=" * 70)
    uvicorn.run(app, host=settings.HOST, port=settings.PORT)
