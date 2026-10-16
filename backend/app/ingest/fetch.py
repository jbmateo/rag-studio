"""SSRF-safe URL fetch: manual redirects, scheme + resolved-IP validation on every hop."""
import ipaddress
import socket
from urllib.parse import urljoin, urlsplit

import httpx

from app.ingest.parsers import ParseError

MAX_REDIRECTS = 5
TOO_LARGE = "Page too large (max 5 MB)"


class UnsafeURLError(Exception):
    """Message is user-facing."""


def _validate(url: str, resolver) -> None:
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        raise UnsafeURLError("Only http and https URLs are allowed")
    host = parts.hostname
    if not host:
        raise UnsafeURLError("Invalid URL")
    try:
        addrs = [str(ipaddress.ip_address(host))]
    except ValueError:
        try:
            infos = resolver(host, parts.port or (443 if parts.scheme == "https" else 80), type=socket.SOCK_STREAM)
        except OSError as exc:
            raise UnsafeURLError("Could not resolve host") from exc
        addrs = [info[4][0] for info in infos]
    if not addrs:
        raise UnsafeURLError("Could not resolve host")
    for addr in addrs:
        try:
            ip = ipaddress.ip_address(addr.split("%")[0])
        except ValueError:
            raise UnsafeURLError("Could not resolve host")
        if not ip.is_global:
            raise UnsafeURLError("URL points to a non-public address")


def fetch_url(
    url: str,
    *,
    max_bytes: int = 5_000_000,
    timeout: float = 10.0,
    resolver=socket.getaddrinfo,
    transport: httpx.BaseTransport | None = None,
) -> tuple[bytes, str]:
    # Residual risk: each hop is validated, but httpx re-resolves the host when
    # connecting, so a DNS-rebinding attacker could swap the answer in between.
    with httpx.Client(transport=transport, timeout=timeout, follow_redirects=False, trust_env=False) as client:
        for _ in range(MAX_REDIRECTS + 1):
            _validate(url, resolver)
            try:
                with client.stream("GET", url) as response:
                    if response.is_redirect:
                        location = response.headers.get("location")
                        if not location:
                            raise ParseError("Could not fetch URL")
                        url = urljoin(url, location)
                        continue
                    if response.status_code >= 400:
                        raise ParseError(f"Could not fetch URL (HTTP {response.status_code})")
                    declared = response.headers.get("content-length")
                    if declared and declared.isdigit() and int(declared) > max_bytes:
                        raise ParseError(TOO_LARGE)
                    body = bytearray()
                    for chunk in response.iter_bytes():
                        body.extend(chunk)
                        if len(body) > max_bytes:
                            raise ParseError(TOO_LARGE)
                    return bytes(body), url
            except httpx.HTTPError as exc:
                raise ParseError("Could not fetch URL") from exc
        raise UnsafeURLError("Too many redirects")
