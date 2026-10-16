import sqlite3
from collections.abc import Iterator

from fastapi import Depends, HTTPException, Request, Response
from pydantic import BaseModel

from app.auth.sessions import resolve_session_ex
from app.db import connect

COOKIE_NAME = "session"
COOKIE_MAX_AGE = 30 * 24 * 3600


def set_session_cookie(request: Request, response: Response, token: str, remember: bool) -> None:
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=COOKIE_MAX_AGE if remember else None,
        httponly=True,
        samesite="lax",
        secure=request.app.state.settings.cookie_secure,
    )


class User(BaseModel):
    id: str
    email: str


def get_conn(request: Request) -> Iterator[sqlite3.Connection]:
    conn = connect(request.app.state.settings.database_path)
    try:
        yield conn
    finally:
        conn.close()


def current_user(request: Request, response: Response, conn: sqlite3.Connection = Depends(get_conn)) -> User:
    token = request.cookies.get(COOKIE_NAME)
    found = resolve_session_ex(conn, token) if token else None
    user_id = found[0] if found else None
    row = (
        conn.execute("select id, email from users where id=?", (user_id,)).fetchone()
        if user_id
        else None
    )
    if row is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    if found[1]:  # remember-me: re-issue the cookie so the browser-side expiry slides too
        set_session_cookie(request, response, token, True)
    return User(id=row["id"], email=row["email"])
