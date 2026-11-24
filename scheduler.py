"""Davriy vazifalar: agent (10 daq), indeks (N daq), kunlik xulosa, haftalik hisobot, tozalash."""

from __future__ import annotations

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from settings_store import store

sched = BackgroundScheduler(timezone="Asia/Tashkent", job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": 600})


def _safe(fn, name: str):
    def run():
        try:
            fn()
        except Exception as e:
            print(f"[scheduler] {name} xatosi: {e}")
    return run


def _daily():
    if store.get("daily_summary"):
        from agent import daily_summary
        daily_summary()


def _weekly():
    if store.get("weekly_report"):
        from agent import weekly_report
        weekly_report()


def _agent():
    from agent import run_agent_checks
    run_agent_checks()


def _index():
    if store.get("indexer_enabled"):
        from indexer import index_once
        index_once()


def _cleanup():
    from indexer import cleanup
    cleanup()


def apply_schedule() -> None:
    """Sozlamalar o'zgarganda vaqtlarni qayta o'rnatadi."""
    h, m = (int(x) for x in str(store.get("daily_summary_time") or "19:00").split(":")[:2])
    sched.add_job(_safe(_daily, "kunlik xulosa"), CronTrigger(hour=h, minute=m), id="daily", replace_existing=True)
    sched.add_job(_safe(_weekly, "haftalik hisobot"), CronTrigger(day_of_week="mon", hour=8, minute=0), id="weekly", replace_existing=True)
    sched.add_job(_safe(_agent, "agent"), IntervalTrigger(minutes=10), id="agent", replace_existing=True)
    sched.add_job(_safe(_index, "indeks"), IntervalTrigger(minutes=max(5, int(store.get("indexer_interval_min")))),
                  id="index", replace_existing=True)
    sched.add_job(_safe(_cleanup, "tozalash"), CronTrigger(hour=3, minute=30), id="cleanup", replace_existing=True)


def start() -> None:
    apply_schedule()
    if not sched.running:
        sched.start()


def jobs_info() -> list:
    return [{"id": j.id, "next_run": j.next_run_time.isoformat(timespec="minutes") if j.next_run_time else None}
            for j in sched.get_jobs()]
