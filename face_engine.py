"""
Yuz tanish motori: OpenCV YuNet (aniqlash) + ArcFace R50 (512 o'lchamli, InsightFace buffalo_l).
ArcFace fayli bo'lmasa SFace (128 o'lchamli) ishlatiladi. InsightFace modeli tijorat uchun litsenziyalanmagan — faqat test.

- C++ kompilyatorsiz ishlaydi (OpenCV ichida), GPU shart emas.
- Xodimlar galereyasi xotirada saqlanadi (numpy matritsa), cosine similarity bilan solishtiriladi.
"""

from __future__ import annotations

import io
import threading
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from config import settings

YUNET_FILE = "face_detection_yunet_2023mar.onnx"
SFACE_FILE = "face_recognition_sface_2021dec.onnx"
ARCFACE_FILE = "w600k_r50.onnx"
_ARCFACE_REF = np.array([[38.2946, 51.6963], [73.5318, 51.5014], [56.0252, 71.7366],
                         [41.5493, 92.3655], [70.7299, 92.2041]], dtype=np.float32)
_MODEL_URLS = {
    YUNET_FILE: [
        "https://huggingface.co/opencv/face_detection_yunet/resolve/main/" + YUNET_FILE,
        "https://hf-mirror.com/opencv/face_detection_yunet/resolve/main/" + YUNET_FILE,
        "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/" + YUNET_FILE,
    ],
    SFACE_FILE: [
        "https://github.com/opencv/opencv_zoo/raw/main/models/face_recognition_sface/" + SFACE_FILE,
        "https://huggingface.co/opencv/face_recognition_sface/resolve/main/" + SFACE_FILE,
        "https://hf-mirror.com/opencv/face_recognition_sface/resolve/main/" + SFACE_FILE,
    ],
}
_MIN_MODEL_BYTES = {YUNET_FILE: 200_000, SFACE_FILE: 30_000_000}
_DETECT_MAX_SIDE = 2560


@dataclass
class FaceResult:
    box: Tuple[int, int, int, int]          # x, y, w, h (asl rasm koordinatalarida)
    score: float
    row: np.ndarray                          # YuNet satri (asl koordinatalarda)
    embedding: Optional[np.ndarray] = None   # normallangan vektor
    employee_id: Optional[int] = None
    name: Optional[str] = None
    similarity: float = 0.0
    too_small: bool = False

    @property
    def known(self) -> bool:
        return self.employee_id is not None


@dataclass
class _Gallery:
    matrix: np.ndarray = field(default_factory=lambda: np.zeros((0, 128), dtype=np.float32))
    labels: np.ndarray = field(default_factory=lambda: np.zeros((0,), dtype=np.int64))
    names: Dict[int, str] = field(default_factory=dict)


def _model_ok(path: Path, name: str) -> bool:
    return path.exists() and path.stat().st_size >= _MIN_MODEL_BYTES[name]


_UA = {"User-Agent": "Mozilla/5.0"}


def _resolve(url: str, timeout: float = 30, retries: int = 8) -> Tuple[str, int]:
    """Redirectlardan keyingi yakuniy URL va fayl hajmini qaytaradi."""
    last = None
    for _ in range(retries):
        try:
            req = urllib.request.Request(url, headers={**_UA, "Range": "bytes=0-0"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                total = int(r.headers.get("Content-Range", "0/0").split("/")[-1] or 0)
                return r.geturl(), total
        except Exception as e:
            last = e
    raise RuntimeError(f"manzil aniqlanmadi: {last}")


def _fetch_range(url: str, start: int, end: int, retries: int = 8) -> bytes:
    last = None
    for _ in range(retries):
        try:
            req = urllib.request.Request(url, headers={**_UA, "Range": f"bytes={start}-{end}"})
            with urllib.request.urlopen(req, timeout=30) as r:
                data = r.read()
            if len(data) == end - start + 1:
                return data
            last = f"qisqa javob {len(data)}"
        except Exception as e:
            last = e
    raise RuntimeError(f"bo'lak {start}-{end} yuklanmadi: {last}")


def _download_ranged(url: str, target: Path, min_bytes: int, workers: int = 16,
                     chunk: int = 1 << 19) -> bool:
    """
    Beqaror/cheklangan tarmoq uchun: faylni bo'laklarga bo'lib parallel yuklaydi.
    Har bo'lak diskka yoziladi — uzilsa, keyingi urinishda qolgan joyidan davom etadi.
    """
    import shutil
    from concurrent.futures import ThreadPoolExecutor, as_completed

    final_url, total = _resolve(url)
    if total < min_bytes:
        return False
    parts_dir = target.parent / ".parts" / f"{target.name}.{total}"
    parts_dir.mkdir(parents=True, exist_ok=True)
    ranges = [(s, min(s + chunk, total) - 1) for s in range(0, total, chunk)]
    todo = [r for r in ranges if not ((parts_dir / f"{r[0]}.bin").exists()
                                      and (parts_dir / f"{r[0]}.bin").stat().st_size == r[1] - r[0] + 1)]

    def _get(r):
        data = _fetch_range(final_url, *r)
        tmp = parts_dir / f"{r[0]}.{threading.get_ident()}.tmp"
        tmp.write_bytes(data)
        tmp.replace(parts_dir / f"{r[0]}.bin")

    done = len(ranges) - len(todo)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for fut in as_completed([pool.submit(_get, r) for r in todo]):
            fut.result()
            done += 1
            if done % 8 == 0 or done == len(ranges):
                print(f"[FaceEngine] {target.name}: {done}/{len(ranges)} bo'lak", flush=True)

    tmp = target.with_suffix(".part")
    with open(tmp, "wb") as f:
        for s, _ in ranges:
            f.write((parts_dir / f"{s}.bin").read_bytes())
    if tmp.stat().st_size != total:
        tmp.unlink(missing_ok=True)
        return False
    tmp.replace(target)
    shutil.rmtree(parts_dir, ignore_errors=True)
    return True


def download_models() -> Dict[str, bool]:
    """Yetishmayotgan modellarni bir nechta manbadan yuklab olishga harakat qiladi."""
    result = {}
    for name, urls in _MODEL_URLS.items():
        target = settings.MODELS_DIR / name
        if _model_ok(target, name):
            result[name] = True
            continue
        ok = False
        for url in urls:
            try:
                ok = _download_ranged(url, target, _MIN_MODEL_BYTES[name])
                if ok:
                    print(f"[FaceEngine] {name} yuklandi ({url.split('/')[2]})")
                    break
            except Exception as e:
                print(f"[FaceEngine] {name} yuklanmadi ({url.split('/')[2]}): {str(e)[:100]}")
        result[name] = ok
    return result


class FaceEngine:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._detector = None
        self._recognizer = None
        self._arcface = None
        self._arcface_input = ""
        self._gallery = _Gallery()
        self._gallery_lock = threading.Lock()
        self._load_error: Optional[str] = None
        self._font_cache: Dict[int, ImageFont.ImageFont] = {}

    # ------------------------------------------------------------------ models
    @property
    def available(self) -> bool:
        return self._ensure_loaded()

    def _ensure_loaded(self) -> bool:
        if self._detector is not None and self._recognizer is not None:
            return True
        yunet = settings.MODELS_DIR / YUNET_FILE
        sface = settings.MODELS_DIR / SFACE_FILE
        if not (_model_ok(yunet, YUNET_FILE) and _model_ok(sface, SFACE_FILE)):
            self._load_error = "Yuz tanish modellari yuklanmagan (models/ papkasi)"
            return False
        with self._lock:
            if self._detector is None:
                try:
                    self._detector = cv2.FaceDetectorYN.create(
                        str(yunet), "", (320, 320), settings.FACE_DETECT_SCORE, 0.3, 5000)
                    self._recognizer = cv2.FaceRecognizerSF.create(str(sface), "")
                    self._load_arcface()
                    self._load_error = None
                except Exception as e:
                    self._detector = self._recognizer = None
                    self._load_error = f"Model yuklash xatosi: {e}"
                    return False
        return True

    def _load_arcface(self) -> None:
        path = settings.MODELS_DIR / ARCFACE_FILE
        if settings.FACE_MODEL != "arcface" or not path.exists():
            return
        try:
            import onnxruntime as ort
            opts = ort.SessionOptions()
            opts.intra_op_num_threads = 2
            self._arcface = ort.InferenceSession(str(path), opts, providers=["CPUExecutionProvider"])
            self._arcface_input = self._arcface.get_inputs()[0].name
        except Exception as e:
            self._arcface = None
            print(f"[FaceEngine] ArcFace yuklanmadi, SFace ishlatiladi: {e}")

    @property
    def dim(self) -> int:
        self._ensure_loaded()
        return 512 if self._arcface is not None else 128

    def status(self) -> dict:
        ok = self._ensure_loaded()
        with self._gallery_lock:
            n_samples = int(self._gallery.matrix.shape[0])
            n_people = len(set(self._gallery.labels.tolist()))
        return {"ready": ok, "error": self._load_error, "samples": n_samples, "employees": n_people,
                "model": "arcface" if self._arcface is not None else "sface",
                "threshold": settings.FACE_MATCH_THRESHOLD}

    # ----------------------------------------------------------------- gallery
    def reload_gallery(self) -> None:
        from sqlmodel import select
        from database import Employee, FaceSample, get_session

        with get_session() as s:
            emps = {e.id: e for e in s.exec(select(Employee).where(Employee.active == True)).all()}  # noqa: E712
            samples = s.exec(select(FaceSample)).all()
        vecs, labels = [], []
        for fs in samples:
            if fs.employee_id not in emps:
                continue
            v = np.frombuffer(fs.embedding, dtype=np.float32)
            if v.shape[0] != self.dim:
                continue
            vecs.append(v)
            labels.append(fs.employee_id)
        gal = _Gallery(
            matrix=np.vstack(vecs).astype(np.float32) if vecs else np.zeros((0, self.dim), dtype=np.float32),
            labels=np.array(labels, dtype=np.int64),
            names={eid: e.full_name for eid, e in emps.items()},
        )
        with self._gallery_lock:
            self._gallery = gal

    def identify(self, emb: np.ndarray) -> Tuple[Optional[int], float]:
        with self._gallery_lock:
            gal = self._gallery
        if gal.matrix.shape[0] == 0 or emb.shape[0] != gal.matrix.shape[1]:
            return None, 0.0  # bo'sh galereya yoki eski modeldagi vektor
        sims = gal.matrix @ emb
        best_per_emp: Dict[int, float] = {}
        for lab, sim in zip(gal.labels.tolist(), sims.tolist()):
            if sim > best_per_emp.get(lab, -1.0):
                best_per_emp[lab] = sim
        eid, sim = max(best_per_emp.items(), key=lambda kv: kv[1])
        second = max((v for k, v in best_per_emp.items() if k != eid), default=-1.0)
        if sim >= settings.FACE_MATCH_THRESHOLD and sim - second >= settings.FACE_MATCH_MARGIN:
            return eid, float(sim)
        return None, float(sim)

    def name_of(self, employee_id: Optional[int]) -> Optional[str]:
        if employee_id is None:
            return None
        with self._gallery_lock:
            return self._gallery.names.get(employee_id)

    # --------------------------------------------------------------- analysis
    def detect(self, img: np.ndarray) -> List[FaceResult]:
        if not self._ensure_loaded() or img is None:
            return []
        h, w = img.shape[:2]
        scale = 1.0
        work = img
        if max(h, w) > _DETECT_MAX_SIDE:
            scale = _DETECT_MAX_SIDE / max(h, w)
            work = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
        with self._lock:
            self._detector.setInputSize((work.shape[1], work.shape[0]))
            _, faces = self._detector.detect(work)
        results: List[FaceResult] = []
        if faces is None:
            return results
        for row in faces:
            row = row.copy()
            if scale != 1.0:
                row[:14] /= scale
            x, y, fw, fh = (int(round(v)) for v in row[:4])
            results.append(FaceResult(
                box=(max(0, x), max(0, y), fw, fh),
                score=float(row[14]),
                row=row,
                too_small=min(fw, fh) < settings.FACE_MIN_SIZE,
            ))
        return results

    def embed(self, img: np.ndarray, face: FaceResult) -> Optional[np.ndarray]:
        if not self._ensure_loaded():
            return None
        if self._arcface is not None:
            matrix, _ = cv2.estimateAffinePartial2D(face.row[4:14].reshape(5, 2).astype(np.float32), _ARCFACE_REF, method=cv2.LMEDS)
            if matrix is None:
                return None
            aligned = cv2.cvtColor(cv2.warpAffine(img, matrix, (112, 112), flags=cv2.INTER_CUBIC), cv2.COLOR_BGR2RGB)
            blob = (np.transpose(aligned, (2, 0, 1))[None].astype(np.float32) - 127.5) / 127.5
            feat = self._arcface.run(None, {self._arcface_input: blob})[0]
        else:
            with self._lock:
                aligned = self._recognizer.alignCrop(img, face.row)
                feat = self._recognizer.feature(aligned)
        v = feat.flatten().astype(np.float32)
        n = float(np.linalg.norm(v))
        return v / n if n > 0 else None

    def embed_crop(self, crop: np.ndarray) -> Optional[np.ndarray]:
        """Saqlangan yuz kesimidan vektor oladi (model almashganda qayta hisoblash uchun)."""
        k = max(1.0, 320 / max(crop.shape[:2]))
        up = cv2.resize(crop, None, fx=k, fy=k, interpolation=cv2.INTER_CUBIC)
        faces = self.detect(up)
        if not faces:
            return None
        return self.embed(up, max(faces, key=lambda f: f.box[2] * f.box[3]))

    def analyze(self, img: np.ndarray, identify: bool = True, channel: Optional[int] = None) -> List[FaceResult]:
        """channel ko'cha kamerasi bo'lsa, faqat tanilgan xodimlar qaytadi (o'tkinchilar notanish hisoblanmaydi)."""
        faces = self.detect(img)
        for f in faces:
            if f.too_small:
                continue
            f.embedding = self.embed(img, f)
            if identify and f.embedding is not None:
                f.employee_id, f.similarity = self.identify(f.embedding)
                f.name = self.name_of(f.employee_id)
        if channel in settings.street_channels:
            return [f for f in faces if f.known]
        return faces

    def analyze_jpeg(self, jpeg: bytes, identify: bool = True) -> Tuple[Optional[np.ndarray], List[FaceResult]]:
        img = decode_jpeg(jpeg)
        if img is None:
            return None, []
        return img, self.analyze(img, identify=identify)

    # ---------------------------------------------------------------- drawing
    def _font(self, size: int):
        if size not in self._font_cache:
            font = None
            for path in ("C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/arial.ttf",
                         "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
                try:
                    font = ImageFont.truetype(path, size)
                    break
                except OSError:
                    continue
            self._font_cache[size] = font or ImageFont.load_default()
        return self._font_cache[size]

    def annotate(self, img: np.ndarray, faces: List[FaceResult]) -> np.ndarray:
        if not faces:
            return img
        pil = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
        draw = ImageDraw.Draw(pil)
        lw = max(2, img.shape[1] // 480)
        font = self._font(max(14, img.shape[1] // 60))
        for f in faces:
            x, y, w, h = f.box
            if f.known:
                color, label = (52, 211, 153), f"{f.name} {int(f.similarity * 100)}%"
            elif f.too_small:
                color, label = (148, 163, 184), "kichik"
            else:
                color, label = (244, 63, 94), "Notanish"
            draw.rectangle([x, y, x + w, y + h], outline=color, width=lw)
            tb = draw.textbbox((0, 0), label, font=font)
            tw, th = tb[2] - tb[0], tb[3] - tb[1]
            ty = y - th - 8 if y - th - 8 > 0 else y + h + 2
            draw.rectangle([x, ty, x + tw + 10, ty + th + 8], fill=color)
            draw.text((x + 5, ty + 2), label, fill=(10, 10, 20), font=font)
        return cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)


# ---------------------------------------------------------------------- utils
def decode_jpeg(data: bytes) -> Optional[np.ndarray]:
    if not data:
        return None
    arr = np.frombuffer(data, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        try:
            pil = Image.open(io.BytesIO(data)).convert("RGB")
            img = cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)
        except Exception:
            return None
    return img


def encode_jpeg(img: np.ndarray, quality: int = 85, max_side: Optional[int] = None) -> bytes:
    if max_side and max(img.shape[:2]) > max_side:
        s = max_side / max(img.shape[:2])
        img = cv2.resize(img, (int(img.shape[1] * s), int(img.shape[0] * s)), interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, quality])
    return buf.tobytes() if ok else b""


def crop_face(img: np.ndarray, face: FaceResult, pad: float = 0.35) -> np.ndarray:
    x, y, w, h = face.box
    px, py = int(w * pad), int(h * pad)
    H, W = img.shape[:2]
    x1, y1 = max(0, x - px), max(0, y - py)
    x2, y2 = min(W, x + w + px), min(H, y + h + py)
    return img[y1:y2, x1:x2].copy()


def emb_to_bytes(v: np.ndarray) -> bytes:
    return np.asarray(v, dtype=np.float32).tobytes()


def bytes_to_emb(b: bytes) -> np.ndarray:
    return np.frombuffer(b, dtype=np.float32)


face_engine = FaceEngine()


def ensure_models_async() -> None:
    def _run():
        if not face_engine.available:
            download_models()
            if face_engine.available:
                face_engine.reload_gallery()
    threading.Thread(target=_run, name="face-model-download", daemon=True).start()
