"""Bosqich 3 — sana oralig'i bo'yicha analitika (davomat, samaradorlik, kamera faolligi, ogohlantirishlar)."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from typing import Dict, List

from sqlmodel import func, select

from config import settings
from database import ActivityMinute, Alert, Sighting, get_session
import staff_service


def day_range(start: str, end: str) -> List[str]:
    d0, d1 = date.fromisoformat(start), date.fromisoformat(end)
    if d1 < d0:
        d0, d1 = d1, d0
    d1 = min(d1, date.today())
    n = min(92, (d1 - d0).days + 1)
    return [(d0 + timedelta(days=i)).isoformat() for i in range(n)]


def build(start: str, end: str) -> dict:
    days = day_range(start, end)
    per_day = []
    per_emp: Dict[int, dict] = {}
    arrival_hours: Counter = Counter()
    for d in days:
        rep = staff_service.daily_attendance(d)
        effs = [e["efficiency"] for e in rep["employees"] if e["efficiency"] is not None]
        per_day.append({
            "date": d, **rep["summary"],
            "avg_efficiency": round(sum(effs) / len(effs)) if effs else None,
            "workday": datetime.fromisoformat(d).weekday() in settings.work_days,
        })
        for e in rep["employees"]:
            agg = per_emp.setdefault(e["id"], {
                "id": e["id"], "name": e["name"], "position": e["position"], "days_present": 0, "late_days": 0,
                "late_minutes": 0, "early_days": 0, "office_minutes": 0, "desk_minutes": 0, "eff_values": [],
                "arrivals": [],
            })
            if e["arrived"]:
                agg["days_present"] += 1
                hh = int(e["arrived"][11:13]) + int(e["arrived"][14:16]) / 60
                agg["arrivals"].append(hh)
                arrival_hours[int(hh)] += 1
            if e["late_minutes"]:
                agg["late_days"] += 1
                agg["late_minutes"] += e["late_minutes"]
            if e["early_minutes"]:
                agg["early_days"] += 1
            agg["office_minutes"] += e["office_minutes"]
            agg["desk_minutes"] += e["desk_minutes"]
            if e["efficiency"] is not None:
                agg["eff_values"].append(e["efficiency"])

    employees = []
    for a in per_emp.values():
        effs = a.pop("eff_values")
        arr = a.pop("arrivals")
        avg_arr = sum(arr) / len(arr) if arr else None
        employees.append({
            **a,
            "office_hours": round(a["office_minutes"] / 60, 1),
            "desk_hours": round(a["desk_minutes"] / 60, 1),
            "avg_efficiency": round(sum(effs) / len(effs)) if effs else None,
            "avg_arrival": f"{int(avg_arr):02d}:{int((avg_arr % 1) * 60):02d}" if avg_arr is not None else None,
        })
    employees.sort(key=lambda x: -x["office_minutes"])

    with get_session() as s:
        sight = s.exec(select(Sighting.channel, func.count()).where(Sighting.date.in_(days)).group_by(Sighting.channel)).all()
        act = s.exec(select(ActivityMinute.channel, func.count(), func.avg(ActivityMinute.motion))
                     .where(ActivityMinute.date.in_(days)).group_by(ActivityMinute.channel)).all()
        alerts = s.exec(select(Alert.kind, func.count()).where(Alert.date.in_(days)).group_by(Alert.kind)).all()
        act_hours = s.exec(select(ActivityMinute.minute).where(ActivityMinute.date.in_(days))).all()

    cams = defaultdict(lambda: {"sightings": 0, "active_minutes": 0, "avg_motion": 0.0})
    for ch, n in sight:
        cams[ch]["sightings"] = n
    for ch, n, avg in act:
        cams[ch]["active_minutes"] = n
        cams[ch]["avg_motion"] = round(float(avg or 0), 4)
    hourly_activity = Counter(m // 60 for m in act_hours)

    return {
        "from": days[0] if days else start,
        "to": days[-1] if days else end,
        "days": per_day,
        "employees": employees,
        "arrival_histogram": [{"hour": h, "count": arrival_hours.get(h, 0)} for h in range(6, 13)],
        "hourly_activity": [{"hour": h, "minutes": hourly_activity.get(h, 0)} for h in range(24)],
        "cameras": [{"channel": ch, "name": settings.get_camera(ch)["name"], **v} for ch, v in sorted(cams.items())],
        "alerts": {k: n for k, n in alerts},
        "totals": {
            "workdays": sum(1 for d in per_day if d["workday"]),
            "attendance_rate": round(100 * sum(d["present"] for d in per_day if d["workday"]) /
                                     max(1, sum(d["total_employees"] for d in per_day if d["workday"]))),
            "late_total": sum(d["late"] for d in per_day),
            "office_hours": round(sum(d["total_office_hours"] for d in per_day), 1),
            "unknown_faces": sum(d["unknown_faces"] for d in per_day),
        },
    }
