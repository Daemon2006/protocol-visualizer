"""
streaming_sim.py
----------------
Builds a simulated DNS lookup + HTTP manifest/playlist + HTTP segment
sequence for the Streaming activity.

This does NOT connect to any real streaming service and does NOT
fetch or play real video. Everything -- the manifest body, the segment
paths, the response headers -- is generated from fixed templates using
real HLS (HTTP Live Streaming) playlist conventions, so the *shape* of
the exchange is accurate even though no real bytes are transferred.

Only two protocols ever appear here, matching how streaming actually
works at the application layer:
    DNS  -- resolves the streaming host, once
    HTTP -- everything else. The manifest AND every segment are just
            ordinary HTTP GET requests/responses -- they are NOT a
            separate "streaming protocol".
"""

import hashlib

STREAMING_HOST = "video.example.com"
SEGMENT_COUNT = 3
SEGMENT_DURATION_SECONDS = 6.0

# The three qualities the assignment asks for. Kept as a tuple (not a
# dict/table) since the only thing that actually changes per quality
# is the "/video/<quality>/..." path segment -- no extra per-quality
# data is needed, which keeps this simulator simple on purpose.
SUPPORTED_QUALITIES = ("360p", "720p", "1080p")


def _fake_ip_for_host(host: str) -> str:
    """
    Deterministic, made-up IPv4 address for the streaming host.

    Same technique used in dns_sim.py for Browsing (hash the hostname,
    use four hash bytes as IP octets) -- duplicated here in one small
    function rather than importing dns_sim, to keep each simulator
    module independent and easy to read on its own.
    """
    digest = hashlib.md5(host.encode("utf-8")).hexdigest()
    octets = [int(digest[i:i + 2], 16) for i in (0, 2, 4, 6)]
    octets = [max(1, min(o, 254)) for o in octets]
    return ".".join(str(o) for o in octets)


def simulate_streaming(quality: str):
    """
    Return the full ordered list of protocol events for starting a
    simulated video stream at the given quality ("360p"/"720p"/"1080p").

    Sequence:
        1) DNS query + response for the streaming host
        2) one HTTP manifest (playlist) request + response
        3) SEGMENT_COUNT pairs of HTTP segment request + response

    Every request path includes the quality (e.g. "/video/720p/..."),
    so calling this with a different quality visibly changes the
    requested resource paths -- that's the whole point of the quality
    selector.
    """
    ip_address = _fake_ip_for_host(STREAMING_HOST)
    events = []

    # ---------- 1-2: DNS ----------
    events.append({
        "protocol": "DNS",
        "direction": "client-to-server",
        "summary": "DNS Query",
        "raw": f"Query: {STREAMING_HOST}  Type: A",
        "fields": {"Domain": STREAMING_HOST, "Type": "A"},
        "highlight": ["Domain", "Type"],
        "timing_ms": 0,
    })
    events.append({
        "protocol": "DNS",
        "direction": "server-to-client",
        "summary": "DNS Response",
        "raw": f"{STREAMING_HOST} -> {ip_address}",
        "fields": {"Domain": STREAMING_HOST, "IP Address": ip_address},
        "highlight": ["IP Address"],
        "timing_ms": 40,
    })

    # ---------- 3-4: HTTP manifest / playlist ----------
    manifest_path = f"/video/{quality}/playlist.m3u8"

    manifest_lines = ["#EXTM3U", "#EXT-X-VERSION:3"]
    for i in range(1, SEGMENT_COUNT + 1):
        manifest_lines.append(f"#EXTINF:{SEGMENT_DURATION_SECONDS:.1f},")
        manifest_lines.append(f"segment{i:03d}.ts")
    manifest_body = "\n".join(manifest_lines)

    events.append({
        "protocol": "HTTP",
        "direction": "client-to-server",
        "summary": "HTTP Manifest Request",
        "raw": (
            f"GET {manifest_path} HTTP/1.1\n"
            f"Host: {STREAMING_HOST}\n"
            "Accept: application/vnd.apple.mpegurl"
        ),
        "fields": {"Method": "GET", "Path": manifest_path, "Host": STREAMING_HOST},
        "highlight": ["Path"],
        "timing_ms": 80,
    })
    events.append({
        "protocol": "HTTP",
        "direction": "server-to-client",
        "summary": "HTTP Manifest Response",
        "raw": (
            "HTTP/1.1 200 OK\n"
            "Content-Type: application/vnd.apple.mpegurl\n"
            "\n"
            f"{manifest_body}"
        ),
        "fields": {
            "Status": "200 OK",
            "Content-Type": "application/vnd.apple.mpegurl",
            "Segments Listed": str(SEGMENT_COUNT),
        },
        "highlight": ["Status"],
        "timing_ms": 120,
    })

    # ---------- 5+: HTTP segments (each is its own ordinary GET) ----------
    timing = 160
    for i in range(1, SEGMENT_COUNT + 1):
        segment_name = f"segment{i:03d}.ts"
        segment_path = f"/video/{quality}/{segment_name}"

        events.append({
            "protocol": "HTTP",
            "direction": "client-to-server",
            "summary": f"HTTP Segment {i} Request",
            "raw": (
                f"GET {segment_path} HTTP/1.1\n"
                f"Host: {STREAMING_HOST}"
            ),
            "fields": {"Method": "GET", "Path": segment_path, "Segment": segment_name},
            "highlight": ["Path"],
            "timing_ms": timing,
        })
        timing += 40

        events.append({
            "protocol": "HTTP",
            "direction": "server-to-client",
            "summary": f"HTTP Segment {i} Response",
            "raw": (
                "HTTP/1.1 200 OK\n"
                "Content-Type: video/mp2t"
            ),
            "fields": {"Status": "200 OK", "Content-Type": "video/mp2t", "Segment": segment_name},
            "highlight": ["Status"],
            "timing_ms": timing,
        })
        timing += 40

    return events
