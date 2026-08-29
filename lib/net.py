"""
Outbound HTTP for URLs a person typed in.

`urllib.request.urlopen` will happily fetch `file:///etc/passwd`,
`http://169.254.169.254/` or a router's admin page — the server reaches places
the browser that asked never could. Every fetch of a user-supplied URL goes
through `safe_get`, which insists on http(s), on a host the caller expects, on an
address outside this network, and on redirects that stay within the same rules.
"""
import ipaddress
import socket
import urllib.request
from urllib.parse import urlparse


class UnsafeURL(Exception):
    """The URL was rejected before any request went out."""


def _assert_public(host: str) -> None:
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        raise UnsafeURL("that address could not be resolved")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        # is_global excludes loopback, link-local, private ranges and 0.0.0.0/8.
        if not ip.is_global or ip.is_multicast:
            raise UnsafeURL("that address points inside this network")


def check_url(url: str, host_ok) -> str:
    p = urlparse(url or "")
    if p.scheme not in ("http", "https"):
        raise UnsafeURL("only http and https addresses are supported")
    host = (p.hostname or "").lower()
    if not host or not host_ok(host):
        raise UnsafeURL("that address is not on an allowed site")
    _assert_public(host)
    return host


class _GuardedRedirects(urllib.request.HTTPRedirectHandler):
    """Re-run the same checks on every hop, so a redirect cannot escape them."""

    def __init__(self, host_ok):
        self.host_ok = host_ok

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        check_url(newurl, self.host_ok)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def safe_get(url: str, *, host_ok, timeout: int = 15, max_bytes: int = 2_000_000) -> bytes:
    """
    Fetch `url` if it passes `check_url`, capped at `max_bytes`.

    `host_ok(hostname) -> bool` decides which sites are in scope. Note the small
    window between the DNS check and the connection: the host allowlist is what
    closes it, since rebinding would require control of that site's DNS.
    """
    check_url(url, host_ok)
    opener = urllib.request.build_opener(_GuardedRedirects(host_ok))
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with opener.open(req, timeout=timeout) as resp:
        body = resp.read(max_bytes + 1)
    if len(body) > max_bytes:
        raise UnsafeURL("that page is too large to import")
    return body
