"""
Yagona ogohlantirish shinasi:
  create() → SQLite `alert` → SSE (brauzer real vaqtda) → Telegram → (ixtiyoriy) o'zbekcha TTS.
Har bir manba (notanish yuz, ish vaqtidan tashqari harakat, agent) shu yerdan o'tadi.
"""

from __future__ import annotations

import asyncio
import html
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

from config import settings
from database import Alert, get_session
from face_engine import encode_jpeg
from settings_store import store
from telegram_notifier import sender

ALERTS_DIR = settings.DATA_DIR / "alerts"
TTS_DIR = settings.DATA_DIR / "tts"

KIND_LABEL = {
    "unknown_face": "Notanish odam",
    "after_hours": "Ish vaqtidan tashqari harakat",
    "camera_offline": "Kamera aloqasi",
    "agent": "AI agent",
    "daily_summary": "Kunlik xulosa",
    "arrival": "Xodim keldi",
    "test": "Sinov",
}
SEVERITY_ICON = {"info": "ℹ️", "warning": "⚠️", "critical": "🚨"}


def _rel(p: Path) -> str:
    return p.relative_to(settings.DATA_DIR).as_posix()


def alert_to_dict(a: Alert) -> dict:
    tts = TTS_DIR / f"{a.id}.mp3"
    return {
        "id": a.id, "ts": a.ts.isoformat(timespec="seconds"), "kind": a.kind, "kind_label": KIND_LABEL.get(a.kind, a.kind),
        "severity": a.severity, "channel": a.channel, "employee_id": a.employee_id, "title": a.title, "message": a.message,
        "snapshot_url": f"/media/{a.snapshot_path}" if a.snapshot_path else None,
        "clip_url": f"/clips/{a.clip_path}" if a.clip_path else None,
        "tts_url": f"/media/tts/{a.id}.mp3" if tts.exists() else None,
        "acknowledged": a.acknowledged,
    }


class AlertBus:
    def __init__(self) -> None:
        self._subs: List[Tuple[asyncio.AbstractEventLoop, asyncio.Queue]] = []
        self._lock = threading.Lock()
        self._cooldown: Dict[str, float] = {}

    # ------------------------------------------------------------ SSE obunachilar
    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=100)
        with self._lock:
            self._subs.append((asyncio.get_running_loop(), q))
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        with self._lock:
            self._subs = [(l, x) for l, x in self._subs if x is not q]

    def publish(self, event: dict) -> None:
        with self._lock:
            subs = list(self._subs)
        for loop, q in subs:
            def _put(q=q):
                if not q.full():
                    q.put_nowait(event)
            try:
                loop.call_soon_threadsafe(_put)
            except RuntimeError:
                self.unsubscribe(q)

    # ------------------------------------------------------------ cooldown
    def allow(self, key: str, minutes: float) -> bool:
        now = time.time()
        with self._lock:
            if now - self._cooldown.get(key, 0) < minutes * 60:
                return False
            self._cooldown[key] = now
            return True

    # ------------------------------------------------------------ yaratish
    def create(self, kind: str, title: str, message: str = "", severity: str = "info",
               channel: Optional[int] = None, employee_id: Optional[int] = None,
               frame: Optional[np.ndarray] = None, snapshot_path: str = "", clip_path: str = "",
               notify: bool = True) -> Alert:
        now = datetime.now()
        if frame is not None and not snapshot_path:
            d = ALERTS_DIR / now.strftime("%Y-%m-%d")
            d.mkdir(parents=True, exist_ok=True)
            p = d / f"{kind}_{now:%H%M%S}_{uuid.uuid4().hex[:6]}.jpg"
            p.write_bytes(encode_jpeg(frame, 82, max_side=1280))
            snapshot_path = _rel(p)
        row = Alert(ts=now, date=now.strftime("%Y-%m-%d"), kind=kind, severity=severity, channel=channel,
                    employee_id=employee_id, title=title, message=message,
                    snapshot_path=snapshot_path, clip_path=clip_path)
        with get_session() as s:
            s.add(row)
            s.commit()
            s.refresh(row)

        if store.get("alert_tts") and severity in ("warning", "critical"):
            self._make_tts(row)
        self.publish({"type": "alert", "alert": alert_to_dict(row)})

        if notify:
            cam = f"\n📹 {settings.get_camera(channel)['name']} (CH-{channel:02d})" if channel else ""
            caption = (f"{SEVERITY_ICON.get(severity, '')} <b>{html.escape(title)}</b>{cam}\n"
                       f"🕒 {now:%Y-%m-%d %H:%M:%S}\n{html.escape(message)}").strip()
            if snapshot_path:
                sender.enqueue("photo", str(settings.DATA_DIR / snapshot_path), caption)
            else:
                sender.enqueue("text", caption)
        return row

    def update_clip(self, alert_id: int, clip_path: str) -> None:
        with get_session() as s:
            a = s.get(Alert, alert_id)
            if a:
                a.clip_path = clip_path
                s.add(a)
                s.commit()
                s.refresh(a)
                self.publish({"type": "alert_update", "alert": alert_to_dict(a)})

    # ------------------------------------------------------------ TTS (faqat alertlar uchun)
    def _make_tts(self, a: Alert) -> None:
        text = f"Diqqat. {a.title}."
        if a.channel:
            text += f" {settings.get_camera(a.channel)['name']}."
        TTS_DIR.mkdir(parents=True, exist_ok=True)
        out = TTS_DIR / f"{a.id}.mp3"

        async def _run():
            import edge_tts
            await edge_tts.Communicate(text, store.get("tts_voice") or "uz-UZ-MadinaNeural").save(str(out))

        def _thread():
            try:
                asyncio.run(asyncio.wait_for(_run(), timeout=12))
            except Exception as e:
                print(f"[TTS] yaratilmadi: {str(e)[:100]}")

        t = threading.Thread(target=_thread, daemon=True)
        t.start()
        t.join(timeout=13)


bus = AlertBus()
