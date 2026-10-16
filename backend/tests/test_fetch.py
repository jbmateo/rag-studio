import httpx
import pytest

from app.ingest.fetch import UnsafeURLError, fetch_url
from app.ingest.parsers import ParseError
from tests.fixtures import fake_resolver, real_ip_resolver

PUBLIC = fake_resolver({"public.example": "93.184.216.34"})


@pytest.mark.parametrize(
    "url",
    ["ftp://x.io/a", "file:///etc/passwd", "http://127.0.0.1/", "http://10.0.0.5/", "http://169.254.169.254/", "http://[::1]/"],
)
def test_rejects_unsafe_urls(url):
    with pytest.raises(UnsafeURLError):
        fetch_url(url, resolver=real_ip_resolver)


def test_rejects_host_resolving_to_private():
    resolver = fake_resolver({"evil.example": "10.1.2.3"})
    with pytest.raises(UnsafeURLError):
        fetch_url("http://evil.example/", resolver=resolver, transport=httpx.MockTransport(lambda r: httpx.Response(200)))


def test_rejects_if_any_resolved_address_is_private():
    def resolver(host, port=None, *a, **k):
        return fake_resolver({"h.example": "93.184.216.34"})(host, port) + fake_resolver({"h.example": "127.0.0.1"})(host, port)

    with pytest.raises(UnsafeURLError):
        fetch_url("http://h.example/", resolver=resolver, transport=httpx.MockTransport(lambda r: httpx.Response(200)))


def test_rejects_unresolvable_host():
    with pytest.raises(UnsafeURLError):
        fetch_url("http://nope.example/", resolver=PUBLIC, transport=httpx.MockTransport(lambda r: httpx.Response(200)))


def test_rejects_redirect_to_private_ip():
    transport = httpx.MockTransport(
        lambda req: httpx.Response(302, headers={"location": "http://127.0.0.1/admin"})
        if req.url.host == "public.example"
        else httpx.Response(200, text="secret")
    )
    with pytest.raises(UnsafeURLError):
        fetch_url("http://public.example/", resolver=PUBLIC, transport=transport)


def test_follows_relative_redirect():
    def handler(req):
        if req.url.path == "/a":
            return httpx.Response(302, headers={"location": "/b"})
        return httpx.Response(200, text="ok")

    body, final = fetch_url("http://public.example/a", resolver=PUBLIC, transport=httpx.MockTransport(handler))
    assert body == b"ok" and final == "http://public.example/b"


def test_too_many_redirects():
    transport = httpx.MockTransport(lambda req: httpx.Response(302, headers={"location": "/loop"}))
    with pytest.raises(UnsafeURLError, match="Too many redirects"):
        fetch_url("http://public.example/", resolver=PUBLIC, transport=transport)


def test_rejects_oversized_body():
    transport = httpx.MockTransport(lambda req: httpx.Response(200, content=b"x" * 6_000_000))
    with pytest.raises(ParseError, match="max 5 MB"):
        fetch_url("http://public.example/", resolver=PUBLIC, transport=transport)


def test_returns_body_and_final_url():
    transport = httpx.MockTransport(lambda req: httpx.Response(200, text="<p>hi</p>"))
    body, final = fetch_url("http://public.example/a", resolver=PUBLIC, transport=transport)
    assert body == b"<p>hi</p>" and final == "http://public.example/a"


def test_http_error_status_is_parse_error():
    transport = httpx.MockTransport(lambda req: httpx.Response(404))
    with pytest.raises(ParseError):
        fetch_url("http://public.example/", resolver=PUBLIC, transport=transport)
