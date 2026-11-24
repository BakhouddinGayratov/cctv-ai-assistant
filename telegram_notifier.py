"""Telegram Bot API orqali xabar/rasm/fayl yuborish (navbat + fon oqimi, tashqi kutubxonasiz)."""

from __future__ import annotations

import json
import queue
import threading
import urllib.request
import uuid
from pathlib import Path
from typing import Optional, Tuple

from settings_store import store


def _multipart(fields: dict, files: dict) -> Tuple[bytes, str]:
    boundary = uuid.uuid4().hex
    parts = []
    for k, v in fields.items():
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
    for k, (name, data, mime) in files.items():
        parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"; filename="{name}"\r\nContent-Type: {mime}\r\n\r\n'.encode()
            + data + b"\r\n"
        )
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def _call(method: str, fields: dict, files: Optional[dict] = None, token: Optional[str] = None, timeout: float = 30) -> dict:
    token = token or store.get("telegram_token")
    if not token:
        raise RuntimeError("Telegram bot tokeni sozlanmagan")
    url = f"https://api.telegram.org/bot{token}/{method}"
    if files:
        body, ctype = _multipart(fields, files)
    else:
        body, ctype = json.dumps(fields).encode(), "application/json"
    req = urllib.request.Request(url, data=body, headers={"Content-Type": ctype}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read())
    if not data.get("ok"):
        raise RuntimeError(data.get("description", "Telegram xatosi"))
    return data


def configured() -> bool:
    return bool(store.get("telegram_token")) and bool(store.get("telegram_chat_id"))


def send_message(text: str, chat_id: Optional[str] = None, token: Optional[str] = None) -> dict:
    return _call("sendMessage", {"chat_id": chat_id or store.get("telegram_chat_id"), "text": text[:4000],
                                 "parse_mode": "HTML", "disable_web_page_preview": True}, token=token)


def send_photo(photo: Path, caption: str) -> dict:
    return _call("sendPhoto", {"chat_id": store.get("telegram_chat_id"), "caption": caption[:1000], "parse_mode": "HTML"},
                 {"photo": (photo.name, photo.read_bytes(), "image/jpeg")})


def send_document(path: Path, caption: str = "") -> dict:
    mime = {".pdf": "application/pdf", ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ".mp4": "video/mp4", ".mp3": "audio/mpeg"}.get(path.suffix, "application/octet-stream")
    return _call("sendDocument", {"chat_id": store.get("telegram_chat_id"), "caption": caption[:1000], "parse_mode": "HTML"},
                 {"document": (path.name, path.read_bytes(), mime)}, timeout=120)


class _Sender:
    """Xabarlarni navbat bilan yuboradi — kamera oqimlari Telegram'ni kutmaydi."""

    def __init__(self) -> None:
        self._q: "queue.Queue[tuple]" = queue.Queue(maxsize=200)
        threading.Thread(target=self._run, name="telegram-sender", daemon=True).start()

    def enqueue(self, kind: str, *args) -> None:
        if not configured():
            return
        try:
            self._q.put_nowait((kind, args))
        except queue.Full:
            pass

    def _run(self) -> None:
        while True:
            kind, args = self._q.get()
            try:
                if kind == "photo" and args[0] and Path(args[0]).exists():
                    send_photo(Path(args[0]), args[1])
                elif kind == "document":
                    send_document(Path(args[0]), args[1])
                else:
                    send_message(args[-1] if kind == "photo" else args[0])
            except Exception as e:
                print(f"[Telegram] yuborilmadi: {str(e)[:120]}")


sender = _Sender()
