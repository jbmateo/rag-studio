import re
import sqlite3
import time
import uuid
from collections import deque

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, field_validator

from app.auth.deps import COOKIE_NAME, User, current_user, get_conn, set_session_cookie
from app.auth.passwords import hash_password, verify_password
from app.auth.sessions import create_session, delete_session

router = APIRouter(prefix="/api/auth")

LOGIN_LIMIT = 5
LOGIN_WINDOW_S = 60
BAD_LOGIN = "Invalid email or password"
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
# Verified against when the email is unknown, so timing doesn't reveal account existence.
_DUMMY_HASH = hash_password("dummy-password")


class Credentials(BaseModel):
    email: str
    password: str
    remember: bool = True

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, v: str) -> str:
        v = v.strip().lower()
        if not _EMAIL_RE.match(v):
            raise ValueError("invalid email")
        return v


class SignupBody(Credentials):
    @field_validator("password")
    @classmethod
    def _min_length(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("password must be at least 8 characters")
        if len(v.encode()) > 72:  # bcrypt limit
            raise ValueError("password must be at most 72 bytes")
        return v


def _check_rate_limit(request: Request) -> None:
    attempts: dict[str, deque] = request.app.state.login_attempts
    ip = request.client.host if request.client else "unknown"
    now = time.monotonic()
    for key in list(attempts):
        old = attempts[key]
        while old and now - old[0] > LOGIN_WINDOW_S:
            old.popleft()
        if not old:
            del attempts[key]
    q = attempts.setdefault(ip, deque())
    if len(q) >= LOGIN_LIMIT:
        raise HTTPException(status_code=429, detail="Too many login attempts. Try again in a minute.")
    q.append(now)


@router.post("/signup", status_code=201, response_model=User)
def signup(body: SignupBody, request: Request, response: Response, conn: sqlite3.Connection = Depends(get_conn)):
    user_id = uuid.uuid4().hex
    try:
        conn.execute(
            "insert into users(id, email, password_hash) values(?,?,?)",
            (user_id, body.email, hash_password(body.password)),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail="Email already registered")
    set_session_cookie(request, response, create_session(conn, user_id, body.remember), body.remember)
    return User(id=user_id, email=body.email)


@router.post("/login", response_model=User)
def login(body: Credentials, request: Request, response: Response, conn: sqlite3.Connection = Depends(get_conn)):
    _check_rate_limit(request)
    row = conn.execute("select id, email, password_hash from users where email=?", (body.email,)).fetchone()
    ok = verify_password(body.password, row["password_hash"] if row else _DUMMY_HASH)
    if row is None or not ok:
        raise HTTPException(status_code=401, detail=BAD_LOGIN)
    set_session_cookie(request, response, create_session(conn, row["id"], body.remember), body.remember)
    return User(id=row["id"], email=row["email"])


@router.post("/logout", status_code=204)
def logout(request: Request, conn: sqlite3.Connection = Depends(get_conn)):
    token = request.cookies.get(COOKIE_NAME)
    if token:
        delete_session(conn, token)
    response = Response(status_code=204)
    response.delete_cookie(COOKIE_NAME, httponly=True, samesite="lax", secure=request.app.state.settings.cookie_secure)
    return response


@router.get("/me", response_model=User)
def me(user: User = Depends(current_user)):
    return user
