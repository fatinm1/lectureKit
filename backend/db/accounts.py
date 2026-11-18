"""
Purpose: Users, sessions and the per-user library, on the same Postgres pool as everything else.

- Passwords: argon2id (argon2-cffi defaults), verified in constant time. Unknown emails are still
  checked against a dummy hash, so a login's timing doesn't reveal whether an account exists.
- Sessions: a random 256-bit bearer token goes to the client; only its SHA-256 is stored.
  Sessions last 30 days. Logout deletes the row; changing the password ends every other session.
- Library: one row per saved result with a snapshot of its payload. Sharing sets an unguessable
  token; revoking clears it, so old links stop working at once.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

SESSION_DAYS = 30
_hasher = PasswordHasher()
_DUMMY_HASH = _hasher.hash("timing-equalizer-not-a-real-password")


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


@dataclass(frozen=True)
class User:
    id: str
    email: str
    created_at: datetime

    def public(self) -> dict[str, Any]:
        return {"id": self.id, "email": self.email, "created_at": self.created_at.isoformat()}


class EmailTaken(Exception):
    pass


class Accounts:
    def __init__(self, store: Any) -> None:
        self.pool = store.pool

    # ---------- users ----------

    def create_user(self, email: str, password: str) -> User:
        email = normalize_email(email)
        pw_hash = _hasher.hash(password)
        with self.pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """INSERT INTO users (id, email, password_hash) VALUES (%s, %s, %s)
                   ON CONFLICT (email) DO NOTHING RETURNING id, email, created_at""",
                (uuid.uuid4().hex, email, pw_hash),
            )
            row = cur.fetchone()
        if row is None:
            raise EmailTaken(email)
        return User(**row)

    def authenticate(self, email: str, password: str) -> Optional[User]:
        with self.pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT id, email, created_at, password_hash FROM users WHERE email = %s",
                (normalize_email(email),),
            )
            row = cur.fetchone()
        try:
            _hasher.verify(row["password_hash"] if row else _DUMMY_HASH, password)
        except (VerificationError, InvalidHashError):
            return None
        if row is None:
            return None
        if _hasher.check_needs_rehash(row["password_hash"]):
            self._set_password(row["id"], password)
        return User(id=row["id"], email=row["email"], created_at=row["created_at"])

    def _set_password(self, user_id: str, password: str) -> None:
        with self.pool.connection() as conn:
            conn.execute("UPDATE users SET password_hash = %s WHERE id = %s", (_hasher.hash(password), user_id))

    def change_password(self, user: User, current: str, new: str, keep_token: str) -> bool:
        if self.authenticate(user.email, current) is None:
            return False
        self._set_password(user.id, new)
        with self.pool.connection() as conn:  # sign out everywhere else
            conn.execute(
                "DELETE FROM sessions WHERE user_id = %s AND token_hash <> %s", (user.id, _token_hash(keep_token))
            )
        return True

    def delete_user(self, user: User, password: str) -> bool:
        if self.authenticate(user.email, password) is None:
            return False
        with self.pool.connection() as conn:  # sessions + library go with it (ON DELETE CASCADE)
            conn.execute("DELETE FROM users WHERE id = %s", (user.id,))
        return True

    # ---------- sessions ----------

    def create_session(self, user: User) -> str:
        token = secrets.token_urlsafe(32)
        expires = datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS)
        with self.pool.connection() as conn:
            conn.execute(
                "INSERT INTO sessions (token_hash, user_id, expires_at) VALUES (%s, %s, %s)",
                (_token_hash(token), user.id, expires),
            )
        return token

    def user_for_token(self, token: str) -> Optional[User]:
        if not token:
            return None
        with self.pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """SELECT u.id, u.email, u.created_at FROM sessions s JOIN users u ON u.id = s.user_id
                   WHERE s.token_hash = %s AND s.expires_at > now()""",
                (_token_hash(token),),
            )
            row = cur.fetchone()
        return User(**row) if row else None

    def delete_session(self, token: str) -> None:
        with self.pool.connection() as conn:
            conn.execute("DELETE FROM sessions WHERE token_hash = %s", (_token_hash(token),))

    # ---------- library ----------

    def save_item(
        self, user: User, *, job_id: str, kind: str, video_id: Optional[str], title: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        """Idempotent per (user, job): saving the same job twice returns the existing item."""
        with self.pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """INSERT INTO library_items (id, user_id, job_id, kind, video_id, title, payload)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (user_id, job_id) DO UPDATE SET job_id = EXCLUDED.job_id
                   RETURNING id, kind, video_id, title, share_token, created_at""",
                (uuid.uuid4().hex[:16], user.id, job_id, kind, video_id, title[:200], Jsonb(payload)),
            )
            return _item_summary(cur.fetchone())

    def list_items(self, user: User, limit: int = 200) -> list[dict[str, Any]]:
        with self.pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """SELECT id, kind, video_id, title, share_token, created_at FROM library_items
                   WHERE user_id = %s ORDER BY created_at DESC LIMIT %s""",
                (user.id, limit),
            )
            return [_item_summary(r) for r in cur.fetchall()]

    def get_item(self, user: User, item_id: str) -> Optional[dict[str, Any]]:
        with self.pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """SELECT id, kind, video_id, title, share_token, created_at, payload FROM library_items
                   WHERE user_id = %s AND id = %s""",
                (user.id, item_id),
            )
            row = cur.fetchone()
        if row is None:
            return None
        return {**_item_summary(row), "payload": row["payload"]}

    def rename_item(self, user: User, item_id: str, title: str) -> Optional[dict[str, Any]]:
        return self._update(user, item_id, "title = %s", (title.strip()[:200],))

    def delete_item(self, user: User, item_id: str) -> bool:
        with self.pool.connection() as conn:
            cur = conn.execute("DELETE FROM library_items WHERE user_id = %s AND id = %s", (user.id, item_id))
            return cur.rowcount > 0

    def share_item(self, user: User, item_id: str) -> Optional[dict[str, Any]]:
        """Keeps an existing token (so a link already sent keeps working); makes one otherwise."""
        return self._update(
            user, item_id, "share_token = COALESCE(share_token, %s), shared_at = COALESCE(shared_at, now())",
            (secrets.token_urlsafe(16),),
        )

    def unshare_item(self, user: User, item_id: str) -> Optional[dict[str, Any]]:
        return self._update(user, item_id, "share_token = NULL, shared_at = NULL", ())

    def _update(self, user: User, item_id: str, set_sql: str, params: tuple) -> Optional[dict[str, Any]]:
        with self.pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                f"""UPDATE library_items SET {set_sql} WHERE user_id = %s AND id = %s
                    RETURNING id, kind, video_id, title, share_token, created_at""",
                (*params, user.id, item_id),
            )
            row = cur.fetchone()
        return _item_summary(row) if row else None

    def shared(self, token: str) -> Optional[dict[str, Any]]:
        """A shared item for anyone with the link: content only, nothing about the owner."""
        if not token:
            return None
        with self.pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT kind, video_id, title, payload, created_at FROM library_items WHERE share_token = %s",
                (token,),
            )
            row = cur.fetchone()
        if row is None:
            return None
        return {
            "kind": row["kind"],
            "video_id": row["video_id"],
            "title": row["title"],
            "payload": row["payload"],
            "created_at": row["created_at"].isoformat(),
        }


def _item_summary(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "kind": row["kind"],
        "video_id": row["video_id"],
        "title": row["title"],
        "shared": row["share_token"] is not None,
        "share_token": row["share_token"],
        "created_at": row["created_at"].isoformat(),
    }
