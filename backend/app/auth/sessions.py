import hashlib
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone

REMEMBER_TTL = timedelta(days=30)
SESSION_TTL = timedelta(hours=24)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(conn: sqlite3.Connection, user_id: str, remember: bool) -> str:
    token = secrets.token_urlsafe(32)
    expires = _now() + (REMEMBER_TTL if remember else SESSION_TTL)
    conn.execute(
        "insert into sessions(token_hash, user_id, expires_at, remember) values(?,?,?,?)",
        (_hash(token), user_id, expires.isoformat(), int(remember)),
    )
    conn.commit()
    return token


def resolve_session(conn: sqlite3.Connection, token: str) -> str | None:
    found = resolve_session_ex(conn, token)
    return found[0] if found else None


def resolve_session_ex(conn: sqlite3.Connection, token: str) -> tuple[str, bool] | None:
    """Like resolve_session, but also reports whether the session is a remember-me one."""
    now = _now()
    conn.execute("delete from sessions where expires_at <= ?", (now.isoformat(),))
    row = conn.execute(
        "select user_id, remember from sessions where token_hash=?", (_hash(token),)
    ).fetchone()
    if row is None:
        conn.commit()
        return None
    if row["remember"]:
        conn.execute(
            "update sessions set expires_at=? where token_hash=?",
            ((now + REMEMBER_TTL).isoformat(), _hash(token)),
        )
    conn.commit()
    return row["user_id"], bool(row["remember"])


def delete_session(conn: sqlite3.Connection, token: str) -> None:
    conn.execute("delete from sessions where token_hash=?", (_hash(token),))
    conn.commit()
