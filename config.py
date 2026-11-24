"""Loyiha sozlamalari (CCTV AI Assistant)."""

from datetime import datetime, time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # --- Google Gemini (BIRINCHI navbat) ---
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.5-flash"

    # --- Groq Cloud (FALLBACK) ---
    GROQ_API_KEY: str = ""
    GROQ_VISION_MODEL: str = "qwen/qwen3.8-27b"

    # --- Hikvision NVR ---
    NVR_IP: str = "192.168.0.150"
    NVR_PORT: int = 554
    NVR_USER: str = "admin"
    NVR_PASSWORD: str = ""  # .env da
    NVR_HTTP_PORT: int = 80              # ISAPI (yozuvlar qidiruvi, PTZ)
    ADMIN_PASSWORD: str = ""
    BOSS_PASSWORD: str = ""
    AUTH_SECRET: str = ""
    BOT_API_KEY: str = ""
    CHANNELS_COUNT: int = 18
    EXCLUDED_CAMERAS: str = "15"          # NVR kanali bor, lekin tizimda ishlatilmaydi

    # --- Server ---
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    BASE_DIR: Path = Path(__file__).resolve().parent

    # --- Yuz tanish (OpenCV YuNet + SFace) ---
    FACE_MATCH_THRESHOLD: float = 0.35   # cosine, ArcFace; ofis kameralari kesimlarida o'lchangan
    FACE_MODEL: str = "arcface"          # arcface (InsightFace, faqat test uchun) | sface
    FACE_STRONG_MATCH: float = 0.45      # bundan past moslik ikkinchi kadr bilan tasdiqlanadi
    FACE_CONFIRM_SECONDS: float = 12.0   # ikkinchi kadr shu vaqt ichida kelishi kerak
    FACE_MATCH_MARGIN: float = 0.05      # eng yaqin ikki xodim orasidagi farq bundan kichik bo'lsa — aniq emas
    FACE_MIN_SIZE: int = 36              # px — bundan kichik yuzlar tanishga yaroqsiz
    FACE_DETECT_SCORE: float = 0.80
    YOLO_MODEL_PATH: str = ""            # bo'sh bo'lsa ../yolov8n.pt ishlatiladi (ish stoli zonalari uchun)

    # --- Davomat (kirish kameralari) ---
    ATTENDANCE_ENABLED: bool = True
    STREET_CAMERAS: str = "1,3,6,7,11,17,18"            # ko'chadagi kameralar: faqat xodimlar taniladi, notanishlar yozilmaydi
    ATTENDANCE_CAMERAS: str = "3,2"      # tartib: tashqi → ichki (yo'nalishni aniqlash uchun)
    ATTENDANCE_PROCESS_FPS: float = 2.0
    ATTENDANCE_USE_MAIN_STREAM: bool = True
    MONITOR_START: str = "07:30"
    MONITOR_END: str = "20:00"
    WORK_DAYS: str = "0,1,2,3,4,5"       # 0=Dushanba ... 6=Yakshanba
    DEFAULT_WORK_START: str = "09:00"
    DEFAULT_WORK_END: str = "18:00"
    LATE_GRACE_MINUTES: int = 10
    SIGHTING_COOLDOWN_SECONDS: int = 90
    PASSAGE_WINDOW_MINUTES: int = 3      # bir o'tishga tegishli ko'rinishlar oynasi
    SIGHTING_RETENTION_DAYS: int = 60

    # --- Ish stoli (effektivlik) ---
    DESK_ENABLED: bool = True
    DESK_CAMERAS: str = "5"
    DESK_INTERVAL_SECONDS: int = 60
    SEAT_CHANGE_PERCENT: float = 3.5     # ketma-ket tekshiruvlar orasida joydagi o'zgarish (orqasi o'girilgan odam uchun)
    SEAT_HOLD_CHECKS: int = 3            # oxirgi harakatdan keyin shuncha tekshiruv "joyida" deb hisoblanadi

    @property
    def channel_ids(self) -> List[int]:
        excluded = self._int_list(self.EXCLUDED_CAMERAS)
        return [ch for ch in range(1, self.CHANNELS_COUNT + 1) if ch not in excluded]

    @property
    def street_channels(self) -> List[int]:
        return self._int_list(self.STREET_CAMERAS)

    @property
    def DATA_DIR(self) -> Path:
        p = self.BASE_DIR / "data"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def MODELS_DIR(self) -> Path:
        p = self.BASE_DIR / "models"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @staticmethod
    def _int_list(raw: str) -> List[int]:
        return [int(x) for x in str(raw).replace(" ", "").split(",") if x.strip().isdigit()]

    @property
    def attendance_channels(self) -> List[int]:
        return self._int_list(self.ATTENDANCE_CAMERAS)

    @property
    def desk_channels(self) -> List[int]:
        return self._int_list(self.DESK_CAMERAS)

    @property
    def work_days(self) -> List[int]:
        return self._int_list(self.WORK_DAYS)

    @staticmethod
    def parse_hhmm(raw: str) -> time:
        h, m = str(raw).strip().split(":")[:2]
        return time(int(h), int(m))

    def in_monitor_window(self, now: Optional[datetime] = None) -> bool:
        now = now or datetime.now()
        if now.weekday() not in self.work_days:
            return False
        return self.parse_hhmm(self.MONITOR_START) <= now.time() <= self.parse_hhmm(self.MONITOR_END)

    # Kameralar uchun do'stona nomlar
    CAMERA_NAMES: Dict[int, Tuple[str, str]] = {
        1: ("shaxsiyxona", "Shaxsiy xona"),
        2: ("kirish", "Kirish yo'lagi"),
        3: ("kocha", "Ko'cha / Darvoza"),
        4: ("ofis_asosiy", "Asosiy Ofis zali"),
        5: ("ish_stoli", "Ishchi stollar hududi"),
        6: ("avtoturargoh", "Avtoturargoh zonasi"),
        7: ("qabulxona", "Qabulxona (Reception)"),
        8: ("oshxona", "Oshxona / Dam olish xonasi"),
        9: ("omborxona", "Asosiy Omborxona"),
        10: ("koridor_1", "1-qavat Koridori"),
        11: ("koridor_2", "2-qavat Koridori"),
        12: ("majlislar_zali", "Majlislar zali"),
        13: ("orqa_hovli", "Orqa hovli"),
        14: ("server_xonasi", "Server xonasi"),
        16: ("garaj", "Garaj hududi"),
        17: ("kassa", "Kassa / Hisob-kitob"),
        18: ("tashqi_perimetr", "Tashqi perimetr"),
    }

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    def get_live_rtsp(self, channel: int, sub_stream: bool = True) -> str:
        """Jonli oqim uchun RTSP URL (sub-stream=602, main=601)."""
        code = f"{channel:01d}02" if sub_stream else f"{channel:01d}01"
        return (
            f"rtsp://{self.NVR_USER}:{self.NVR_PASSWORD}"
            f"@{self.NVR_IP}:{self.NVR_PORT}/Streaming/Channels/{code}"
        )

    def get_playback_rtsp(self, channel: int, start: str, end: str, sub_stream: bool = False) -> str:
        """
        Hikvision NVR HDD arxividan vaqt oralig'iga tegishli RTSP URL.
        sub_stream=True → 02 track (yengil, ~200 KB/s), tez chiqib keladi.
        sub_stream=False → 01 track (asosiy sifat, kattaroq).
        start/end formati: YYYYMMDDTHHMMSSZ (UTC).
        """
        code = f"{channel:01d}02" if sub_stream else f"{channel:01d}01"
        return (
            f"rtsp://{self.NVR_USER}:{self.NVR_PASSWORD}"
            f"@{self.NVR_IP}:{self.NVR_PORT}"
            f"/Streaming/tracks/{code}?starttime={start}&endtime={end}"
        )

    def get_camera(self, channel: int) -> Dict[str, str]:
        code, name = self.CAMERA_NAMES.get(channel, (f"kamera_{channel:02d}", f"Kamera #{channel:02d}"))
        return {"channel": channel, "code_name": code, "name": name}

    def list_cameras(self) -> list:
        return [self.get_camera(ch) for ch in self.channel_ids]


settings = Settings()
