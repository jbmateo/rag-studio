import sqlite3
from collections.abc import Iterator

from fastapi import Depends, HTTPException, Request
from pydantic import BaseModel

from app.auth.sessions import resolve_session
from app.db import connect

COOKIE_NAME = "session"


class User(BaseModel):
    id: str
    email: str


def get_conn(request: Request) -> Iterator[sqlite3.Connection]:
    conn = connect(request.app.state.settings.database_path)
    try:
        yield conn
    finally:
        conn.close()


def current_user(request: Request, conn: sqlite3.Connection = Depends(get_conn)) -> User:
    token = request.cookies.get(COOKIE_NAME)
    user_id = resolve_session(conn, token) if token else None
    row = (
        conn.execute("select id, email from users where id=?", (user_id,)).fetchone()
        if user_id
        else None
    )
    if row is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return User(id=row["id"], email=row["email"])
