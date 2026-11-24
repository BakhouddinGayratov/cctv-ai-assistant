"""
Bosqich 5.1 — doimiy kuzatuv agenti + Bosqich 3.3/3.4 avtomatik hisobotlar.

Agent (har 10 daqiqada):
- Ofisda bo'lib, N daqiqadan beri ish stolida yo'q xodim → xabar.
- Ish boshlanishidan 30 daqiqa o'tib, hali kelmaganlar ro'yxati (kuniga bir marta).
- So'nggi soatda notanish yuzlar ko'payib ketsa → xabar.
Kunlik xulosa — belgilangan vaqtda AI kunni tahlil qiladi (chat + Telegram).
Haftalik hisobot — dushanba 08:00 Excel + PDF Telegram'ga.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from typing import List

from sqlmodel import select

from alerts import bus
from config import settings
from database import Alert, DeskSample, Sighting, get_session
from settings_store import store
import staff_service

REPORTS_DIR = settings.DATA_DIR / "reports"


def _already(kind: str, key: str, day: str) -> bool:
    with get_session() as s:
        return s.exec(select(Alert).where(Alert.date == day, Alert.kind == kind, Alert.message.contains(key))).first() is not None


def run_agent_checks() -> List[str]:
    if not store.get("agent_enabled"):
        return []
    now = datetime.now()
    if now.weekday() not in settings.work_days:
        return []
    day = now.date().isoformat()
    rep = staff_service.daily_attendance(day)
    made: List[str] = []

    # 1) Ish stolidan uzoq vaqt yo'q
    away_min = int(store.get("agent_away_minutes"))
    with get_session() as s:
        desk = s.exec(select(DeskSample).where(DeskSample.date == day).order_by(DeskSample.ts)).all()
    by_emp = {}
    for d in desk:
        by_emp.setdefault(d.employee_id, []).append(d)
    for e in rep["employees"]:
        samples = by_emp.get(e["id"], [])
        if e["status"] != "ofisda" or not any(d.present for d in samples):
            continue  # bugun umuman ko'rinmagan bo'lsa, kamera uni ko'ra olmayotgan bo'lishi mumkin
        streak = 0
        for d in reversed(samples):
            if d.present:
                break
            streak += d.interval_seconds // 60
        if streak >= away_min and bus.allow(f"away-{e['id']}", 120):
            msg = f"{e['name']} {streak} daqiqadan beri ish joyida ko'rinmayapti (ofisda deb hisoblanadi). Tekshirish kerakmi?"
            bus.create("agent", f"{e['name']} ish joyida yo'q", msg, severity="info", employee_id=e["id"])
            made.append(msg)

    # 2) Hali kelmaganlar (ish boshlanishidan 30 daqiqa keyin, kuniga bir marta)
    missing = []
    for e in rep["employees"]:
        start = datetime.combine(now.date(), settings.parse_hhmm(e["work_start"])) + timedelta(minutes=30)
        if e["status"] == "kelmagan" and now >= start:
            missing.append(e["name"])
    if missing and not _already("agent", "Hali kelmaganlar", day) and now.hour < 13:
        msg = "Hali kelmaganlar: " + ", ".join(missing)
        bus.create("agent", f"{len(missing)} xodim hali kelmagan", msg, severity="warning")
        made.append(msg)

    # 3) Notanish yuzlar ko'payishi
    with get_session() as s:
        n_unknown = len(s.exec(select(Sighting).where(Sighting.ts >= now - timedelta(hours=1), Sighting.employee_id == None)).all())  # noqa: E711
    if n_unknown >= 6 and bus.allow("unknown-surge", 120):
        msg = f"So'nggi 1 soatda {n_unknown} ta notanish yuz qayd etildi. Mehmonlar bo'lsa — e'tibor bermang, aks holda tekshiring."
        bus.create("unknown_face", "Notanish yuzlar ko'paydi", msg, severity="warning", notify=False)  # faqat saytda
        made.append(msg)
    return made


def daily_summary(day: str | None = None, notify: bool = True) -> Alert:
    from ai_service import text_reply

    day = day or date.today().isoformat()
    facts = staff_service.attendance_facts(staff_service.StaffQuery("attendance", [], [day]))
    with get_session() as s:
        alerts = s.exec(select(Alert).where(Alert.date == day, Alert.kind.in_(["unknown_face", "after_hours", "camera_offline"]))).all()
    facts["alerts"] = [{"time": a.ts.strftime("%H:%M"), "kind": a.kind, "title": a.title, "channel": a.channel} for a in alerts]
    system = (
        "Sen ofis rahbari uchun kunlik hisobot yozadigan AI yordamchisan. Berilgan JSON faktlar asosida o'zbek tilida "
        "5–8 gaplik qisqa, aniq xulosa yoz: nechta xodim keldi, kim kechikdi (necha daqiqa), kim erta ketdi, "
        "samaradorlik (eng yuqori/past), muhim ogohlantirishlar. Raqamlarni o'zgartirma, to'qima. "
        "Oxirida bitta qisqa tavsiya ber."
    )
    text = text_reply(system, json.dumps(facts, ensure_ascii=False, default=str)[:50000])
    if not text:
        text = staff_service.attendance_text(facts)
        if alerts:
            text += f"\nOgohlantirishlar: {len(alerts)} ta."
    return bus.create("daily_summary", f"Kunlik xulosa — {day}", text, severity="info", notify=notify)


def weekly_report(send: bool = True) -> dict:
    from reports import build_excel, build_pdf
    from telegram_notifier import configured, send_document

    today = date.today()
    end = today - timedelta(days=today.weekday() + 1)      # o'tgan yakshanba
    start = end - timedelta(days=6)                       # o'tgan dushanba
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    xlsx = REPORTS_DIR / f"davomat_{start}_{end}.xlsx"
    pdf = REPORTS_DIR / f"davomat_{start}_{end}.pdf"
    xlsx.write_bytes(build_excel(start.isoformat(), end.isoformat()))
    pdf.write_bytes(build_pdf(start.isoformat(), end.isoformat()))
    if send and configured():
        send_document(pdf, f"📊 Haftalik davomat hisoboti: {start} — {end}")
        send_document(xlsx, "Excel versiyasi")
    return {"xlsx": xlsx.name, "pdf": pdf.name, "from": start.isoformat(), "to": end.isoformat()}
