"""SQLite ma'lumotlar bazasi: xodimlar, yuz namunalari, ko'rinishlar, ish stoli, qamrov."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Column, LargeBinary, event
from sqlmodel import Field, Session, SQLModel, create_engine

from config import settings


class Employee(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    first_name: str
    last_name: str = ""
    position: str = ""
    phone: str = ""
    work_start: str = Field(default_factory=lambda: settings.DEFAULT_WORK_START)
    work_end: str = Field(default_factory=lambda: settings.DEFAULT_WORK_END)
    active: bool = True
    desk_channel: Optional[int] = None
    desk_zone: Optional[str] = None  # "x1,y1,x2,y2" (0..1 nisbiy koordinatalar)
    room_id: Optional[int] = None    # o'z xonasi (ofis xaritasidan)
    created_at: datetime = Field(default_factory=datetime.now)

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()


class FaceSample(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    employee_id: int = Field(foreign_key="employee.id", index=True)
    embedding: bytes = Field(sa_column=Column(LargeBinary, nullable=False))
    image_path: str = ""   # data/ ichidagi nisbiy yo'l
    source: str = "upload"  # upload | camera | sighting
    created_at: datetime = Field(default_factory=datetime.now)


class Sighting(SQLModel, table=True):
    """Kirish kamerasida yuz ko'rinishi (tanilgan yoki notanish)."""
    id: Optional[int] = Field(default=None, primary_key=True)
    ts: datetime = Field(index=True)
    date: str = Field(index=True)  # YYYY-MM-DD
    channel: int = Field(index=True)
    employee_id: Optional[int] = Field(default=None, index=True)
    similarity: float = 0.0
    face_path: str = ""
    frame_path: str = ""
    embedding: bytes = Field(sa_column=Column(LargeBinary, nullable=False))


class DeskSample(SQLModel, table=True):
    """Ish stoli tekshiruvi: xodim o'z joyida bormi."""
    id: Optional[int] = Field(default=None, primary_key=True)
    ts: datetime = Field(index=True)
    date: str = Field(index=True)
    channel: int
    employee_id: int = Field(index=True)
    present: bool
    method: str = "face"  # face | zone
    interval_seconds: int = 300


class Coverage(SQLModel, table=True):
    """Kamera kuzatuvi qaysi vaqtlarda uzluksiz ishlagani (javoblar ishonchliligi uchun)."""
    id: Optional[int] = Field(default=None, primary_key=True)
    channel: int = Field(index=True)
    date: str = Field(index=True)
    start_ts: datetime
    end_ts: datetime


class Setting(SQLModel, table=True):
    """UI'dan o'zgartiriladigan sozlamalar (kalit → JSON qiymat)."""
    key: str = Field(primary_key=True)
    value: str


class Alert(SQLModel, table=True):
    """Ogohlantirishlar va agent xabarlari (Bosqich 2 va 5)."""
    id: Optional[int] = Field(default=None, primary_key=True)
    ts: datetime = Field(index=True)
    date: str = Field(index=True)
    kind: str = Field(index=True)       # unknown_face | after_hours | camera_offline | agent | daily_summary | arrival
    severity: str = "info"              # info | warning | critical
    channel: Optional[int] = None
    employee_id: Optional[int] = None
    title: str
    message: str = ""
    snapshot_path: str = ""
    clip_path: str = ""
    acknowledged: bool = False
    notified: bool = False


class ActivityMinute(SQLModel, table=True):
    """Kamera faolligi daqiqa bo'yicha (kun chizig'i va issiqlik xaritasi uchun)."""
    id: Optional[int] = Field(default=None, primary_key=True)
    channel: int = Field(index=True)
    date: str = Field(index=True)
    minute: int                          # 0..1439
    motion: float = 0.0                  # 0..1
    people: int = 0


class FrameIndex(SQLModel, table=True):
    """Semantik qidiruv uchun kadr tavsiflari (Bosqich 5.4)."""
    id: Optional[int] = Field(default=None, primary_key=True)
    ts: datetime = Field(index=True)
    date: str = Field(index=True)
    channel: int = Field(index=True)
    image_path: str
    description: str = ""
    tags: str = ""                        # vergul bilan: eshik_ochiq, odam, mashina, ...


DB_PATH = settings.DATA_DIR / "cctv.db"
engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})


@event.listens_for(engine, "connect")
def _sqlite_pragmas(dbapi_conn, _):
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA busy_timeout=5000")
    cur.close()


class Room(SQLModel, table=True):
    """Ofis xaritasi: xona, uni ko'radigan kameralar va eshik orqali tutash xonalar."""
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    kind: str = "work"        # work | meeting | rest | corridor | yard | blind
    channels: str = ""        # "4,5"
    neighbors: str = ""       # tutash xonalar id: "2,7"


class PresenceSample(SQLModel, table=True):
    """Har daqiqada xodim qayerda (presence.py)."""
    id: Optional[int] = Field(default=None, primary_key=True)
    ts: datetime = Field(index=True)
    date: str = Field(index=True)
    employee_id: int = Field(index=True)
    place: str                # xona id | out | away | unknown
    conf: str = "seen"        # seen | inferred | unknown
    interval_seconds: int = 60


class AwayPeriod(SQLModel, table=True):
    """Ofisdan tashqarida ish (mijoz, bank, xizmat safari) — rahbar belgilaydi."""
    id: Optional[int] = Field(default=None, primary_key=True)
    employee_id: int = Field(index=True)
    date: str = Field(index=True)
    start: str                # HH:MM
    end: str
    reason: str = ""


def init_db() -> None:
    SQLModel.metadata.create_all(engine)
    with engine.begin() as conn:  # create_all mavjud jadvalga ustun qo'shmaydi
        cols = {r[1] for r in conn.exec_driver_sql("PRAGMA table_info(employee)")}
        if "room_id" not in cols:
            conn.exec_driver_sql("ALTER TABLE employee ADD COLUMN room_id INTEGER")


def get_session() -> Session:
    return Session(engine, expire_on_commit=False)
