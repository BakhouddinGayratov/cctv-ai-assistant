"""
Bosqich 5.4 — semantik video qidiruv.

Indeks: har N daqiqada barcha kameralardan kadr → 9 tadan kollaj → AI har katak uchun qisqa tavsif + teglar.
Qidiruv: so'rov → sana/kamera filtri → kalit so'z bo'yicha nomzodlar (indeks + ogohlantirishlar)
        → AI eng mos lahzalarni tanlaydi va tushuntiradi.
"""

from __future__ import annotations

import json
import re
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from typing import List, Optional, Tuple

from sqlmodel import select

from config import settings
from database import Alert, FrameIndex, get_session
from face_engine import decode_jpeg, encode_jpeg
from rtsp_manager import capture_snapshot, nvr_online

INDEX_DIR = settings.DATA_DIR / "index"
TAGS = ["odam", "ko'p_odam", "mashina", "eshik_ochiq", "eshik_yopiq", "darvoza_ochiq", "chiroq_yoniq", "qorong'i",
        "bo'sh", "tartibsizlik", "yuk", "hayvon", "kompyuter_oldida", "uchrashuv"]
_lock = threading.Lock()


def _rel(p) -> str:
    return p.relative_to(settings.DATA_DIR).as_posix()


def index_once(channels: Optional[List[int]] = None) -> int:
    """Barcha (yoki berilgan) kameralarni bir marta indekslaydi. Qaytaradi: yozilgan qatorlar soni."""
    from ai_service import build_collage, vision_json

    if not nvr_online() or not _lock.acquire(blocking=False):
        return 0
    try:
        channels = channels or settings.channel_ids
        now = datetime.now()
        with ThreadPoolExecutor(max_workers=4) as pool:
            shots = list(pool.map(lambda ch: (ch, capture_snapshot(ch, max_attempts=1)), channels))
        shots = [(ch, j) for ch, j in shots if j]
        written = 0
        day_dir = INDEX_DIR / now.strftime("%Y-%m-%d")
        day_dir.mkdir(parents=True, exist_ok=True)
        for i in range(0, len(shots), 9):
            group = shots[i:i + 9]
            collage = build_collage([(f"CH-{ch:02d}", j) for ch, j in group], cols=3)
            if not collage:
                continue
            prompt = (
                "Kollajdagi har bir xavfsizlik kamerasi kadrini (chap yuqorida CH-XX yorlig'i) tavsifla. "
                "Har katak uchun: nima ko'rinyapti, nechta odam, eshik/darvoza ochiqmi, chiroq yoniqmi, g'ayrioddiy narsa. "
                f"Teglarni faqat shu ro'yxatdan tanla: {', '.join(TAGS)}. "
                'Javob: [{"ch": raqam, "description": "1 gap o\'zbekcha", "tags": ["..."]}]'
            )
            data = vision_json(prompt, [collage])
            if not isinstance(data, list):
                continue
            by_ch = {ch: j for ch, j in group}
            rows = []
            for item in data:
                try:
                    ch = int(item.get("ch"))
                except (TypeError, ValueError):
                    continue
                if ch not in by_ch:
                    continue
                img = decode_jpeg(by_ch[ch])
                p = day_dir / f"ch{ch:02d}_{now:%H%M}_{uuid.uuid4().hex[:4]}.jpg"
                p.write_bytes(encode_jpeg(img, 75, max_side=640) if img is not None else by_ch[ch])
                tags = [t for t in (item.get("tags") or []) if t in TAGS]
                rows.append(FrameIndex(ts=now, date=now.strftime("%Y-%m-%d"), channel=ch, image_path=_rel(p),
                                       description=str(item.get("description", ""))[:400], tags=",".join(tags)))
            if rows:
                with get_session() as s:
                    s.add_all(rows)
                    s.commit()
                written += len(rows)
        return written
    finally:
        _lock.release()


# ----------------------------------------------------------------------------- qidiruv
_SYN = {
    "eshik": ["eshik", "eshik_ochiq", "eshik_yopiq"], "ochiq": ["ochiq", "eshik_ochiq", "darvoza_ochiq"],
    "darvoza": ["darvoza", "darvoza_ochiq"], "mashina": ["mashina", "avtomobil"], "odam": ["odam", "kishi", "ko'p_odam"],
    "chiroq": ["chiroq", "chiroq_yoniq"], "qorong'i": ["qorong'i", "tun"],
    "yuk": ["yuk", "quti"], "tartibsiz": ["tartibsizlik"], "uchrashuv": ["uchrashuv", "majlis"],
}
_WORD = re.compile(r"[a-zа-яё'ʻ’]+")


def _tokens(text: str) -> List[str]:
    t = text.lower().replace("’", "'").replace("ʻ", "'")
    return [w for w in _WORD.findall(t) if len(w) >= 3]


def _expand(tokens: List[str]) -> List[str]:
    out = set()
    for tok in tokens:
        out.add(tok[:5])
        for k, vals in _SYN.items():
            if tok.startswith(k[:4]):
                out.update(v[:5] for v in vals)
    return list(out)


def search(query: str, days: List[str], channel: Optional[int] = None, limit: int = 8) -> Tuple[str, List[dict]]:
    from ai_service import text_reply

    with get_session() as s:
        q = select(FrameIndex).where(FrameIndex.date.in_(days))
        a = select(Alert).where(Alert.date.in_(days), Alert.kind.in_(["after_hours", "unknown_face", "camera_offline"]))
        if channel:
            q, a = q.where(FrameIndex.channel == channel), a.where(Alert.channel == channel)
        frames = s.exec(q).all()
        alerts = s.exec(a).all()
    cands = [{"id": f"f{f.id}", "ts": f.ts, "channel": f.channel, "text": f"{f.description} [{f.tags}]",
              "image": f"/media/{f.image_path}"} for f in frames]
    cands += [{"id": f"a{x.id}", "ts": x.ts, "channel": x.channel, "text": f"OGOHLANTIRISH: {x.title}. {x.message}",
               "image": f"/media/{x.snapshot_path}" if x.snapshot_path else None} for x in alerts]
    if not cands:
        return ("Bu davr uchun indekslangan kadrlar yo'q. Indeks har 15 daqiqada to'planadi (NVR ulangan bo'lishi kerak).", [])

    keys = _expand(_tokens(query))
    for c in cands:
        hay = c["text"].lower()
        c["score"] = sum(1 for k in keys if k and k in hay) + (0.5 if c["id"].startswith("a") else 0)
    pool = sorted([c for c in cands if c["score"] > 0], key=lambda c: (-c["score"], c["ts"]))[:60] or \
        sorted(cands, key=lambda c: c["ts"], reverse=True)[:40]

    listing = "\n".join(f"{c['id']} | {c['ts']:%Y-%m-%d %H:%M} | CH-{c['channel']:02d} | {c['text'][:160]}" for c in pool)
    system = (
        "Sen video arxiv qidiruv yordamchisisan. Quyida kameralar kadrlari tavsiflari va ogohlantirishlar ro'yxati. "
        "Foydalanuvchi savoliga mos keladiganlarini tanla. Javob JSON: "
        '{"answer": "o\'zbekcha 2-4 gaplik javob (vaqtlar bilan)", "ids": ["f12", "a3", ...]} — eng ko\'pi 8 ta id, '
        "faqat haqiqatan mos keladiganlarini. Mos topilmasa ids bo'sh."
    )
    raw = text_reply(system, f"SAVOL: {query}\n\nRO'YXAT:\n{listing}")
    answer, ids = "", []
    if raw:
        m = re.search(r"\{.*\}", raw, re.S)
        try:
            data = json.loads(m.group(0)) if m else {}
            answer, ids = str(data.get("answer", "")), [str(i) for i in data.get("ids", [])]
        except ValueError:
            answer = raw
    by_id = {c["id"]: c for c in pool}
    hits = [by_id[i] for i in ids if i in by_id][:limit]
    if not answer:
        hits = pool[:limit] if pool[0]["score"] > 0 else []
        answer = f"{len(hits)} ta mos lahza topildi." if hits else "Mos lahza topilmadi."
    return answer, [{"ts": h["ts"].isoformat(timespec="minutes"), "channel": h["channel"], "text": h["text"],
                     "image": h["image"]} for h in hits]


def cleanup(days_keep: int = 30) -> None:
    cutoff = (datetime.now() - timedelta(days=days_keep)).strftime("%Y-%m-%d")
    with get_session() as s:
        for r in s.exec(select(FrameIndex).where(FrameIndex.date < cutoff)).all():
            (settings.DATA_DIR / r.image_path).unlink(missing_ok=True)
            s.delete(r)
        s.commit()
