"""
dns_live.py
-----------
Performs a REAL DNS resolution (Live Mode) for the Browsing activity,
using only Python's standard library -- no extra packages installed.

This is intentionally narrow, matching what Live Phase 1 is scoped to:
it resolves a domain name to an IPv4 address via
socket.gethostbyname(), which asks the operating system's configured
DNS resolver to do the lookup. It does NOT, and cannot:
    - know or report which DNS server actually answered
    - see the real transaction ID, TTL, or raw wire-format packet
    - let the caller choose a custom DNS server
    - make any HTTP/HTTPS request

Anything Python's standard resolver genuinely cannot observe is left
out of the event data entirely rather than invented -- the assignment
is explicit that Live Mode must not fabricate packet-level detail it
didn't actually capture.
"""

import socket
import time


class DNSLookupError(Exception):
    """Raised when a real DNS lookup fails for an otherwise well-formed domain."""


def resolve_domain(domain: str):
    """
    Perform a real DNS A-record lookup for `domain` using the system's
    configured resolver.

    Returns (ip_address, duration_ms) on success, where duration_ms is
    the ACTUAL measured wall-clock time the lookup took -- never a
    fabricated number.

    Raises DNSLookupError if the domain cannot be resolved (it doesn't
    exist, there's no DNS/network connectivity, etc.), with a message
    safe to show directly to the user.
    """
    start = time.perf_counter()
    try:
        ip_address = socket.gethostbyname(domain)
    except socket.gaierror as exc:
        raise DNSLookupError(
            f"Could not resolve '{domain}': {exc.strerror or 'name resolution failed'}."
        ) from exc
    except OSError as exc:
        # Covers other resolver-level failures (e.g. no network route)
        # without leaking a raw traceback back to the user.
        raise DNSLookupError(f"DNS lookup failed for '{domain}': {exc}") from exc

    duration_ms = (time.perf_counter() - start) * 1000
    return ip_address, duration_ms


def build_live_dns_events(domain: str):
    """
    Perform a real DNS lookup for `domain` and return the two protocol
    events (Query, Response) describing it, using the exact same event
    structure as the offline simulators (protocol, direction, summary,
    raw, fields, highlight, timing_ms) so the shared Visualizer Engine
    can render either one without changes.

    Raises DNSLookupError on failure -- the Flask route is responsible
    for turning that into an HTTP error response.
    """
    ip_address, duration_ms = resolve_domain(domain)

    query_event = {
        "protocol": "DNS",
        "direction": "client-to-server",
        "summary": "DNS Query (Live)",
        "raw": f"Query: {domain}  Type: A",
        "fields": {
            "Domain": domain,
            "Type": "A",
            # Honest about what we actually know: Python's resolver
            # doesn't expose which specific DNS server answered, so we
            # say "system default" rather than inventing a server IP.
            "Resolver": "System default (OS-configured)",
        },
        "highlight": ["Domain", "Type"],
        "timing_ms": 0,
    }

    response_event = {
        "protocol": "DNS",
        "direction": "server-to-client",
        "summary": "DNS Response (Live)",
        "raw": f"{domain} -> {ip_address}",
        "fields": {
            "Domain": domain,
            "IP Address": ip_address,
            "Lookup Time (ms)": f"{duration_ms:.1f}",
        },
        "highlight": ["IP Address"],
        # Real, measured timing -- unlike the simulator's fixed 0/40ms
        # offsets, this is how long the actual lookup took just now.
        "timing_ms": round(duration_ms),
    }

    return [query_event, response_event]
