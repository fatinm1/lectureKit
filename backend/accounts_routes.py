"""
Purpose: Accounts (email + password), the personal library and read-only share links.

Auth is a bearer token (`Authorization: Bearer <token>`), not a cookie: the frontend (Vercel) and
API (Railway) are on different sites, where browsers increasingly block third-party cookies.

  POST   /auth/signup           {email, password}            → {token, user}
  POST   /auth/login            {email, password}            → {token, user}
  POST   /auth/logout                                         → 204
  GET    /auth/me                                             → {user}
  POST   /auth/password         {current_password, new_password} → 204 (other sessions end)
  DELETE /auth/account          {password}                    → 204 (library goes too)

  GET    /library                                             → {items: [...]}
  POST   /library               {job_id}                      → item (a finished job, snapshotted)
  GET    /library/{id}                                        → item + payload
  PATCH  /library/{id}          {title}                       → item
  DELETE /library/{id}                                        → 204
  POST   /library/{id}/share                                  → item with share_token
  DELETE /library/{id}/share                                  → item, link revoked

  GET    /shared/{token}                                      → {kind, title, payload, ...}

Login and signup are rate limited per IP (limits.py, AUTH_RATE_LIMIT_PER_HOUR).
Everything here needs Postgres; without DATABASE_URL these return 503.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any, Optional

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from pydantic import BaseModel, Field

import services
from db.accounts import Accounts, EmailTaken, User
from jobs.events import JobEventBus

logger = logging.getLogger("lecturekit.accounts")

router = APIRouter()

MIN_PASSWORD = 8
MAX_PASSWORD = 128
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def accounts() -> Accounts:
    if services.store is None:
        raise HTTPException(status_code=503, detail="Accounts aren't available on this server (no database).")
    return Accounts(services.store)


def _bearer(authorization: Optional[str]) -> str:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return ""


def current_user(authorization: Optional[str] = Header(default=None)) -> User:
    user = accounts().user_for_token(_bearer(authorization))
    if user is None:
        raise HTTPException(status_code=401, detail="Please sign in again.")
    return user


# ---------- auth ----------


class Credentials(BaseModel):
    email: str
    password: str


class PasswordChange(BaseModel):
    current_password: str
    new_password: str


class PasswordConfirm(BaseModel):
    password: str


def _check_password(pw: str) -> None:
    if len(pw) < MIN_PASSWORD:
        raise HTTPException(status_code=422, detail=f"Password must be at least {MIN_PASSWORD} characters.")
    if len(pw) > MAX_PASSWORD:
        raise HTTPException(status_code=422, detail=f"Password must be at most {MAX_PASSWORD} characters.")


@router.post("/auth/signup", status_code=201)
def signup(body: Credentials) -> dict[str, Any]:
    email = body.email.strip()
    if not _EMAIL.match(email) or len(email) > 254:
        raise HTTPException(status_code=422, detail="Enter a valid email address.")
    _check_password(body.password)
    acc = accounts()
    try:
        user = acc.create_user(email, body.password)
    except EmailTaken:
        raise HTTPException(status_code=409, detail="An account with this email already exists. Sign in instead.")
    logger.info("signup", extra={"user_id": user.id})
    return {"token": acc.create_session(user), "user": user.public()}


@router.post("/auth/login")
def login(body: Credentials) -> dict[str, Any]:
    acc = accounts()
    user = acc.authenticate(body.email, body.password[:MAX_PASSWORD])
    if user is None:
        raise HTTPException(status_code=401, detail="Email or password is incorrect.")
    return {"token": acc.create_session(user), "user": user.public()}


@router.post("/auth/logout", status_code=204)
def logout(authorization: Optional[str] = Header(default=None)) -> Response:
    token = _bearer(authorization)
    if token:
        accounts().delete_session(token)
    return Response(status_code=204)


@router.get("/auth/me")
def me(user: User = Depends(current_user)) -> dict[str, Any]:
    return {"user": user.public()}


@router.post("/auth/password", status_code=204)
def change_password(
    body: PasswordChange, user: User = Depends(current_user), authorization: Optional[str] = Header(default=None)
) -> Response:
    _check_password(body.new_password)
    if not accounts().change_password(user, body.current_password, body.new_password, _bearer(authorization)):
        raise HTTPException(status_code=403, detail="Current password is incorrect.")
    return Response(status_code=204)


@router.delete("/auth/account", status_code=204)
def delete_account(body: PasswordConfirm, user: User = Depends(current_user)) -> Response:
    if not accounts().delete_user(user, body.password):
        raise HTTPException(status_code=403, detail="Password is incorrect.")
    logger.info("account deleted", extra={"user_id": user.id})
    return Response(status_code=204)


# ---------- library ----------


class SaveRequest(BaseModel):
    job_id: str = Field(..., min_length=8, max_length=64)


class RenameRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)


def _youtube_title(video_id: str) -> Optional[str]:
    """Best effort: YouTube's oEmbed has the real title. Any failure → None (caller falls back)."""
    try:
        r = httpx.get(
            "https://www.youtube.com/oembed",
            params={"url": f"https://www.youtube.com/watch?v={video_id}", "format": "json"},
            timeout=2.5,
        )
        if r.status_code == 200:
            title = str(r.json().get("title") or "").strip()
            return title or None
    except Exception:
        pass
    return None


def title_for(kind: str, result: dict[str, Any]) -> str:
    if kind == "provost":
        n = int(result.get("lecture_count") or len(result.get("video_ids") or []) or 0)
        return f"Curriculum map · {n} lecture{'s' if n != 1 else ''}"
    video_id = str(result.get("video_id") or "")
    name = _youtube_title(video_id) if video_id else None
    if not name and kind == "student":
        outline = result.get("outline") or []
        name = (outline[0].get("title") if outline and isinstance(outline[0], dict) else None) or None
    name = name or f"Lecture {video_id}"
    return f"Audit · {name}" if kind == "faculty" else name


@router.post("/library", status_code=201)
async def save_to_library(body: SaveRequest, request: Request, user: User = Depends(current_user)) -> dict[str, Any]:
    pool = getattr(request.app.state, "arq", None)
    if pool is None:
        raise HTTPException(status_code=503, detail="Saving needs background jobs (Redis) on this server.")
    job = await JobEventBus(pool).get(body.job_id)
    if not job:
        raise HTTPException(status_code=404, detail="That run has expired. Process the lecture again to save it.")
    if job.get("status") != "done" or not job.get("result"):
        raise HTTPException(status_code=409, detail="Only finished runs can be saved.")
    kind = str(job.get("kind") or "")
    result = job["result"]
    video_id = result.get("video_id") if kind != "provost" else None
    title = await asyncio.to_thread(title_for, kind, result)
    return await asyncio.to_thread(
        accounts().save_item, user, job_id=body.job_id, kind=kind, video_id=video_id, title=title, payload=result
    )


@router.get("/library")
def list_library(user: User = Depends(current_user)) -> dict[str, Any]:
    return {"items": accounts().list_items(user)}


def _found(item: Optional[dict[str, Any]]) -> dict[str, Any]:
    if item is None:
        raise HTTPException(status_code=404, detail="Not found in your library.")
    return item


@router.get("/library/{item_id}")
def get_library_item(item_id: str, user: User = Depends(current_user)) -> dict[str, Any]:
    return _found(accounts().get_item(user, item_id))


@router.patch("/library/{item_id}")
def rename_library_item(item_id: str, body: RenameRequest, user: User = Depends(current_user)) -> dict[str, Any]:
    if not body.title.strip():
        raise HTTPException(status_code=422, detail="Title can't be empty.")
    return _found(accounts().rename_item(user, item_id, body.title))


@router.delete("/library/{item_id}", status_code=204)
def delete_library_item(item_id: str, user: User = Depends(current_user)) -> Response:
    if not accounts().delete_item(user, item_id):
        raise HTTPException(status_code=404, detail="Not found in your library.")
    return Response(status_code=204)


@router.post("/library/{item_id}/share")
def share_library_item(item_id: str, user: User = Depends(current_user)) -> dict[str, Any]:
    return _found(accounts().share_item(user, item_id))


@router.delete("/library/{item_id}/share")
def unshare_library_item(item_id: str, user: User = Depends(current_user)) -> dict[str, Any]:
    return _found(accounts().unshare_item(user, item_id))


# ---------- public share links ----------


@router.get("/shared/{token}")
def get_shared(token: str, response: Response) -> dict[str, Any]:
    item = accounts().shared(token) if len(token) <= 64 else None
    if item is None:
        raise HTTPException(status_code=404, detail="This link doesn't work. It may have been turned off by its owner.")
    response.headers["X-Robots-Tag"] = "noindex"
    response.headers["Cache-Control"] = "no-store"
    return item
