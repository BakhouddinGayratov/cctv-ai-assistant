"""
Hikvision ISAPI klienti (HTTP Digest/Basic):
- NVR HDD'dagi yozuv bo'laklarini qidirish (kun chizig'i uchun, harakat yozuvlarini ajratib).
- PTZ: uzluksiz harakat, to'xtatish, presetlar (NVR proksi orqali).
"""

from __future__ import annotations

import re
import time
import urllib.error
import urllib.request
import uuid
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional, Tuple

from config import settings
from rtsp_manager import nvr_online

_opener: Optional[urllib.request.OpenerDirector] = None
_ptz_cache: Dict[int, Tuple[float, bool]] = {}


def _get_opener() -> urllib.request.OpenerDirector:
    global _opener
    if _opener is None:
        base = f"http://{settings.NVR_IP}:{settings.NVR_HTTP_PORT}/"
        pm = urllib.request.HTTPPasswordMgrWithDefaultRealm()
        pm.add_password(None, base, settings.NVR_USER, settings.NVR_PASSWORD)
        _opener = urllib.request.build_opener(urllib.request.HTTPDigestAuthHandler(pm), urllib.request.HTTPBasicAuthHandler(pm))
    return _opener


def _request(method: str, path: str, body: Optional[str] = None, timeout: float = 8) -> Tuple[int, str]:
    url = f"http://{settings.NVR_IP}:{settings.NVR_HTTP_PORT}{path}"
    req = urllib.request.Request(url, data=body.encode() if body else None, method=method,
                                 headers={"Content-Type": "application/xml"} if body else {})
    try:
        with _get_opener().open(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace") if e.fp else ""
    except (urllib.error.URLError, OSError) as e:  # NVR o'chiq / tarmoq uzilgan
        return 0, str(e)


def _strip_ns(xml: str) -> ET.Element:
    return ET.fromstring(re.sub(r'\sxmlns(:\w+)?="[^"]+"', "", xml, count=0))


# ----------------------------------------------------------------------------- yozuvlar qidiruvi
def search_recordings(channel: int, day: str) -> Optional[List[dict]]:
    """Kun bo'yicha yozuv bo'laklari: [{start, end, type}] (type: continuous | motion | event). None — NVR javob bermadi."""
    if not nvr_online():
        return None
    out: List[dict] = []
    pos = 0
    sid = str(uuid.uuid4()).upper()
    for _ in range(20):
        body = (
            '<?xml version="1.0" encoding="UTF-8"?><CMSearchDescription>'
            f"<searchID>{sid}</searchID><trackList><trackID>{channel}01</trackID></trackList>"
            f"<timeSpanList><timeSpan><startTime>{day}T00:00:00Z</startTime><endTime>{day}T23:59:59Z</endTime></timeSpan></timeSpanList>"
            f"<maxResults>200</maxResults><searchResultPostion>{pos}</searchResultPostion>"
            "<metadataList><metadataDescriptor>//recordType.meta.std-cgi.com</metadataDescriptor></metadataList>"
            "</CMSearchDescription>"
        )
        status, text = _request("POST", "/ISAPI/ContentMgmt/search", body, timeout=12)
        if status != 200:
            return out or None
        try:
            root = _strip_ns(text)
        except ET.ParseError:
            return out or None
        items = root.findall(".//searchMatchItem")
        for it in items:
            st, en = it.findtext(".//startTime"), it.findtext(".//endTime")
            meta = (it.findtext(".//metadataDescriptor") or "").lower()
            kind = "motion" if "motion" in meta else ("continuous" if ("timing" in meta or "continuous" in meta or not meta) else "event")
            if st and en:
                out.append({"start": st.rstrip("Z")[:19], "end": en.rstrip("Z")[:19], "type": kind})
        pos += len(items)
        if (root.findtext(".//responseStatusStrg") or "").upper() != "MORE" or not items:
            break
    return out


# ----------------------------------------------------------------------------- PTZ
def ptz_supported(channel: int) -> bool:
    cached = _ptz_cache.get(channel)
    if cached and time.time() - cached[0] < 600:
        return cached[1]
    ok = False
    if nvr_online():
        status, text = _request("GET", f"/ISAPI/ContentMgmt/PTZCtrlProxy/channels/{channel}/capabilities", timeout=5)
        ok = status == 200 and ("PTZChanelCap" in text or "PTZChannelCap" in text)
    _ptz_cache[channel] = (time.time(), ok)
    return ok


def ptz_move(channel: int, pan: int, tilt: int, zoom: int) -> bool:
    """pan/tilt/zoom: -100..100 (0 = to'xtatish)."""
    if not nvr_online():
        return False
    clamp = lambda v: max(-100, min(100, int(v)))
    body = f"<PTZData><pan>{clamp(pan)}</pan><tilt>{clamp(tilt)}</tilt><zoom>{clamp(zoom)}</zoom></PTZData>"
    status, _ = _request("PUT", f"/ISAPI/ContentMgmt/PTZCtrlProxy/channels/{channel}/continuous", body, timeout=4)
    return status == 200


def ptz_stop(channel: int) -> bool:
    return ptz_move(channel, 0, 0, 0)


def ptz_presets(channel: int) -> List[dict]:
    status, text = _request("GET", f"/ISAPI/ContentMgmt/PTZCtrlProxy/channels/{channel}/presets", timeout=5)
    if status != 200:
        return []
    try:
        root = _strip_ns(text)
    except ET.ParseError:
        return []
    out = []
    for p in root.findall(".//PTZPreset"):
        pid = p.findtext("id")
        if pid and (p.findtext("enabled") or "true").lower() == "true":
            out.append({"id": int(pid), "name": p.findtext("presetName") or f"Preset {pid}"})
    return out


def ptz_goto(channel: int, preset_id: int) -> bool:
    if not nvr_online():
        return False
    status, _ = _request("PUT", f"/ISAPI/ContentMgmt/PTZCtrlProxy/channels/{channel}/presets/{preset_id}/goto", timeout=5)
    return status == 200

