"""
Multi-Provider AI xizmati.

Falsafa: Gemini BIRINCHI → xato bo'lsa Groq FALLBACK.
Har bir muvaffaqiyatli chaqiruvdan keyin faol model global holatga yoziladi va
frontend'ga `/api/model/status` orqali qaytariladi.
"""

from __future__ import annotations

import base64
import io
import re
import threading
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Deque, Dict, List, Optional, Tuple

from PIL import Image

from config import settings


# =============================================================================
# 1. NIYAT VA KAMERA / VAQT ORALIG'INI AJRATISH
# =============================================================================

@dataclass
class Intent:
    kind: str  # "live" | "playback" | "general"
    channel: Optional[int] = None
    time_start: Optional[datetime] = None
    time_end: Optional[datetime] = None


_TIME_RE = re.compile(r"(\d{1,2})[:\.](\d{2})(?:[:\.](\d{2}))?")
_RANGE_RE = re.compile(
    r"(\d{1,2})[:\.](\d{2})(?:[:\.](\d{2}))?\s*(?:dan|-|—|to)\s*(\d{1,2})[:\.](\d{2})(?:[:\.](\d{2}))?",
    re.IGNORECASE,
)
_LIVE_KEYWORDS = (
    "hozir", "jonli", "ayni paytda", "shu daqiqa", "shu payt", "real vaqt", "real-time",
    "nechta odam", "nechta mashina", "kim bor", "nima bo'lyapti", "nima qilyapti",
    "tekshir", "qara", "qarachi", "ko'r", "korib ber", "kadrda", "eshik ochiqmi",
    "holat qanday",
)
_PLAYBACK_KEYWORDS = (
    "kecha", "bugun", "ertalab", "kechqurun", "tushdan keyin",
    "soat", "sodir bo'l", "nima bo'l", "bo'ldi", "keldi", "ketdi",
)


def _extract_channel(query: str) -> Optional[int]:
    q = query.lower().strip()
    for ch, (code_name, full_name) in settings.CAMERA_NAMES.items():
        if code_name in q or full_name.lower().split()[0] in q:
            return ch
    for pat in [
        r"(\d+)\s*[-_]?\s*(?:chi\s*)?kamera", r"kamera\s*#?\s*(\d+)",
        r"camera\s*#?\s*(\d+)", r"ch\s*[-_]?\s*(\d+)",
        r"kanal\s*#?\s*(\d+)", r"(\d+)\s*[-_]?\s*(?:chi\s*)?kanal",
    ]:
        m = re.search(pat, q)
        if m:
            v = int(m.group(1))
            if v in settings.channel_ids:
                return v
    words = {"birinchi": 1, "ikkinchi": 2, "uchinchi": 3, "to'rtinchi": 4, "beshinchi": 5,
             "oltinchi": 6, "yettinchi": 7, "sakkizinchi": 8, "to'qqizinchi": 9, "o'ninchi": 10}
    for w, n in words.items():
        if f"{w} kamera" in q or f"{w} kanal" in q:
            return n
    # So'z boshi bo'yicha: "omborga" → Omborxona, "garajda" → Garaj, "oshxonada" → Oshxona
    tokens = [t for t in re.findall(r"[a-z'ʻ]+", q.replace("_", " ")) if len(t) >= 5]
    for ch, (code_name, full_name) in settings.CAMERA_NAMES.items():
        stems = {w[:5] for w in re.findall(r"[a-z'ʻ]+", f"{code_name.replace('_', ' ')} {full_name.lower()}")
                 if len(w) >= 5 and w not in ("asosiy", "hududi", "zonasi", "qavat", "xonasi", "olish", "hisob", "kitob")}
        if any(t[:5] in stems for t in tokens):
            return ch
    return None


def _extract_time_range(query: str, now: Optional[datetime] = None) -> Optional[Tuple[datetime, datetime]]:
    q = query.lower()
    now = now or datetime.now()
    base_date = now.date()
    if "kecha" in q or "yesterday" in q:
        base_date = (now - timedelta(days=1)).date()

    m = re.search(r"(\d{4})[-./](\d{1,2})[-./](\d{1,2})", q)
    if m:
        try: base_date = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3))).date()
        except ValueError: pass
    else:
        m = re.search(r"(\d{1,2})[-./](\d{1,2})[-./](\d{4})", q)
        if m:
            try: base_date = datetime(int(m.group(3)), int(m.group(2)), int(m.group(1))).date()
            except ValueError: pass

    m = _RANGE_RE.search(q)
    if m:
        h1, mi1, s1, h2, mi2, s2 = m.groups()
        try:
            start = datetime.combine(base_date, datetime.min.time().replace(
                hour=int(h1), minute=int(mi1), second=int(s1 or 0)))
            end = datetime.combine(base_date, datetime.min.time().replace(
                hour=int(h2), minute=int(mi2), second=int(s2 or 0)))
            if end <= start: end += timedelta(days=1)
            # Uzoq oraliq uchun cheklov: max 12 soat (bir kunlik ish sessiyasi)
            if (end - start).total_seconds() > 12 * 3600:
                end = start + timedelta(hours=12)
            if end > datetime.now(): return None
            return start, end
        except ValueError: return None

    m = _TIME_RE.search(q)
    if m and any(kw in q for kw in ("soat", "kecha", "bugun")):
        try:
            h, mi, s = m.groups()
            start = datetime.combine(base_date, datetime.min.time().replace(
                hour=int(h), minute=int(mi), second=int(s or 0)))
            end = start + timedelta(minutes=1)
            if end > datetime.now(): return None
            return start, end
        except ValueError: return None
    return None


def parse_intent(query: str) -> Intent:
    ch = _extract_channel(query)
    tr = _extract_time_range(query)
    if tr:
        return Intent("playback", ch, tr[0], tr[1])
    q = query.lower()
    if any(kw in q for kw in _LIVE_KEYWORDS) or ch is not None:
        return Intent("live", ch)
    if any(kw in q for kw in _PLAYBACK_KEYWORDS) and ch is not None:
        now = datetime.now()
        return Intent("playback", ch, now - timedelta(minutes=5), now - timedelta(minutes=4))
    return Intent("general", ch)


# =============================================================================
# 2. CHAT XOTIRASI (in-memory)
# =============================================================================

@dataclass
class ChatTurn:
    role: str
    content: str
    ts: datetime = field(default_factory=datetime.utcnow)


class ChatMemory:
    def __init__(self, max_turns: int = 12) -> None:
        self._s: Dict[str, Deque[ChatTurn]] = defaultdict(lambda: deque(maxlen=max_turns))
        self._l = threading.Lock()

    def append(self, sid: str, role: str, content: str) -> None:
        with self._l: self._s[sid].append(ChatTurn(role, content))

    def get(self, sid: str, limit: Optional[int] = None) -> List[ChatTurn]:
        with self._l: turns = list(self._s[sid])
        return turns[-limit:] if limit else turns

    def clear(self, sid: str) -> None:
        with self._l: self._s.pop(sid, None)


chat_memory = ChatMemory()


# =============================================================================
# 3. FAOL MODEL HOLATI (frontend header uchun)
# =============================================================================

class ModelStatus:
    def __init__(self) -> None:
        self._l = threading.Lock()
        self._provider: str = "—"      # "Gemini" | "Groq" | "—"
        self._model: str = "kutilmoqda"
        self._at: Optional[datetime] = None

    def set(self, provider: str, model: str) -> None:
        with self._l:
            self._provider = provider
            self._model = model
            self._at = datetime.utcnow()

    def snapshot(self) -> dict:
        with self._l:
            return {
                "provider": self._provider,
                "model": self._model,
                "used_at": self._at.isoformat() if self._at else None,
            }


model_status = ModelStatus()


# =============================================================================
# 4. GEMINI (BIRINCHI) VA GROQ (FALLBACK) PROVIDERLARI
# =============================================================================

class GeminiProvider:
    """Gemini birinchi navbat. Xato (503/429/timeout) bo'lsa 90 s davomida chetlab o'tiladi."""

    COOLDOWN_SECONDS = 90
    TIMEOUT_MS = 25_000

    def __init__(self) -> None:
        self._client = None
        self._models = [settings.GEMINI_MODEL, "gemini-2.5-flash", "gemini-flash-latest"]
        seen = set()
        self._models = [m for m in self._models if m and not (m in seen or seen.add(m))]
        self._skip_until = 0.0

    @property
    def configured(self) -> bool:
        return bool(settings.GEMINI_API_KEY) and settings.GEMINI_API_KEY != "YOUR_GEMINI_API_KEY_HERE"

    @property
    def available(self) -> bool:
        import time as _t
        return self.configured and _t.time() >= self._skip_until

    def _trip(self, err: Exception) -> None:
        import time as _t
        self._skip_until = _t.time() + self.COOLDOWN_SECONDS
        print(f"[Gemini] {str(err)[:90]} — {self.COOLDOWN_SECONDS} s Groq ishlatiladi")

    def _get_client(self):
        if self._client is None and self.configured:
            try:
                from google import genai
                from google.genai import types
                self._client = genai.Client(api_key=settings.GEMINI_API_KEY,
                                            http_options=types.HttpOptions(timeout=self.TIMEOUT_MS))
            except Exception as e:
                print(f"[Gemini] client xato: {e}")
                return None
        return self._client

    def _generate(self, contents) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        cli = self._get_client()
        if cli is None:
            return None, None, "Gemini kaliti sozlanmagan"
        last_err = None
        for m in self._models:
            try:
                resp = cli.models.generate_content(model=m, contents=contents)
                text = (resp.text or "").strip() if resp else ""
                if text:
                    return text, m, None
            except Exception as e:
                last_err = e
                msg = str(e)
                # Server yuklangan / limit / timeout — boshqa Gemini modellari ham odatda ishlamaydi
                if any(k in msg for k in ("503", "429", "UNAVAILABLE", "RESOURCE_EXHAUSTED", "timed out", "Timeout")):
                    break
        if last_err is not None:
            self._trip(last_err)
        return None, None, str(last_err)[:200] if last_err else "Gemini javobsiz"

    def vision(self, prompt: str, images: List[bytes]) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """Qaytaradi: (text, model_used, error). Xato bo'lsa text=None."""
        pil_images = [Image.open(io.BytesIO(b)) for b in images if b]
        return self._generate([*pil_images, prompt])

    def text(self, system: str, history: List[ChatTurn], query: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        hist_lines = []
        for t in history[-6:]:
            role = "Foydalanuvchi" if t.role == "user" else "AI"
            hist_lines.append(f"{role}: {t.content}")
        full = f"{system}\n\n### Suhbat tarixi:\n" + "\n".join(hist_lines) + f"\n\n### Yangi savol:\n{query}"
        return self._generate(full)


class GroqProvider:
    def __init__(self) -> None:
        self._client = None
        self._vision_models = [settings.GROQ_VISION_MODEL, "qwen/qwen3.8-27b", "qwen/qwen3.6-27b"]
        self._text_models = ["openai/gpt-oss-120b", "openai/gpt-oss-20b", "qwen/qwen3.8-27b"]
        seen = set()
        self._vision_models = [m for m in self._vision_models if m and not (m in seen or seen.add(m))]

    @property
    def available(self) -> bool:
        return bool(settings.GROQ_API_KEY) and settings.GROQ_API_KEY.startswith("gsk_")

    def _get_client(self):
        if self._client is None and self.available:
            try:
                from groq import Groq
                self._client = Groq(api_key=settings.GROQ_API_KEY)
            except Exception as e:
                print(f"[Groq] client xato: {e}")
                return None
        return self._client

    @staticmethod
    def _b64(b: bytes) -> str:
        return base64.b64encode(b).decode("ascii")

    def vision(self, system: str, user_text: str, images: List[bytes],
               history: Optional[List[ChatTurn]] = None) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        cli = self._get_client()
        if cli is None:
            return None, None, "Groq kaliti sozlanmagan"
        content = [{"type": "text", "text": user_text}]
        for b in images:
            content.append({"type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{self._b64(b)}"}})
        msgs = [{"role": "system", "content": system}]
        for t in (history or [])[-6:]:
            if t.content:
                msgs.append({"role": "user" if t.role == "user" else "assistant", "content": t.content})
        msgs.append({"role": "user", "content": content})

        last_err = None
        for m in self._vision_models:
            try:
                r = cli.chat.completions.create(model=m, messages=msgs, temperature=0.2, max_tokens=700)
                text = (r.choices[0].message.content or "").strip()
                if text:
                    return text, m, None
            except Exception as e:
                last_err = e
                continue
        return None, None, str(last_err)[:200] if last_err else "Groq javobsiz"

    def text(self, system: str, history: List[ChatTurn], query: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        cli = self._get_client()
        if cli is None:
            return None, None, "Groq kaliti sozlanmagan"
        msgs = [{"role": "system", "content": system}]
        for t in history[-6:]:
            if t.content:
                msgs.append({"role": "user" if t.role == "user" else "assistant", "content": t.content})
        msgs.append({"role": "user", "content": query})
        last_err = None
        for m in self._text_models:
            try:
                r = cli.chat.completions.create(model=m, messages=msgs, temperature=0.4, max_tokens=500)
                text = (r.choices[0].message.content or "").strip()
                if text:
                    return text, m, None
            except Exception as e:
                last_err = e
                continue
        return None, None, str(last_err)[:200] if last_err else "Groq javobsiz"


gemini = GeminiProvider()
groq = GroqProvider()


# =============================================================================
# 5. YUQORI DARAJALI CHAQIRUV — GEMINI → GROQ FALLBACK
# =============================================================================

def _history_msgs(hist: Optional[List[ChatTurn]]) -> List[ChatTurn]:
    return hist or []


def analyze_live(image_bytes: bytes, query: str, camera_name: str,
                 channel: int, history: Optional[List[ChatTurn]] = None,
                 face_context: str = "") -> str:
    """Jonli kadrni tahlil qilish: Gemini birinchi, Groq fallback."""
    system = (
        "Sen 'CCTV AI Assistant' — Hikvision NVR videokuzatuv tizimining aqlli yordamchisisan. "
        "Foydalanuvchiga ayni damda olingan JONLI kamera kadrini tahlil qilib beryapsan. "
        "Faqat kadrda haqiqatan ko'rinib turgan narsalarni bayon qil. "
        "Hech narsani to'qib chiqarma. Faqat o'zbek tilida qisqa, aniq va faktik javob ber."
    )
    if face_context:
        system += (
            "\n\nYuz tanish tizimi natijasi (ishonchli manba, rasmdagi yashil ramkalar shu odamlar): "
            f"{face_context}. Odamlarni tilga olganda ularning ismlarini ishlat. "
            "Qizil ramka — tizim tanimagan odam."
        )
    prompt = f"{system}\n\nKamera: {camera_name} (Kanal #{channel:02d})\nSavol: {query}"

    # 1) Gemini birinchi
    if gemini.available:
        text, model_used, err = gemini.vision(prompt, [image_bytes])
        if text:
            model_status.set("Gemini", model_used)
            return text
        print(f"[live] Gemini xato: {err} — Groq'ga o'tamiz")

    # 2) Groq fallback
    if groq.available:
        text, model_used, err = groq.vision(
            system=system,
            user_text=f"Kamera: **{camera_name}** (Kanal #{channel:02d})\nSavol: {query}",
            images=[image_bytes],
            history=_history_msgs(history),
        )
        if text:
            model_status.set("Groq", model_used)
            return text
        return f"⚠️ Gemini ham Groq ham javob bermadi. Groq xatosi: {err}"

    return "⚠️ Hech qanday AI kaliti sozlanmagan (`.env` da GEMINI_API_KEY yoki GROQ_API_KEY)."


def analyze_playback(frames: List[bytes], query: str, camera_name: str, channel: int,
                     start: datetime, end: datetime,
                     history: Optional[List[ChatTurn]] = None) -> str:
    if not frames:
        return (
            f"⚠️ NVR arxividan {start:%Y-%m-%d %H:%M:%S} — {end:%H:%M:%S} oralig'idagi "
            f"{camera_name} yozuvi olinmadi. Ushbu vaqtda NVR'da yozuv bor-yo'qligini tekshiring."
        )
    system = (
        "Sen 'CCTV AI Assistant'san. Senga NVR HDD arxividan ma'lum vaqt oralig'ida "
        "olingan bir nechta kadr taqdim etilmoqda. Kadrlar orasidagi harakatni, "
        "kim nima qilganini vaqt tartibida qisqa, aniq va faktik o'zbek tilida bayon qil. "
        "Kadrlarda ko'rinmagan narsalarni to'qib chiqarma."
    )
    prompt_head = (
        f"Kamera: {camera_name} (Kanal #{channel:02d})\n"
        f"Oraliq: {start:%Y-%m-%d %H:%M:%S} — {end:%H:%M:%S}\n"
        f"Savol: {query}\n\nQuyida {len(frames)} ta ketma-ket kadr:"
    )
    prompt = f"{system}\n\n{prompt_head}"

    if gemini.available:
        text, model_used, err = gemini.vision(prompt, frames)
        if text:
            model_status.set("Gemini", model_used)
            return text
        print(f"[playback] Gemini xato: {err} — Groq'ga o'tamiz")

    if groq.available:
        text, model_used, err = groq.vision(
            system=system, user_text=prompt_head, images=frames,
            history=_history_msgs(history),
        )
        if text:
            model_status.set("Groq", model_used)
            return text
        return f"⚠️ Gemini ham Groq ham javob bermadi. Groq xatosi: {err}"

    return "⚠️ Hech qanday AI kaliti sozlanmagan."


def analyze_long_range(samples: List[Tuple[datetime, bytes]], query: str,
                        camera_name: str, channel: int,
                        start: datetime, end: datetime,
                        history: Optional[List[ChatTurn]] = None) -> str:
    """Uzoq oraliqdan olingan N ta kadrni AI'ga birgalikda uzatib, sanash xulosasini olamiz."""
    if not samples:
        return (
            f"⚠️ NVR arxividan {start:%Y-%m-%d %H:%M} — {end:%H:%M} oralig'idagi "
            f"{camera_name} yozuvlaridan hech qanday kadr olib bo'lmadi. "
            "Ushbu vaqt oralig'ida NVR HDD'da yozuv borligini tekshiring."
        )

    span_seconds = (end - start).total_seconds()
    step_minutes = int(span_seconds / len(samples) / 60) or 1
    system = (
        "Sen 'CCTV AI Assistant'san. Senga uzun vaqt oralig'idan (bir necha soat) "
        "TARQOQ NAMUNA sifatida olingan bir nechta kadr taqdim etilmoqda. "
        "Har kadr ostida uning aniq vaqti ko'rsatilgan. "
        "Sening vazifang: har kadrda ko'ringan odamlarni sanash, kelib-ketishni farqlash va "
        "umumiy taxminiy hisobot berish. Faqat kadrlarda ko'rinib turgan narsalarni bayon qil. "
        f"MUHIM ESLATMA: bu davomiy video emas, taxminan har {step_minutes} daqiqada 1 ta kadr olingan. "
        "Shu sababli aniq son berishning iloji yo'q — TAXMINIY DIAPAZON bilan javob ber "
        "(masalan: 'kamida 3, taxminan 5-7 kishi'). Javob strukturasi:\n"
        "1) Har bir kadrda ko'ringan odamlar soni (vaqt bilan)\n"
        "2) Umumiy taxmin (min-max diapazon)\n"
        "3) Muhim kuzatuvlar\n"
        "O'zbek tilida yozing."
    )

    header = (
        f"Kamera: **{camera_name}** (Kanal #{channel:02d})\n"
        f"Oraliq: {start:%Y-%m-%d %H:%M} — {end:%H:%M}  ({span_seconds/3600:.1f} soat)\n"
        f"Namuna: {len(samples)} ta kadr (har ~{step_minutes} daqiqada 1 ta)\n"
        f"Savol: {query}"
    )

    frames_only = [b for _, b in samples]

    # 1) GEMINI (birinchi) — Gemini bir nechta rasmni yaxshi qabul qiladi
    if gemini.available:
        pil_images = [Image.open(io.BytesIO(b)) for b in frames_only]
        interleaved: List = [system, header + "\n\nQuyida namuna kadrlar:"]
        for (ts, _), img in zip(samples, pil_images):
            interleaved.append(f"— Kadr [{ts:%H:%M:%S}]:")
            interleaved.append(img)
        text, model_used, err = gemini._generate(interleaved)
        if text:
            model_status.set("Gemini", model_used)
            return text
        print(f"[long_range] Gemini xato: {err} — Groq'ga o'tamiz")

    # 2) GROQ FALLBACK
    if groq.available:
        # Groq'ga birga jo'natamiz — content list orqali
        cli = groq._get_client()
        if cli is not None:
            content: List[dict] = [{"type": "text", "text": header + "\n\nQuyida namuna kadrlar:"}]
            for ts, b in samples:
                content.append({"type": "text", "text": f"— Kadr [{ts:%H:%M:%S}]:"})
                content.append({"type": "image_url",
                                "image_url": {"url": f"data:image/jpeg;base64,{groq._b64(b)}"}})
            msgs = [{"role": "system", "content": system},
                    {"role": "user", "content": content}]
            last_err = None
            for m in groq._vision_models:
                try:
                    r = cli.chat.completions.create(model=m, messages=msgs, temperature=0.2, max_tokens=900)
                    text = (r.choices[0].message.content or "").strip()
                    if text:
                        model_status.set("Groq", m)
                        return text
                except Exception as e:
                    last_err = e
                    continue
            return f"⚠️ Gemini ham Groq ham javob bermadi. Groq xatosi: {last_err}"

    return "⚠️ Hech qanday AI kaliti sozlanmagan."


def general_reply(query: str, history: Optional[List[ChatTurn]] = None) -> str:
    system = (
        "Sen 'CCTV AI Assistant'san — Hikvision NVR videokuzatuv tizimi yordamchisi. "
        "Foydalanuvchi konkret kamera yoki vaqt oralig'ini ko'rsatmadi. "
        "Xushmuomalalik bilan, o'zbek tilida qisqa javob ber va qanday so'rash mumkinligini "
        "misol bilan tavsiya qil (masalan: 'Kamera 2 da hozir kim bor?', "
        "'Bugun soat 14:30 da 6-kamerada nima bo'ldi?')."
    )
    hist = _history_msgs(history)

    if gemini.available:
        text, model_used, err = gemini.text(system, hist, query)
        if text:
            model_status.set("Gemini", model_used)
            return text
        print(f"[general] Gemini xato: {err} — Groq'ga o'tamiz")

    if groq.available:
        text, model_used, err = groq.text(system, hist, query)
        if text:
            model_status.set("Groq", model_used)
            return text
        return f"⚠️ Gemini ham Groq ham javob bermadi. Groq xatosi: {err}"

    return "⚠️ Hech qanday AI kaliti sozlanmagan."


def staff_answer(query: str, facts: dict, history: Optional[List[ChatTurn]] = None) -> Optional[str]:
    """
    Davomat/effektivlik savollariga faqat berilgan faktlar asosida javob.
    AI ishlamasa None qaytaradi (chaqiruvchi deterministik matn ishlatadi).
    """
    import json

    system = (
        "Sen ofis xodimlari davomati va ish samaradorligi bo'yicha AI yordamchisan. "
        "Quyidagi JSON — kameralar va yuz tanish tizimidan olingan ANIQ FAKTLAR. "
        "Faqat shu faktlar asosida o'zbek tilida qisqa, aniq javob ber; raqam va vaqtlarni o'zgartirma, "
        "yo'q ma'lumotni to'qima. Vaqtlarni HH:MM ko'rinishida yoz. "
        "Maydonlar: arrived=kelgan vaqt, left=ketgan vaqt, late_minutes=kechikish (daq), "
        "early_minutes=erta ketish (daq), office_minutes=ofisda bo'lgan vaqt, "
        "desk_minutes=biriktirilgan xona yoki joyda ishlagan vaqt, confirmed_minutes=shundan yuz bilan tasdiqlangani, away_minutes=ish joyidan uzoqda, efficiency=ish joyida/ofisda %. "
        "efficiency null bo'lsa — bu xodimga ish joyi biriktirilmagan yoki kuzatilmagan. "
        "arrived_approx=true bo'lsa kelish vaqti ish joyi kamerasidan taxminiy. "
        "coverage — kamera kuzatuvi so'ralgan vaqtning qancha qismini qamragani (1.0 = to'liq); "
        "1.0 dan past bo'lsa buni javobda eslat.\n\n"
        f"FAKTLAR:\n{json.dumps(facts, ensure_ascii=False, default=str)[:60000]}"
    )
    hist = _history_msgs(history)
    if gemini.available:
        text, model_used, _ = gemini.text(system, hist, query)
        if text:
            model_status.set("Gemini", model_used)
            return text
    if groq.available:
        text, model_used, _ = groq.text(system, hist, query)
        if text:
            model_status.set("Groq", model_used)
            return text
    return None


# =============================================================================
# 6. TUZILGAN (JSON) VISION SO'ROVLARI — semantik indeks
# =============================================================================

def build_collage(tiles: List[Tuple[str, bytes]], tile_w: int = 480, cols: int = 3) -> Optional[bytes]:
    """Bir nechta kadrni yorliqli setkaga yig'adi — bitta AI so'rovida ko'p kamera."""
    import cv2
    import numpy as np

    imgs = []
    for label, jpg in tiles:
        img = cv2.imdecode(np.frombuffer(jpg, np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            continue
        h = int(tile_w * img.shape[0] / img.shape[1])
        img = cv2.resize(img, (tile_w, h))
        cv2.rectangle(img, (0, 0), (150, 34), (0, 0, 0), -1)
        cv2.putText(img, label, (8, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
        imgs.append(img)
    if not imgs:
        return None
    th = max(i.shape[0] for i in imgs)
    imgs = [cv2.copyMakeBorder(i, 0, th - i.shape[0], 0, 0, cv2.BORDER_CONSTANT) for i in imgs]
    cols = min(cols, len(imgs))
    while len(imgs) % cols:
        imgs.append(np.zeros_like(imgs[0]))
    rows = [np.hstack(imgs[r * cols:(r + 1) * cols]) for r in range(len(imgs) // cols)]
    ok, buf = cv2.imencode(".jpg", np.vstack(rows), [cv2.IMWRITE_JPEG_QUALITY, 82])
    return buf.tobytes() if ok else None


def _parse_json(text: str):
    import json as _json
    m = re.search(r"```(?:json)?\s*(.+?)```", text, re.S)
    raw = m.group(1) if m else text
    start = min([i for i in (raw.find("["), raw.find("{")) if i >= 0], default=-1)
    if start < 0:
        return None
    for end in range(len(raw), start, -1):
        try:
            return _json.loads(raw[start:end])
        except ValueError:
            continue
    return None


def vision_json(prompt: str, images: List[bytes]):
    """Vision modeldan JSON javob oladi (Gemini → Groq). Muvaffaqiyatsiz bo'lsa None."""
    full = prompt + "\n\nFaqat to'g'ri JSON qaytar, boshqa matn yozma."
    if gemini.available:
        text, model_used, _ = gemini.vision(full, images)
        if text:
            data = _parse_json(text)
            if data is not None:
                model_status.set("Gemini", model_used)
                return data
    if groq.available:
        text, model_used, _ = groq.vision(system="Sen kamera kadrlarini tahlil qiluvchi tizimsan. Faqat JSON qaytarasan.",
                                          user_text=full, images=images)
        if text:
            data = _parse_json(text)
            if data is not None:
                model_status.set("Groq", model_used)
                return data
    return None


def text_reply(system: str, query: str) -> Optional[str]:
    """Kontekstsiz matnli javob (Gemini → Groq)."""
    if gemini.available:
        text, m, _ = gemini.text(system, [], query)
        if text:
            model_status.set("Gemini", m)
            return text
    if groq.available:
        text, m, _ = groq.text(system, [], query)
        if text:
            model_status.set("Groq", m)
            return text
    return None
