"""
Kirish va rollar: xojayin (boss) va admin. Sessiya imzolangan kukida, serverda saqlanmaydi.

/api, /media, /clips faqat kirgan foydalanuvchiga ochiq. Telegram bot X-Kamera-Kalit sarlavhasi bilan kiradi.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from http.cookies import SimpleCookie
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from config import settings

COOKIE = "cctv_session"
MAX_AGE = 30 * 24 * 3600
_ROLES = {"boss", "admin"}
_ADMIN_ONLY = ("/api/rooms", "/api/settings", "/api/system", "/api/model/status", "/api/workers/force", "/api/desk/check-now",
               "/api/index/run", "/api/agent/run", "/api/alerts/test", "/api/faces", "/api/sightings")


def _signature(body: str) -> str:
    return hmac.new(settings.AUTH_SECRET.encode(), body.encode(), hashlib.sha256).hexdigest()


def make_token(role: str, now: Optional[float] = None) -> str:
    body = f"{role}.{int((now or time.time()) + MAX_AGE)}"
    return f"{body}.{_signature(body)}"


def role_from_token(token: str) -> Optional[str]:
    if not settings.AUTH_SECRET:
        return None
    body, _, signature = token.rpartition(".")
    role, _, expires = body.partition(".")
    if not hmac.compare_digest(signature, _signature(body)) or role not in _ROLES or not expires.isdigit():
        return None
    return role if int(expires) > time.time() else None


def admin_only(method: str, path: str) -> bool:
    if path.startswith(_ADMIN_ONLY):
        return True
    return path.startswith("/api/employees") and (method != "GET" or "/faces" in path)


def _request_role(scope) -> Optional[str]:
    headers = {k.decode("latin-1"): v.decode("latin-1") for k, v in scope["headers"]}
    key = headers.get("x-kamera-kalit", "")
    if settings.BOT_API_KEY and hmac.compare_digest(key.encode(), settings.BOT_API_KEY.encode()):
        return "boss"
    jar = SimpleCookie()
    try:
        jar.load(headers.get("cookie", ""))
    except Exception:
        return None
    return role_from_token(jar[COOKIE].value) if COOKIE in jar else None


class AuthMiddleware:
    """Sof ASGI: BaseHTTPMiddleware MJPEG/SSE oqimlari uzilishini kechiktiradi."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http" or not scope["path"].startswith(("/api/", "/media/", "/clips/")) \
                or scope["path"] == "/api/auth/login":
            return await self.app(scope, receive, send)
        role = _request_role(scope)
        if role is None:
            return await self._deny(send, 401, "Tizimga kiring")
        if role != "admin" and admin_only(scope["method"], scope["path"]):
            return await self._deny(send, 403, "Bu bo'lim faqat admin uchun")
        scope.setdefault("state", {})["role"] = role
        await self.app(scope, receive, send)

    @staticmethod
    async def _deny(send, status: int, detail: str) -> None:
        body = json.dumps({"detail": detail}, ensure_ascii=False).encode()
        await send({"type": "http.response.start", "status": status,
                    "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]})
        await send({"type": "http.response.body", "body": body})


router = APIRouter(prefix="/api/auth")


class LoginIn(BaseModel):
    login: str
    password: str


@router.post("/login")
def login(body: LoginIn, response: Response):
    # shortcut: parollar .env da ochiq (NVR paroli kabi), foydalanuvchilar ko'paysa bazada xeshlash kerak
    expected = {"admin": ("admin", settings.ADMIN_PASSWORD), "xojayin": ("boss", settings.BOSS_PASSWORD)}.get(body.login.strip().lower())
    if not (settings.AUTH_SECRET and expected and expected[1]
            and hmac.compare_digest(body.password.encode(), expected[1].encode())):
        time.sleep(1)  # parol tanlashni sekinlashtiradi
        raise HTTPException(status_code=401, detail="Login yoki parol noto'g'ri")
    response.set_cookie(COOKIE, make_token(expected[0]), max_age=MAX_AGE, httponly=True, samesite="lax", path="/")
    return {"role": expected[0]}


@router.get("/me")
def me(request: Request):
    return {"role": request.state.role}


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(COOKIE, path="/")
    return {"status": "ok"}
