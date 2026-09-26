"""
http_live.py
------------
Performs a REAL HTTP/HTTPS GET request (Live Mode) for the Browsing
activity, using only Python's standard library (urllib.request) --
no extra packages.

Deliberately bounded, matching the scope of this Live phase:
    - GET requests only -- no other HTTP method is ever used
    - no custom headers/body/options come from the user -- only the
      URL they typed controls anything
    - a fixed timeout, so a slow/unresponsive real server can't hang
      the Flask app
    - redirects are NOT followed. A 3xx response is shown as-is (with
      its Location header, if present) as the real Event 4, rather
      than silently chasing it -- this keeps the visible event
      sequence honest about what actually happened on this one request
    - the SSRF safety check is done against the IP already obtained by
      the DNS step (passed in as `resolved_ip`), never by re-resolving
      the domain here. Re-resolving separately would open a TOCTOU gap
      (the domain could resolve to a different address between the
      "check" and the "use", e.g. via DNS rebinding) -- reusing the
      one already-obtained IP closes that gap
    - the ORIGINAL HOSTNAME -- never the resolved IP -- is used to
      build the actual request URL. This matters for two real
      protocol reasons: HTTP virtual hosting depends on the Host
      header matching the hostname, and HTTPS depends on hostname-
      based SNI and certificate validation -- connecting to the bare
      IP would break both

Only what the real response genuinely contains is reported. No header
or status is invented, and the response body's actual content is never
displayed (only its metadata -- status, a few headers, timing) to keep
the panel simple and avoid dumping arbitrary fetched content into the UI.
"""

import ipaddress
import time
import urllib.error
import urllib.request

REQUEST_TIMEOUT_SECONDS = 6
USER_AGENT = "ProtocolVisualizer-LiveMode/1.0 (educational demo)"
# Which response headers are worth showing -- enough to be useful,
# small enough to stay readable in the panel. "Location" matters here
# specifically because we no longer follow redirects, so it's the only
# way to see where a 3xx response would have sent a real browser.
HEADERS_TO_SHOW = ("Content-Type", "Content-Length", "Server", "Date", "Location", "X-Frame-Options")


class HTTPRequestError(Exception):
    """Raised when the real HTTP(S) request cannot be made at all."""


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """
    Overrides urllib's default "silently follow 301/302/303/307/308"
    behavior. Returning None from redirect_request() tells urllib NOT
    to follow the redirect -- the original 3xx response is returned to
    the caller as-is (status, headers, everything) instead of being
    swallowed and replaced with whatever the redirect target sends
    back. This is what lets Event 4 honestly show a real 301 response
    instead of secretly performing a second, invisible HTTP request.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_opener = urllib.request.build_opener(_NoRedirectHandler)


def _ip_is_blocked(resolved_ip: str) -> bool:
    """
    True if `resolved_ip` (a string IPv4/IPv6 address ALREADY obtained
    by the DNS step -- never re-resolved here) is private, loopback,
    link-local, reserved, or multicast. Live Mode refuses to fetch
    these, so the app can't be used to probe the machine's own
    internal network (a basic SSRF safeguard, not a full security
    review).
    """
    try:
        ip = ipaddress.ip_address(resolved_ip)
    except ValueError:
        # Not a parseable IP at all -- treat as not-blocked and let the
        # real request attempt (and fail normally) rather than guessing.
        return False
    return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast


def fetch_live(url: str, resolved_ip: str):
    """
    Perform a real HTTP(S) GET request to `url` (built from the
    ORIGINAL HOSTNAME, not an IP) and return
    (status_code, reason, headers_dict, duration_ms).

    `resolved_ip` is used ONLY for the SSRF safety check -- it is the
    IP the DNS step already obtained, reused here rather than
    re-resolved, and it never replaces the hostname in the request
    itself.

    Raises HTTPRequestError if the request cannot be completed at all
    (refused for safety, or a DNS/connection/TLS/timeout failure at
    the transport level). A valid-but-unsuccessful HTTP status like
    404 or 500 is NOT an error here -- that IS a real response and is
    returned normally, exactly like a 200 would be.
    """
    if _ip_is_blocked(resolved_ip):
        raise HTTPRequestError(
            f"The resolved address {resolved_ip} is a private/internal address -- "
            "Live Mode only fetches public internet addresses."
        )

    request = urllib.request.Request(url, method="GET", headers={"User-Agent": USER_AGENT})
    start = time.perf_counter()
    try:
        with _opener.open(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            status_code = response.status
            reason = response.reason
            headers = dict(response.getheaders())
    except urllib.error.HTTPError as exc:
        # HTTPError is urllib's way of surfacing a 4xx/5xx -- that is
        # still a REAL, valid response, not a failed connection, so we
        # treat it as success with an unsuccessful status code.
        status_code = exc.code
        reason = exc.reason
        headers = dict(exc.headers.items()) if exc.headers else {}
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        # Covers connection failures, timeouts, and TLS/certificate
        # errors (ssl.SSLError is a subclass of OSError) -- none of
        # these produced any real response, so they're a genuine error.
        reason_detail = getattr(exc, "reason", exc)
        raise HTTPRequestError(f"Could not reach '{url}': {reason_detail}") from exc

    duration_ms = (time.perf_counter() - start) * 1000
    return status_code, reason, headers, duration_ms


def build_live_http_events(domain: str, path: str, resolved_ip: str, scheme: str = "https"):
    """
    Perform a real HTTP(S) GET for scheme://domain/path (hostname-based,
    never IP-based) and return the two protocol events (Request,
    Response) describing it, using the exact same event structure as
    the rest of the project. `protocol` stays "HTTP" for both http and
    https requests (HTTPS is HTTP-over-TLS at the application layer,
    matching the project's established protocol categories) -- the
    scheme is instead surfaced in the summary text and a "Scheme" field
    so HTTPS/TLS is still clearly indicated without inventing a new
    protocol category.
    """
    url = f"{scheme}://{domain}{path}"
    label = scheme.upper()  # "HTTP" or "HTTPS", for display only
    status_code, reason, headers, duration_ms = fetch_live(url, resolved_ip)

    request_event = {
        "protocol": "HTTP",
        "transport": "TCP",
        "direction": "client-to-server",
        "summary": f"{label} Request (Live)",
        "raw": (
            f"GET {path} HTTP/1.1\n"
            f"Host: {domain}\n"
            f"User-Agent: {USER_AGENT}"
        ),
        "fields": {"Method": "GET", "Scheme": label, "URL": url},
        "highlight": ["Method", "URL"],
        "timing_ms": 0,
    }

    shown_headers = {k: v for k, v in headers.items() if k in HEADERS_TO_SHOW}
    raw_lines = [f"HTTP {status_code} {reason}"]
    raw_lines.extend(f"{k}: {v}" for k, v in shown_headers.items())

    response_fields = {"Status": f"{status_code} {reason}", "Scheme": label, **shown_headers}
    response_fields["Fetch Time (ms)"] = f"{duration_ms:.1f}"

    response_event = {
        "protocol": "HTTP",
        "transport": "TCP",
        "direction": "server-to-client",
        "summary": f"{label} Response (Live)",
        "raw": "\n".join(raw_lines),
        "fields": response_fields,
        "highlight": ["Status"],
        # Real, measured timing for this specific request -- kept
        # separate from the DNS step's own timing (see dns_live.py).
        "timing_ms": round(duration_ms),
    }

    return [request_event, response_event]
