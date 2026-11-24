"""
UI orqali boshqariladigan sozlamalar (SQLite `setting` jadvali).
.env — o'rnatish konfiguratsiyasi; bu yerda — foydalanuvchi ish paytida o'zgartiradigan narsalar.
"""

from __future__ import annotations

import json
import threading
from typing import Any, Dict

from sqlmodel import select

from database import Setting, get_session

DEFAULTS: Dict[str, Any] = {
    # Telegram
    "telegram_token": "",
    "telegram_chat_id": "",
    # Bosqich 2 — ogohlantirishlar
    "alert_unknown_face": True,
    "alert_unknown_cooldown_min": 5,
    "alert_after_hours": True,
    "security_cameras": [2, 6, 9, 14, 18],
    "after_hours_start": "20:00",
    "after_hours_end": "07:00",
    "after_hours_weekends": True,          # dam olish kunlari kun bo'yi qo'riqlash
    "after_hours_cooldown_min": 10,
    "alert_camera_offline": True,
    # Bosqich 3 — hisobotlar
    "daily_summary": True,
    "daily_summary_time": "19:00",
    "weekly_report": True,                 # dushanba 08:00 Telegram'ga Excel+PDF
    # Bosqich 5
    "agent_enabled": True,
    "agent_away_minutes": 40,
    "announce_arrivals": True,
    "alert_tts": False,                    # ovozli ogohlantirish — faqat alertlar uchun, standart o'chiq
    "tts_voice": "uz-UZ-MadinaNeural",
    "indexer_enabled": True,
    # Xodim qayerda (presence.py)
    "lunch_start": "13:00",
    "lunch_end": "14:00",
    "yard_max_min": 10,                    # hovlida shundan ko'p — "ofisdan tashqarida"
    "blind_max_min": 15,                   # kamerasiz joyda shundan ko'p — rahbarga xabar
    "room_grace_min": 5,                   # kamerali xona shuncha bo'sh tursa — "noma'lum"
    "indexer_interval_min": 15,
}

# UI'ga qaytarilmaydigan maxfiy kalitlar (faqat "o'rnatilgan" belgisi)
SECRET_KEYS = {"telegram_token"}


class SettingsStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._cache: Dict[str, Any] | None = None

    def _load(self) -> Dict[str, Any]:
        if self._cache is None:
            data = dict(DEFAULTS)
            with get_session() as s:
                for row in s.exec(select(Setting)).all():
                    if row.key not in DEFAULTS:  # olib tashlangan funksiyalarning eski sozlamalari
                        continue
                    try:
                        data[row.key] = json.loads(row.value)
                    except ValueError:
                        continue
            self._cache = data
        return self._cache

    def get(self, key: str) -> Any:
        with self._lock:
            return self._load().get(key, DEFAULTS.get(key))

    def all(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self._load())

    def public(self) -> Dict[str, Any]:
        data = self.all()
        for k in SECRET_KEYS:
            data[f"{k}_set"] = bool(data.get(k))
            data[k] = ""
        return data

    def update(self, values: Dict[str, Any]) -> Dict[str, Any]:
        clean = {}
        for k, v in values.items():
            if k not in DEFAULTS:
                continue
            if k in SECRET_KEYS and v in ("", None):
                continue  # bo'sh maxfiy maydon — o'zgartirmaslik
            expected = type(DEFAULTS[k])
            if expected is bool:
                v = bool(v)
            elif expected is int:
                v = int(v)
            elif expected is list:
                v = [int(x) for x in v]
            elif expected is str:
                v = str(v).strip()
            clean[k] = v
        with self._lock:
            with get_session() as s:
                for k, v in clean.items():
                    s.merge(Setting(key=k, value=json.dumps(v, ensure_ascii=False)))
                s.commit()
            data = self._load()
            data.update(clean)
        return clean


store = SettingsStore()
