"""
Bosqich 5.2 — kunning video xulosasi (≈30 s montaj).

Lahzalar: ogohlantirishlar > yuz ko'rinishlari > eng kuchli harakat daqiqalari.
Har lahzadan NVR arxividan 2 s kesiladi (bo'lmasa — kadrdan 2 s "slayd"), vaqt/kamera yozuvi qo'shiladi,
hammasi bitta MP4'ga ulanadi.
"""

from __future__ import annotations

import shutil
import subprocess
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional

from sqlmodel import select

from config import settings
from database import ActivityMinute, Alert, Employee, Sighting, get_session
from jobs import Job
from rtsp_manager import CLIPS_DIR, _grab_single_from_playback, _hik_time, nvr_online

SEG_SECONDS = 2
MAX_MOMENTS = 15
FONT = next((p for p in ("C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/arial.ttf",
                         "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf") if Path(p).exists()), None)


def _ff_font() -> str:
    return FONT.replace(":", "\\:") if FONT else ""


def pick_moments(day: str, channel: Optional[int] = None, limit: int = MAX_MOMENTS) -> List[dict]:
    with get_session() as s:
        alerts = s.exec(select(Alert).where(Alert.date == day, Alert.channel != None,  # noqa: E711
                                            Alert.kind.in_(["after_hours", "unknown_face", "arrival"]))).all()
        sights = s.exec(select(Sighting).where(Sighting.date == day)).all()
        acts = s.exec(select(ActivityMinute).where(ActivityMinute.date == day).order_by(ActivityMinute.motion.desc()).limit(200)).all()
        names = {e.id: e.full_name for e in s.exec(select(Employee)).all()}
    cands = []
    prio = {"after_hours": 90, "unknown_face": 70, "arrival": 60}
    for a in alerts:
        cands.append({"ts": a.ts, "channel": a.channel, "score": prio.get(a.kind, 50), "label": a.title})
    for r in sights:
        cands.append({"ts": r.ts, "channel": r.channel, "score": 40 if r.employee_id else 55,
                      "label": names.get(r.employee_id, "Notanish odam") if r.employee_id else "Notanish odam"})
    for m in acts:
        ts = datetime.fromisoformat(m.date) + timedelta(minutes=m.minute, seconds=20)
        cands.append({"ts": ts, "channel": m.channel, "score": 10 + m.motion * 100, "label": "Harakat"})
    if channel is not None:
        cands = [c for c in cands if c["channel"] == channel]
    cands.sort(key=lambda c: -c["score"])
    chosen: List[dict] = []
    for c in cands:
        if c["ts"] > datetime.now() - timedelta(minutes=2):
            continue
        if all(abs((c["ts"] - x["ts"]).total_seconds()) > 300 or c["channel"] != x["channel"] for x in chosen):
            chosen.append(c)
        if len(chosen) >= limit:
            break
    return sorted(chosen, key=lambda c: c["ts"])


def _label_filter(text: str) -> str:
    safe = text.replace("\\", "").replace("'", "’").replace(":", "\\:").replace("%", "\\%")
    font = f"fontfile='{_ff_font()}':" if FONT else ""
    return (f"scale=960:540:force_original_aspect_ratio=decrease,pad=960:540:(ow-iw)/2:(oh-ih)/2,fps=15,"
            f"drawbox=x=0:y=ih-56:w=iw:h=56:color=black@0.55:t=fill,"
            f"drawtext={font}text='{safe}':x=20:y=h-40:fontsize=24:fontcolor=white")


def _segment(m: dict, work: Path, idx: int) -> Optional[Path]:
    ts: datetime = m["ts"]
    start = ts - timedelta(seconds=1)
    out = work / f"seg_{idx:02d}.mp4"
    label = f"{ts:%H:%M:%S}  CH-{m['channel']:02d}  {m['label']}"[:70]
    url = settings.get_playback_rtsp(m["channel"], _hik_time(start), _hik_time(start + timedelta(seconds=SEG_SECONDS + 2)))
    cmd = ["ffmpeg", "-y", "-rtsp_transport", "tcp", "-timeout", "10000000", "-i", url, "-t", str(SEG_SECONDS), "-an",
           "-vf", _label_filter(label), "-c:v", "libx264", "-preset", "veryfast", "-crf", "26", "-pix_fmt", "yuv420p", str(out)]
    try:
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=90)
        if out.exists() and out.stat().st_size > 5000:
            return out
    except subprocess.TimeoutExpired:
        pass
    # Zaxira: bitta kadrdan 2 s "slayd"
    jpg = _grab_single_from_playback(m["channel"], ts)
    if not jpg:
        return None
    img = work / f"seg_{idx:02d}.jpg"
    img.write_bytes(jpg)
    cmd = ["ffmpeg", "-y", "-loop", "1", "-i", str(img), "-t", str(SEG_SECONDS), "-vf", _label_filter(label),
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "26", "-pix_fmt", "yuv420p", str(out)]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60)
    return out if out.exists() and out.stat().st_size > 2000 else None


def concat(segments: List[Path], out: Path) -> bool:
    lst = out.with_suffix(".txt")
    lst.write_text("".join(f"file '{p.as_posix()}'\n" for p in segments), encoding="utf-8")
    cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", "-movflags", "+faststart", str(out)]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)
    lst.unlink(missing_ok=True)
    return out.exists() and out.stat().st_size > 5000


def build_summary(job: Job, day: str, channel: Optional[int] = None) -> dict:
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg o'rnatilmagan")
    if not nvr_online():
        raise RuntimeError("Kameralar ulanmagan — arxivdan lahzalarni kesib bo'lmaydi")
    moments = pick_moments(day, channel)
    if not moments:
        raise RuntimeError("Bu kun uchun lahzalar topilmadi (kuzatuv ma'lumoti yo'q)")
    job.update(0.05, f"{len(moments)} ta lahza tanlandi, NVR arxividan kesilmoqda…")
    work = CLIPS_DIR / f"_sum_{uuid.uuid4().hex[:6]}"
    work.mkdir(parents=True, exist_ok=True)
    segs: List[Optional[Path]] = [None] * len(moments)
    done = 0
    try:
        with ThreadPoolExecutor(max_workers=3) as pool:
            futs = {pool.submit(_segment, m, work, i): i for i, m in enumerate(moments)}
            for f in futs:
                i = futs[f]
                segs[i] = f.result()
                done += 1
                job.update(0.05 + 0.85 * done / len(moments), f"{done}/{len(moments)} lahza tayyor")
        ok_segs = [s for s in segs if s]
        if not ok_segs:
            raise RuntimeError("NVR arxividan birorta ham lahza olinmadi")
        job.update(0.93, "Montaj qilinmoqda…")
        name = f"summary_{day}_{'all' if channel is None else f'ch{channel:02d}'}_{uuid.uuid4().hex[:6]}.mp4"
        if not concat(ok_segs, CLIPS_DIR / name):
            raise RuntimeError("Montaj muvaffaqiyatsiz")
        job.update(1.0, f"Tayyor: {len(ok_segs)} lahza, ~{len(ok_segs) * SEG_SECONDS} s")
        return {"url": f"/clips/{name}", "moments": [
            {"ts": m["ts"].isoformat(timespec="seconds"), "channel": m["channel"], "label": m["label"]}
            for m, s in zip(moments, segs) if s]}
    finally:
        shutil.rmtree(work, ignore_errors=True)
