def test_signup_sets_persistent_cookie_and_me_works(client):
    r = client.post("/api/auth/signup", json={"email": "a@x.io", "password": "password1"})
    assert r.status_code == 201
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie and "max-age=2592000" in cookie
    assert client.get("/api/auth/me").json()["email"] == "a@x.io"


def test_login_without_remember_sets_session_cookie(client, signup):
    signup("a@x.io")
    client.cookies.clear()
    r = client.post("/api/auth/login", json={"email": "a@x.io", "password": "password1", "remember": False})
    assert "max-age" not in r.headers["set-cookie"].lower()


def test_bad_credentials_uniform_message(client, signup):
    signup("a@x.io")
    for body in ({"email": "a@x.io", "password": "wrongpass"}, {"email": "no@x.io", "password": "password1"}):
        r = client.post("/api/auth/login", json=body)
        assert r.status_code == 401 and r.json()["detail"] == "Invalid email or password"


def test_login_rate_limited_after_5_attempts(client):
    codes = [
        client.post("/api/auth/login", json={"email": "n@x.io", "password": "password1"}).status_code
        for _ in range(6)
    ]
    assert codes[:5] == [401] * 5 and codes[5] == 429


def test_logout_invalidates_session(client, signup):
    signup("a@x.io")
    client.post("/api/auth/logout")
    assert client.get("/api/auth/me").status_code == 401


def test_session_token_stored_hashed(client, conn, signup):
    signup("a@x.io")
    raw = client.cookies["session"]
    assert conn.execute("select count(*) from sessions where token_hash=?", (raw,)).fetchone()[0] == 0


def test_expired_session_rejected(client, conn, signup):
    signup("a@x.io")
    conn.execute("update sessions set expires_at='2000-01-01T00:00:00+00:00'")
    conn.commit()
    assert client.get("/api/auth/me").status_code == 401


def test_short_password_and_duplicate_email(client, signup):
    assert client.post("/api/auth/signup", json={"email": "b@x.io", "password": "short"}).status_code == 422
    signup("a@x.io")
    assert client.post("/api/auth/signup", json={"email": "a@x.io", "password": "password1"}).status_code == 409


def test_me_reissues_persistent_cookie_for_remember_session(client, signup):
    signup("a@x.io")
    r = client.get("/api/auth/me")
    assert "max-age=2592000" in r.headers["set-cookie"].lower()


def test_me_does_not_set_max_age_for_non_remember_session(client, signup):
    signup("a@x.io")
    client.cookies.clear()
    client.post("/api/auth/login", json={"email": "a@x.io", "password": "password1", "remember": False})
    r = client.get("/api/auth/me")
    assert r.status_code == 200
    assert "max-age" not in r.headers.get("set-cookie", "").lower()


def test_overlong_password_rejected_not_500(client):
    for pw in ("a" * 100, "é" * 40):  # 100 bytes; 40 chars but 80 bytes
        r = client.post("/api/auth/signup", json={"email": "b@x.io", "password": pw})
        assert r.status_code == 422


def test_rate_limiter_drops_idle_ips(client):
    client.post("/api/auth/login", json={"email": "n@x.io", "password": "password1"})
    attempts = client.app.state.login_attempts
    for q in attempts.values():
        q.clear()
    client.post("/api/auth/login", json={"email": "n@x.io", "password": "password1"})
    assert len(attempts) == 1
