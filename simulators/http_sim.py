"""
http_sim.py
-----------
Builds a simulated HTTP request/response pair for a given domain + path.

This does NOT make a real HTTP request. It builds HTTP/1.1 message text
using fixed templates, so the message format is always protocol-correct
(status line, headers, blank-line-separated sections) even though the
content itself is fabricated.
"""

import hashlib


def _fake_content_length(domain: str, path: str) -> int:
    """Deterministic, made-up response size (in bytes) for this domain+path."""
    digest = hashlib.md5(f"{domain}{path}".encode("utf-8")).hexdigest()
    return 800 + (int(digest[:4], 16) % 4000)


def simulate_http(domain: str, path: str = "/"):
    """
    Return a list of two protocol events representing one HTTP exchange:
        1) the client's HTTP GET request
        2) the server's HTTP response

    A domain containing the word "notfound" simulates a 404 response
    instead of 200, so the visualization can demonstrate that the
    status code is generated logic, not a hardcoded "always succeeds".
    """
    request_event = {
        "protocol": "HTTP",
        "direction": "client-to-server",
        "summary": "HTTP GET Request",
        "raw": (
            f"GET {path} HTTP/1.1\n"
            f"Host: {domain}\n"
            f"User-Agent: SimBrowser/1.0\n"
            f"Accept: text/html"
        ),
        "fields": {
            "Method": "GET",
            "Path": path,
            "Host": domain,
        },
        "highlight": ["Method", "Path"],
        "timing_ms": 60,
    }

    if "notfound" in domain.lower():
        status_line = "HTTP/1.1 404 Not Found"
        status_field = "404 Not Found"
    else:
        status_line = "HTTP/1.1 200 OK"
        status_field = "200 OK"

    content_type = "text/html"
    content_length = _fake_content_length(domain, path)

    response_event = {
        "protocol": "HTTP",
        "direction": "server-to-client",
        "summary": "HTTP Response",
        "raw": (
            f"{status_line}\n"
            f"Content-Type: {content_type}\n"
            f"Content-Length: {content_length}"
        ),
        "fields": {
            "Status": status_field,
            "Content-Type": content_type,
            "Content-Length": str(content_length),
        },
        "highlight": ["Status"],
        "timing_ms": 120,
    }

    return [request_event, response_event]
