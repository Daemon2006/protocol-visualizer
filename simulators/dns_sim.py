"""
dns_sim.py
----------
Builds a simulated DNS query/response pair for a given domain name.

This does NOT perform a real DNS lookup. It fabricates a realistic,
deterministic response so the same domain always resolves to the same
fake IP address every time you run the simulation (useful for demos
and grading -- the output is repeatable, not random).
"""

import hashlib


def _fake_ip_for_domain(domain: str) -> str:
    """
    Turn a domain name into a deterministic, made-up IPv4 address.

    We hash the domain name and use four bytes of the hash as the four
    octets of an IP address. This is NOT a real lookup -- it just
    guarantees "example.com" always maps to the same fake IP every
    time, without needing a hardcoded table for every possible domain.
    """
    digest = hashlib.md5(domain.encode("utf-8")).hexdigest()
    octets = [int(digest[i:i + 2], 16) for i in (0, 2, 4, 6)]
    # Keep octets in a "normal looking" range (avoid 0 and 255).
    octets = [max(1, min(o, 254)) for o in octets]
    return ".".join(str(o) for o in octets)


def simulate_dns(domain: str):
    """
    Return a list of two protocol events representing a DNS lookup:
        1) the client's DNS query
        2) the DNS server's response

    Each event follows the shared event structure used across the whole
    project (protocol, direction, summary, raw, fields, highlight,
    timing_ms). The caller (app.py) is responsible for assigning the
    final "step" numbers once it knows the full combined sequence.
    """
    ip_address = _fake_ip_for_domain(domain)
    transaction_id = "0x" + hashlib.md5(domain.encode("utf-8")).hexdigest()[:4]

    query_event = {
        "protocol": "DNS",
        "direction": "client-to-server",
        "summary": "DNS Query",
        "raw": f"Query: {domain}  Type: A  ID: {transaction_id}",
        "fields": {
            "Domain": domain,
            "Type": "A",
            "Transaction ID": transaction_id,
        },
        "highlight": ["Domain", "Type"],
        "timing_ms": 0,
    }

    response_event = {
        "protocol": "DNS",
        "direction": "server-to-client",
        "summary": "DNS Response",
        "raw": f"{domain} -> {ip_address}  TTL: 300  ID: {transaction_id}",
        "fields": {
            "Domain": domain,
            "IP Address": ip_address,
            "TTL": "300",
        },
        "highlight": ["IP Address"],
        "timing_ms": 40,
    }

    return [query_event, response_event]
