"""
Pure On-Demand RTSP Manager.

Falsafa:
- Hech qanday fon threadi yo'q, YOLO yo'q, disk yozuvi yo'q.
- Snapshot: RTSP ochiladi → 1 kadr o'qiladi → RTSP darhol yopiladi.
- Playback: Hikvision NVR HDD arxividan vaqt oralig'i → 1-2 kadr → yopiladi.
- Jonli MJPEG oqim: bir vaqtda faqat BITTA kamera uchun ochiladi. Boshqa kamera
  tanlansa yoki sahifa yopilsa oldingi oqim darhol to'xtatiladi.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Generator, List, Optional, Tuple

import cv2
import numpy as np

from config import settings


# =============================================================================
# Vaqtinchalik klip papkasi (30 daqiqadan keyin avto-tozalanadi)
# =============================================================================

CLIPS_DIR: Path = settings.BASE_DIR / "clips"
CLIPS_DIR.mkdir(parents=True, exist_ok=True)
_CLIP_TTL_SECONDS = 30 * 60  # 30 daqiqa


def _cleanup_old_clips_loop() -> None:
    while True:
        try:
            now = time.time()
            for f in CLIPS_DIR.glob("*.mp4"):
                try:
                    if now - f.stat().st_mtime > _CLIP_TTL_SECONDS:
                        f.unlink(missing_ok=True)
                except OSError:
                    pass
        except Exception:
            pass
        time.sleep(120)


threading.Thread(target=_cleanup_old_clips_loop, name="clip-cleanup", daemon=True).start()


def _has_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None


_nvr_state = {"ok": None, "checked": 0.0}
_nvr_lock = threading.Lock()


def nvr_online(ttl: float = 15.0) -> bool:
    """NVR RTSP porti ochiqmi (2 s ichida). Natija 15 s keshlanadi — oflayn bo'lsa RTSP'da 30 s kutmaymiz."""
    import socket
    with _nvr_lock:
        if _nvr_state["ok"] is not None and time.time() - _nvr_state["checked"] < ttl:
            return _nvr_state["ok"]
    ok = False
    try:
        with socket.create_connection((settings.NVR_IP, settings.NVR_PORT), timeout=2.0):
            ok = True
    except OSError:
        ok = False
    with _nvr_lock:
        _nvr_state.update(ok=ok, checked=time.time())
    return ok


_FFMPEG_AVAILABLE = _has_ffmpeg()


# =============================================================================
# 1. ON-DEMAND SNAPSHOT (1 KADR)
# =============================================================================

# Fon kuzatuvchilari (yuz tanish, qo'riqlash) o'qiyotgan kanallarning so'nggi kadri.
# Shu kanal uchun kadr so'ralsa ikkinchi RTSP ulanish ochilmaydi: kamera/NVR ulanishlar soni cheklangan,
# ikkinchi ulanish 30+ soniya osilib qolardi.
_latest: Dict[Tuple[int, bool], Tuple[float, np.ndarray]] = {}


def publish_frame(channel: int, frame: np.ndarray, sub_stream: bool) -> None:
    _latest[(channel, sub_stream)] = (time.time(), frame)


def latest_frame(channel: int, sub_stream: bool, max_age: float = 4.0) -> Optional[np.ndarray]:
    """sub_stream=False (yuqori sifat) faqat asosiy oqim kadrini qabul qiladi; past sifat uchun ikkalasi ham bo'ladi."""
    keys = [(channel, False)] if not sub_stream else [(channel, True), (channel, False)]
    now = time.time()
    for k in keys:
        item = _latest.get(k)
        if item and now - item[0] <= max_age:
            return item[1]
    return None


def _is_corrupt(frame: np.ndarray) -> bool:
    """H.265 oqimi kalit kadrgacha bir tekis kulrang (128) kadr beradi — bunday kadrda odam topilmaydi."""
    small = cv2.resize(frame, (64, 36), interpolation=cv2.INTER_NEAREST).astype(np.int16)
    return float(np.mean(np.all(np.abs(small - 128) <= 3, axis=2))) > 0.6


def _ffmpeg_frame(rtsp_url: str, timeout: float) -> Optional[bytes]:
    """Asosiy H.265 oqimidan bitta kadr: ayrim kameralarda OpenCV faqat buzilgan kadr beradi, ffmpeg esa toza oladi."""
    if not _FFMPEG_AVAILABLE:
        return None
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "quiet", "-rtsp_transport", "tcp", "-timeout", "10000000", "-i", rtsp_url,
           "-frames:v", "1", "-q:v", "3", "-f", "image2pipe", "-c:v", "mjpeg", "-"]
    try:
        data = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=timeout).stdout
    except subprocess.TimeoutExpired:
        return None
    frame = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR) if data else None
    return data if frame is not None and not _is_corrupt(frame) else None


def capture_snapshot(channel: int, max_attempts: int = 2, timeout_seconds: float = 6.0,
                     sub_stream: bool = True) -> Optional[bytes]:
    """
    RTSP ochib, bitta stabil kadr olib, ulanishni darhol yopadi.
    sub_stream=False — asosiy (yuqori sifat) oqim, yuz tanish uchun.
    Muvaffaqiyatli bo'lsa JPEG bayt qaytaradi, aks holda None.
    """
    cached = latest_frame(channel, sub_stream)
    if cached is not None and not _is_corrupt(cached):
        if sub_stream and cached.shape[1] > 1280:
            cached = cv2.resize(cached, (1280, int(cached.shape[0] * 1280 / cached.shape[1])), interpolation=cv2.INTER_AREA)
        ok, buf = cv2.imencode(".jpg", cached, [cv2.IMWRITE_JPEG_QUALITY, 85])
        if ok:
            return buf.tobytes()
    if not nvr_online():
        return None
    rtsp_url = settings.get_live_rtsp(channel, sub_stream=sub_stream)
    if not sub_stream:
        jpeg = _ffmpeg_frame(rtsp_url, timeout_seconds + 6)
        if jpeg:
            return jpeg
    open_params =[cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, int(timeout_seconds * 1500), cv2.CAP_PROP_READ_TIMEOUT_MSEC, int(timeout_seconds * 1000)]
    for attempt in range(1, max_attempts + 1):
        cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG, open_params)
        try:
            if not cap.isOpened():
                time.sleep(0.4)
                continue
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

            deadline = time.time() + timeout_seconds
            frame = None
            # Bir nechta kadrni "yutamiz" (sekin ochilishi mumkin) va oxirgi barqarorini olamiz
            warm_up = 0
            while time.time() < deadline:
                grabbed = cap.grab()
                if not grabbed:
                    time.sleep(0.05)
                    continue
                ret, f = cap.retrieve()
                if not ret or f is None:
                    time.sleep(0.05)
                    continue
                if _is_corrupt(f):
                    continue
                frame = f
                warm_up += 1
                if warm_up >= 3:
                    break

            if frame is None:
                continue

            ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
            if ok:
                return buf.tobytes()
        finally:
            cap.release()
    return None


# =============================================================================
# 2. PLAYBACK — NVR HDD ARXIVIDAN VAQT ORALIG'I UCHUN 1-N KADR
# =============================================================================

def _hik_time(dt: datetime) -> str:
    return dt.strftime("%Y%m%dT%H%M%SZ")


# =============================================================================
# LIVE BURST — bir zumda bir nechta snapshot olish (video o'rniga)
# =============================================================================

def capture_live_burst(channel: int, count: int = 3, spacing_seconds: float = 1.2,
                       timeout_seconds: float = 12.0) -> List[bytes]:
    """
    Jonli RTSP oqimidan bir zumda `count` ta kadr olib ulanishni yopadi.
    Kadrlar orasida `spacing_seconds` uzilish saqlanadi (harakatni sezish uchun).
    """
    if not nvr_online():
        return []
    rtsp_url = settings.get_live_rtsp(channel, sub_stream=True)
    cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)
    frames: List[bytes] = []
    try:
        if not cap.isOpened():
            return []
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        # warm-up
        deadline = time.time() + 3.0
        while time.time() < deadline:
            if cap.grab():
                break
            time.sleep(0.05)

        end_at = time.time() + timeout_seconds
        next_at = time.time()
        while len(frames) < count and time.time() < end_at:
            if not cap.grab():
                time.sleep(0.05)
                continue
            if time.time() < next_at:
                continue
            ret, f = cap.retrieve()
            if not ret or f is None:
                continue
            ok, buf = cv2.imencode(".jpg", f, [cv2.IMWRITE_JPEG_QUALITY, 82])
            if ok:
                frames.append(buf.tobytes())
                next_at = time.time() + spacing_seconds
    finally:
        cap.release()
    return frames


# =============================================================================
# LIVE CLIP — jonli oqimdan qisqa MP4 yozish
# =============================================================================

def record_live_clip(channel: int, duration_seconds: int = 10) -> Optional[str]:
    """
    Jonli RTSP oqimidan `duration_seconds` (max 30) MP4 klip yozadi.
    Muvaffaqiyatli bo'lsa `clips/xxx.mp4` fayl nomini qaytaradi.
    """
    if not nvr_online():
        return None
    duration_seconds = max(3, min(30, int(duration_seconds)))
    rtsp_url = settings.get_live_rtsp(channel, sub_stream=True)  # yengil, tez
    fname = f"live_cam{channel:02d}_{datetime.now():%Y%m%d_%H%M%S}_{uuid.uuid4().hex[:6]}.mp4"
    out_path = CLIPS_DIR / fname

    if _FFMPEG_AVAILABLE:
        cmd = [
            "ffmpeg", "-y", "-rtsp_transport", "tcp", "-timeout", "10000000",
            "-i", rtsp_url,
            "-t", str(duration_seconds),
            "-c", "copy", "-movflags", "+faststart",
            str(out_path),
        ]
        try:
            proc = subprocess.run(cmd, stdout=subprocess.DEVNULL,
                                  stderr=subprocess.PIPE,
                                  timeout=duration_seconds + 20)
            if proc.returncode == 0 and out_path.exists() and out_path.stat().st_size > 10_000:
                return fname
            print(f"[record_live_clip] ffmpeg xato: {proc.stderr.decode(errors='ignore')[:200]}")
        except subprocess.TimeoutExpired:
            print("[record_live_clip] ffmpeg timeout")
        except Exception as e:
            print(f"[record_live_clip] ffmpeg exception: {e}")

    # OpenCV fallback
    return _record_opencv(rtsp_url, out_path, duration_seconds, fname)


def _record_opencv(rtsp_url: str, out_path: Path, duration_seconds: int, fname: str) -> Optional[str]:
    cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)
    try:
        if not cap.isOpened():
            return None
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 640)
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 360)
        fps = min(cap.get(cv2.CAP_PROP_FPS) or 12.0, 15.0)
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        out = cv2.VideoWriter(str(out_path), fourcc, fps, (w, h))
        if not out.isOpened():
            return None

        deadline = time.time() + duration_seconds + 3
        frames_written = 0
        while time.time() < deadline:
            ret, frame = cap.read()
            if not ret or frame is None:
                time.sleep(0.05)
                continue
            out.write(frame)
            frames_written += 1
        out.release()
        if frames_written > 10:
            return fname
        # Muvaffaqiyatsiz — bo'sh faylni o'chirib yuboramiz
        try: out_path.unlink(missing_ok=True)
        except OSError: pass
        return None
    finally:
        cap.release()


# =============================================================================
# LONG-RANGE SAMPLING — uzoq vaqt oraligidan parallel N ta kadr
# =============================================================================

def _grab_single_from_playback(channel: int, at_time: datetime,
                               window_seconds: int = 8,
                               timeout: float = 15.0) -> Optional[bytes]:
    """
    Berilgan aniq vaqt atrofidagi kichik oynadan (window_seconds) 1 ta kadr oladi.
    Ffmpeg orqali ishlaydi (OpenCV Hikvision playback bilan sekin).
    """
    if not nvr_online():
        return None
    start = at_time
    end = at_time + timedelta(seconds=window_seconds)
    rtsp_url = settings.get_playback_rtsp(channel, _hik_time(start), _hik_time(end), sub_stream=False)

    if _FFMPEG_AVAILABLE:
        tmp = CLIPS_DIR / f"_tmp_{uuid.uuid4().hex[:8]}.jpg"
        cmd = [
            "ffmpeg", "-y",
            "-rtsp_transport", "tcp", "-timeout", "10000000",
            "-i", rtsp_url,
            "-vframes", "1",
            "-q:v", "3",
            str(tmp),
        ]
        try:
            proc = subprocess.run(cmd, stdout=subprocess.DEVNULL,
                                  stderr=subprocess.PIPE, timeout=timeout)
            if proc.returncode == 0 and tmp.exists() and tmp.stat().st_size > 500:
                data = tmp.read_bytes()
                tmp.unlink(missing_ok=True)
                return data
            if tmp.exists():
                tmp.unlink(missing_ok=True)
        except subprocess.TimeoutExpired:
            if tmp.exists():
                try: tmp.unlink()
                except OSError: pass
        except Exception as e:
            print(f"[_grab_single_from_playback] xato: {e}")
    return None


def sample_playback_range(channel: int, start: datetime, end: datetime,
                          sample_count: int = 15, max_workers: int = 6) -> List[Tuple[datetime, bytes]]:
    """
    `start`—`end` oraliqdan `sample_count` ta kadrni parallel yig'ib oladi.
    Qaytaradi: [(vaqt, jpeg_bytes), ...] — vaqt bo'yicha tartibda.

    Uzoq oraliqlar uchun (masalan bugun 07:00—13:00, 6 soatlik) tez tahlil imkonini beradi:
    6 soat / 15 kadr = 24 daqiqada bitta namuna.
    Parallel 6 ta thread bilan ~60-90 sekundda tugaydi.
    """
    span = (end - start).total_seconds()
    if span <= 0 or sample_count < 1 or not nvr_online():
        return []
    sample_count = max(1, min(30, int(sample_count)))
    step = span / (sample_count + 1)
    sample_times = [start + timedelta(seconds=step * (i + 1)) for i in range(sample_count)]

    results: List[Tuple[datetime, Optional[bytes]]] = []
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        future_to_time = {
            pool.submit(_grab_single_from_playback, channel, t): t for t in sample_times
        }
        for fut in as_completed(future_to_time):
            t = future_to_time[fut]
            try:
                data = fut.result()
            except Exception:
                data = None
            if data:
                results.append((t, data))

    results.sort(key=lambda x: x[0])
    return results


# =============================================================================
# PLAYBACK CLIP — NVR HDD arxividan MP4 kesib olish
# =============================================================================

def record_playback_clip(channel: int, start: datetime, end: datetime,
                         max_seconds: int = 30) -> Optional[str]:
    """NVR HDD arxividan MP4 klip kesib oladi (max 30 s). Fayl nomini qaytaradi."""
    if end <= start or not nvr_online():
        return None
    span = int((end - start).total_seconds())
    if span <= 0:
        return None
    if span > max_seconds:
        end = start + timedelta(seconds=max_seconds)
        span = max_seconds

    # Hikvision NVR odatda faqat main-stream'ni HDD'ga yozadi. Main-stream'dan copy qilamiz.
    rtsp_url = settings.get_playback_rtsp(channel, _hik_time(start), _hik_time(end), sub_stream=False)
    fname = f"pb_cam{channel:02d}_{start:%Y%m%d_%H%M%S}_{span}s_{uuid.uuid4().hex[:6]}.mp4"
    out_path = CLIPS_DIR / fname

    if _FFMPEG_AVAILABLE:
        # Hikvision playback tez orada real-time'da chiqib keladi.
        # `-re` bilan tezlashtirib bo'lmaydi (playback allaqachon RTP timing bo'yicha keladi).
        # Timeout: span * 2 + 60 (Hikvision seek + boshlash uchun ~10-20s ketishi mumkin)
        # Copy (re-encode yo'q) — tez yoziladi, katta fayl (main-stream) lekin foydalanuvchi tez javob oladi
        cmd = [
            "ffmpeg", "-y",
            "-rtsp_transport", "tcp", "-timeout", "10000000",
            "-fflags", "+genpts",
            "-i", rtsp_url,
            "-t", str(span + 2),
            "-c", "copy",
            "-an",
            "-movflags", "+faststart",
            str(out_path),
        ]
        try:
            proc = subprocess.run(cmd, stdout=subprocess.DEVNULL,
                                  stderr=subprocess.PIPE,
                                  timeout=span * 2 + 60)
            if proc.returncode == 0 and out_path.exists() and out_path.stat().st_size > 5_000:
                return fname
            err_snippet = proc.stderr.decode(errors='ignore')[:300]
            print(f"[record_playback_clip] ffmpeg rc={proc.returncode}: {err_snippet}")
        except subprocess.TimeoutExpired:
            print(f"[record_playback_clip] ffmpeg timeout ({span*2+60}s), fayl hajmi: "
                  f"{out_path.stat().st_size if out_path.exists() else 0}")
            # Timeout bo'lsa ham fayl qisman yozilgan bo'lishi mumkin — tekshiramiz
            if out_path.exists() and out_path.stat().st_size > 50_000:
                return fname
        except Exception as e:
            print(f"[record_playback_clip] ffmpeg exception: {e}")

    return _record_opencv(rtsp_url, out_path, span, fname)


def capture_playback_frames(
    channel: int,
    start: datetime,
    end: datetime,
    frames_wanted: int = 2,
    timeout_seconds: float = 20.0,
) -> List[bytes]:
    """
    NVR qattiq diskidan `start`—`end` oraliqdagi RTSP Playback oqimini
    ochib, bir tekis taqsimlangan `frames_wanted` ta kadr JPEG olib qaytaradi.
    Ulanish oxirida darhol yopiladi.
    """
    if end <= start or not nvr_online():
        return []
    rtsp_url = settings.get_playback_rtsp(channel, _hik_time(start), _hik_time(end))
    cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)
    frames: List[bytes] = []
    try:
        if not cap.isOpened():
            return []
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        # Playback davomiyligi soniyada
        span = max(1.0, (end - start).total_seconds())
        # Har `interval` soniyada bitta kadr olamiz
        interval = span / (frames_wanted + 1)

        deadline = time.time() + timeout_seconds
        next_capture_at = time.time()  # relative wall-clock
        elapsed = 0.0
        last_ts = time.time()

        while len(frames) < frames_wanted and time.time() < deadline:
            grabbed = cap.grab()
            if not grabbed:
                time.sleep(0.03)
                continue
            now = time.time()
            elapsed += now - last_ts
            last_ts = now

            if now >= next_capture_at:
                ret, f = cap.retrieve()
                if ret and f is not None:
                    ok, buf = cv2.imencode(".jpg", f, [cv2.IMWRITE_JPEG_QUALITY, 85])
                    if ok:
                        frames.append(buf.tobytes())
                        next_capture_at = now + max(0.2, interval * 0.3)
    finally:
        cap.release()
    return frames


# =============================================================================
# 3. JONLI MJPEG OQIM — SLOTLAR (asosiy pleer + ko'p kamerali setka)
# =============================================================================

MAX_SLOTS = 17


class _StreamGuard:
    """
    Har bir "slot" (asosiy pleer yoki setka katagi) bir vaqtda faqat bitta oqimga ega.
    Slotga yangi kamera ochilsa — eskisi darhol to'xtaydi. stop_all() — hammasini yopadi.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._slots: Dict[str, Tuple[int, int]] = {}  # slot -> (token, channel)
        self._token = 0

    def start_new(self, channel: int, slot: str = "main") -> int:
        with self._lock:
            if slot not in self._slots and len(self._slots) >= MAX_SLOTS:
                raise RuntimeError("Juda ko'p parallel oqim")
            self._token += 1
            self._slots[slot] = (self._token, channel)
            return self._token

    def is_current(self, token: int, slot: str = "main") -> bool:
        with self._lock:
            cur = self._slots.get(slot)
            return cur is not None and cur[0] == token

    def release(self, token: int, slot: str) -> None:
        with self._lock:
            cur = self._slots.get(slot)
            if cur and cur[0] == token:
                self._slots.pop(slot, None)

    def active_channel(self) -> Optional[int]:
        with self._lock:
            cur = self._slots.get("main")
            return cur[1] if cur else None

    def active(self) -> Dict[str, int]:
        with self._lock:
            return {k: v[1] for k, v in self._slots.items()}

    def stop(self, prefix: str = "") -> None:
        with self._lock:
            for k in [k for k in self._slots if k.startswith(prefix)]:
                self._slots.pop(k, None)

    def stop_all(self) -> None:
        self.stop("")


stream_guard = _StreamGuard()


def _placeholder_jpeg(text: str) -> bytes:
    img = np.zeros((360, 640, 3), dtype=np.uint8)
    img[:] = (18, 22, 33)
    cv2.putText(img, text, (30, 190), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (180, 190, 210), 2)
    ok, buf = cv2.imencode(".jpg", img)
    return buf.tobytes() if ok else b""


def generate_mjpeg(channel: int, slot: str = "main", faces: bool = False, fps: float = 14.0) -> Generator[bytes, None, None]:
    """
    Kameraning jonli MJPEG oqimi. Mijoz uzilsa, slotga boshqa kamera ochilsa yoki stop qilinsa — RTSP yopiladi.
    faces=True — har ~1.5 s da yuzlar aniqlanib, tanilganlar ramka bilan belgilanadi.
    """
    token = stream_guard.start_new(channel, slot)
    rtsp_url = settings.get_live_rtsp(channel, sub_stream=True)
    cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG) if nvr_online() else cv2.VideoCapture()
    if cap.isOpened():
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    boundary = b"--frame\r\n"
    connecting_placeholder = _placeholder_jpeg(f"Kamera #{channel:02d} oqimi ulanmoqda...")
    offline_placeholder = _placeholder_jpeg(f"NVR {settings.NVR_IP} ulanmagan (tarmoqni tekshiring)")
    delay = 1.0 / max(1.0, fps)

    try:
        placeholder_sent_at = 0.0
        while stream_guard.is_current(token, slot):
            if not cap.isOpened():
                online = nvr_online()
                now = time.time()
                if now - placeholder_sent_at >= 1.0:
                    placeholder_sent_at = now
                    ph = connecting_placeholder if online else offline_placeholder
                    yield boundary + b"Content-Type: image/jpeg\r\n\r\n" + ph + b"\r\n"
                time.sleep(0.2 if online else 2.0)
                if not online:
                    continue
                cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)
                if cap.isOpened():
                    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                continue

            if not cap.grab():
                time.sleep(0.05)
                continue
            ret, frame = cap.retrieve()
            if not ret or frame is None:
                time.sleep(0.05)
                continue

            if faces:
                from live_overlay import live_overlay
                frame = live_overlay.draw(frame, channel)

            ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 72])
            if not ok:
                continue
            yield boundary + b"Content-Type: image/jpeg\r\n\r\n" + buf.tobytes() + b"\r\n"
            time.sleep(delay)
    except GeneratorExit:
        pass
    finally:
        cap.release()
        stream_guard.release(token, slot)


# =============================================================================
# 4. MOZAIKA OQIMI — ko'p kamera bitta MJPEG'da (brauzer 6-ulanish chegarasini aylanib o'tadi)
# =============================================================================

class _ChannelReader(threading.Thread):
    """Bitta kameraning sub-stream'idan eng so'nggi kadrni ushlab turadi."""

    def __init__(self, channel: int, stop: threading.Event) -> None:
        super().__init__(name=f"mosaic-ch{channel:02d}", daemon=True)
        self.channel = channel
        self.stop_event = stop
        self.frame: Optional[np.ndarray] = None
        self.lock = threading.Lock()

    def run(self) -> None:
        cap = None
        while not self.stop_event.is_set():
            if cap is None:
                if not nvr_online():
                    self.stop_event.wait(3)
                    continue
                cap = cv2.VideoCapture(settings.get_live_rtsp(self.channel, sub_stream=True), cv2.CAP_FFMPEG)
                if not cap.isOpened():
                    cap.release()
                    cap = None
                    self.stop_event.wait(5)
                    continue
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            if not cap.grab():
                cap.release()
                cap = None
                continue
            ok, f = cap.retrieve()
            if ok and f is not None:
                with self.lock:
                    self.frame = f
        if cap is not None:
            cap.release()

    def latest(self) -> Optional[np.ndarray]:
        with self.lock:
            return self.frame


def generate_mosaic(channels: List[int], cols: int, faces: bool = False, fps: float = 5.0) -> Generator[bytes, None, None]:
    """Tanlangan kameralarni bitta setka kadriga yig'ib MJPEG sifatida uzatadi (slot 'grid')."""
    token = stream_guard.start_new(0, "grid")
    stop = threading.Event()
    readers = [_ChannelReader(ch, stop) for ch in channels]
    for r in readers:
        r.start()
    cols = max(1, cols)
    rows = -(-len(channels) // cols)
    tw = 640 if cols <= 2 else 480 if cols <= 3 else 400
    th = tw * 9 // 16
    blank = np.zeros((th, tw, 3), np.uint8)
    blank[:] = (18, 22, 33)
    boundary = b"--frame\r\n"
    try:
        while stream_guard.is_current(token, "grid"):
            tiles = []
            online = nvr_online()
            for r in readers:
                f = r.latest()
                if f is None:
                    t = blank.copy()
                    msg = "ulanmoqda..." if online else "Kamera ulanmagan"
                    cv2.putText(t, msg, (tw // 2 - 70, th // 2), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (150, 160, 190), 1, cv2.LINE_AA)
                else:
                    t = cv2.resize(f, (tw, th), interpolation=cv2.INTER_AREA)
                    if faces:
                        from live_overlay import live_overlay
                        t = live_overlay.draw(t, r.channel)
                tiles.append(t)
            while len(tiles) < rows * cols:
                tiles.append(blank)
            grid = np.vstack([np.hstack(tiles[i * cols:(i + 1) * cols]) for i in range(rows)])
            ok, buf = cv2.imencode(".jpg", grid, [cv2.IMWRITE_JPEG_QUALITY, 70])
            if ok:
                yield boundary + b"Content-Type: image/jpeg\r\n\r\n" + buf.tobytes() + b"\r\n"
            time.sleep(1.0 / max(1.0, fps))
    except GeneratorExit:
        pass
    finally:
        stop.set()
        stream_guard.release(token, "grid")
