"""
app.py
------
This is the Flask application entry point.

It has two jobs:
    1. serve the single HTML page (templates/index.html)
    2. expose small JSON API routes that generate protocol event
       sequences for each activity:

       Simulation Mode (fully offline, deterministic):
         - POST /api/simulate/browsing  (Phase 1: DNS + HTTP)
         - POST /api/simulate/mail      (Phase 2: DNS/MX + SMTP)
         - POST /api/simulate/streaming (Phase 3: DNS + HTTP manifest/segments)

       Live Mode (real network activity):
         - POST /api/live/dns           (real DNS only, used for stream host resolution & compatibility)
         - POST /api/live/browsing      (real DNS + real HTTP/HTTPS)
         - POST /api/live/mail          (real authenticated SMTP submission)

No Simulation route makes a real network connection -- every one of
those events comes from a "simulator" module under simulators/. The
Live routes perform actual DNS resolution, real HTTP/HTTPS requests,
or real SMTP submission via Python's standard library through the live/ module.
"""

import re
from urllib.parse import urlparse

from flask import Flask, render_template, request, jsonify

from simulators.dns_sim import simulate_dns
from simulators.http_sim import simulate_http
from simulators.smtp_sim import simulate_mail
from simulators.streaming_sim import simulate_streaming, SUPPORTED_QUALITIES
from simulators.flow_control_sim import (
    simulate_stop_and_wait,
    simulate_stop_and_wait_arq,
)
from live.dns_live import build_live_dns_events, DNSLookupError
from live.http_live import build_live_http_events, HTTPRequestError
from live.smtp_live import send_live_mail, is_smtp_configured, SMTPLiveError
from live.flow_control_live import (
    live_stop_and_wait,
    live_stop_and_wait_arq,
    LiveFlowControlError,
)

# Create the Flask application object.
# __name__ tells Flask where to look for templates/ and static/ folders.
app = Flask(__name__)

# A deliberately simple email-shape check: something@something.something
# This is NOT a full RFC 5322 validator -- just enough to catch obviously
# empty/malformed addresses without over-engineering Phase 2.
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@app.route("/")
def index():
    """
    This function runs whenever a browser requests the home page ("/").

    render_template() looks inside the templates/ folder for a file
    called index.html, fills in any placeholders, and sends the
    resulting HTML back to the browser.
    """
    return render_template("index.html")


def _parse_url(raw_url: str):
    """
    Turn whatever the user typed into (domain, path).

    This is intentionally simple -- just enough to demonstrate DNS/HTTP
    behavior, not a full URL-validation library. If the user forgot the
    "http://" part (e.g. typed "example.com"), we add it ourselves so
    urlparse() can still split out the domain correctly.
    """
    raw_url = raw_url.strip()
    if not raw_url:
        return None, None

    if "://" not in raw_url:
        raw_url = "http://" + raw_url

    parsed = urlparse(raw_url)
    domain = parsed.netloc
    path = parsed.path if parsed.path else "/"

    if not domain:
        return None, None

    return domain, path


@app.route("/api/simulate/browsing", methods=["POST"])
def simulate_browsing():
    """
    API endpoint for the Browsing activity.

    Expects a JSON body like: { "url": "example.com" }

    Builds a DNS event pair followed by an HTTP event pair (no real
    network requests are made -- everything comes from the simulator
    modules), numbers them in order, and returns them as JSON for the
    frontend's Visualizer Engine to play back.
    """
    data = request.get_json(silent=True) or {}
    raw_url = data.get("url", "")

    domain, path = _parse_url(raw_url)
    if not domain:
        # Simple, useful validation: just make sure we got a usable domain.
        return jsonify({"error": "Please enter a valid URL before clicking Visit."}), 400

    # Build the full sequence: DNS first (we need an IP before we can
    # "reach" the web server), then HTTP.
    events = simulate_dns(domain) + simulate_http(domain, path)

    # Assign the final step numbers now that we know the combined order.
    for index, event in enumerate(events, start=1):
        event["step"] = index

    return jsonify({
        "activity": "browsing",
        "url": raw_url,
        "domain": domain,
        "events": events,
    })


@app.route("/api/live/dns", methods=["POST"])
def live_dns_route():
    """
    LIVE MODE endpoint (Live Phase 1) for the Browsing activity.

    Expects a JSON body like: { "url": "example.com" }

    Unlike /api/simulate/browsing, this performs a REAL DNS lookup via
    Python's standard library (see live/dns_live.py) -- no HTTP request
    is made, and the user cannot specify a custom DNS server or any
    other network operation; this endpoint does exactly one thing.

    Reuses the same _parse_url() helper as Simulation Mode so both
    modes accept and validate the URL identically, and returns events
    in the exact same shape the shared Visualizer Engine already knows
    how to render.
    """
    data = request.get_json(silent=True) or {}
    raw_url = data.get("url", "")

    domain, _path = _parse_url(raw_url)
    if not domain:
        return jsonify({"error": "Please enter a valid URL before clicking Visit."}), 400

    try:
        events = build_live_dns_events(domain)
    except DNSLookupError as exc:
        # A well-formed domain that the resolver couldn't actually look
        # up (doesn't exist, no connectivity, etc.) -- 502 signals "the
        # upstream DNS lookup failed", distinct from a 400 (bad input).
        return jsonify({"error": str(exc)}), 502

    for index, event in enumerate(events, start=1):
        event["step"] = index

    return jsonify({
        "activity": "browsing",
        "mode": "live",
        "url": raw_url,
        "domain": domain,
        "events": events,
    })


def _live_scheme_or_error(raw_url: str):
    """
    Determine which scheme to use for the real HTTP(S) request, and
    reject anything Live Mode doesn't support.

    Only http:// and https:// are ever accepted. If the person typed
    an explicit scheme other than those (e.g. "ftp://", "file://"),
    that's rejected with a clear error rather than silently treated as
    http/https. If no scheme was given at all, default to https --
    real-world sites overwhelmingly require it today, so this gives
    Live mode the best chance of reaching a genuine response.

    Returns (scheme, error_message) -- error_message is None on success.
    """
    stripped = raw_url.strip()
    if ":" in stripped:
        potential = stripped.split(":", 1)[0].lower()
        if re.match(r"^[a-z][a-z0-9+.-]*$", potential):
            if potential not in ("http", "https"):
                return None, f"Live mode only supports http:// and https:// URLs (got '{potential}:')."
            return potential, None
    return "https", None


@app.route("/api/live/browsing", methods=["POST"])
def live_browsing_route():
    """
    LIVE MODE endpoint for the Browsing activity.

    Expects a JSON body like: { "url": "example.com" }

    Performs the full real sequence: a real DNS lookup, THEN (only if
    that succeeds) a real HTTP/HTTPS GET request. Validates scheme,
    resolves DNS, enforces SSRF safeguards, and returns all 4 protocol
    events to the Visualizer.
    """
    data = request.get_json(silent=True) or {}
    raw_url = data.get("url", "")

    scheme, scheme_error = _live_scheme_or_error(raw_url)
    if scheme_error:
        return jsonify({"error": scheme_error}), 400

    domain, path = _parse_url(raw_url)
    if not domain:
        return jsonify({"error": "Please enter a valid URL before clicking Visit."}), 400

    # Step 1: real DNS. If this fails, there's no point attempting the
    # HTTP request at all -- surface the DNS failure directly.
    try:
        dns_events = build_live_dns_events(domain)
    except DNSLookupError as exc:
        return jsonify({"error": str(exc)}), 502

    # The DNS step's own resolved IP, reused (not re-resolved) for the
    # HTTP step's SSRF check -- see the docstring above.
    resolved_ip = dns_events[1]["fields"]["IP Address"]

    # Step 2: real HTTP(S), only after DNS succeeded. Uses `domain`
    # (the original hostname), never `resolved_ip`, to build the URL.
    try:
        http_events = build_live_http_events(domain, path, resolved_ip, scheme=scheme)
    except HTTPRequestError as exc:
        return jsonify({"error": str(exc)}), 502

    events = dns_events + http_events
    for index, event in enumerate(events, start=1):
        event["step"] = index

    return jsonify({
        "activity": "browsing",
        "mode": "live",
        "url": raw_url,
        "domain": domain,
        "events": events,
    })


@app.route("/api/simulate/mail", methods=["POST"])
def simulate_mail_route():
    """
    API endpoint for the Mail activity.

    Expects a JSON body like:
        { "to": "alice@example.com", "subject": "Hi", "body": "Hello!" }

    Validates the three fields, then builds a DNS/MX lookup followed by
    a full SMTP conversation (no real email is ever sent -- everything
    comes from simulators/smtp_sim.py), numbers the events in order,
    and returns them as JSON for the same Visualizer Engine already
    used by Browsing.
    """
    data = request.get_json(silent=True) or {}
    to = (data.get("to") or "").strip()
    subject = (data.get("subject") or "").strip()
    body = (data.get("body") or "").strip()

    # Validate one field at a time so the error message tells the user
    # exactly what's missing, rather than a generic "invalid input".
    if not to:
        return jsonify({"error": "Please enter a recipient address (To)."}), 400
    if not EMAIL_PATTERN.match(to):
        return jsonify({"error": "That doesn't look like a valid email address, e.g. name@example.com."}), 400
    if not subject:
        return jsonify({"error": "Please enter a subject."}), 400
    if not body:
        return jsonify({"error": "Please enter a message body."}), 400

    events = simulate_mail(to, subject, body)

    # Assign the final step numbers now that we know the combined order
    # (DNS/MX lookup first, then the full SMTP conversation).
    for index, event in enumerate(events, start=1):
        event["step"] = index

    return jsonify({
        "activity": "mail",
        "to": to,
        "subject": subject,
        "events": events,
    })


@app.route("/api/live/mail", methods=["POST"])
def live_mail_route():
    """
    LIVE MODE endpoint for the Mail activity.

    Expects a JSON body like:
        { "to": "alice@example.com", "subject": "Hi", "body": "Hello!" }

    Validates inputs, verifies SMTP environment configuration is present,
    and performs a real authenticated SMTP submission via Python's standard
    smtplib. No secrets are stored in code or exposed in logs.
    """
    data = request.get_json(silent=True) or {}
    to = (data.get("to") or "").strip()
    subject = (data.get("subject") or "").strip()
    body = (data.get("body") or "").strip()

    if not to:
        return jsonify({"error": "Please enter a recipient address (To)."}), 400
    if not EMAIL_PATTERN.match(to):
        return jsonify({"error": "That doesn't look like a valid email address, e.g. name@example.com."}), 400
    if not subject:
        return jsonify({"error": "Please enter a subject."}), 400
    if not body:
        return jsonify({"error": "Please enter a message body."}), 400

    if not is_smtp_configured():
        return jsonify({
            "error": "Live SMTP is not configured. Please set SMTP_HOST in environment variables or .env file."
        }), 400

    try:
        events = send_live_mail(to, subject, body)
    except SMTPLiveError as exc:
        return jsonify({"error": str(exc)}), 502

    for index, event in enumerate(events, start=1):
        event["step"] = index

    return jsonify({
        "activity": "mail",
        "mode": "live",
        "to": to,
        "subject": subject,
        "events": events,
    })


@app.route("/api/simulate/streaming", methods=["POST"])
def simulate_streaming_route():
    """
    API endpoint for the Streaming activity.

    Expects a JSON body like: { "quality": "720p" }

    Validates that the quality is one of the supported options, then
    builds a DNS lookup followed by an HTTP manifest request/response
    and several HTTP segment request/response pairs (no real streaming
    service is ever contacted -- everything comes from
    simulators/streaming_sim.py), numbers the events in order, and
    returns them as JSON for the same Visualizer Engine already used
    by Browsing and Mail.
    """
    data = request.get_json(silent=True) or {}
    quality = (data.get("quality") or "").strip()

    if quality not in SUPPORTED_QUALITIES:
        return jsonify({
            "error": f"Please choose a supported quality: {', '.join(SUPPORTED_QUALITIES)}."
        }), 400

    events = simulate_streaming(quality)

    # Assign the final step numbers now that we know the combined order
    # (DNS first, then the manifest, then each segment in sequence).
    for index, event in enumerate(events, start=1):
        event["step"] = index

    return jsonify({
        "activity": "streaming",
        "quality": quality,
        "events": events,
    })


SUPPORTED_FLOW_VARIANTS = ("stop-and-wait", "stop-and-wait-arq")


@app.route("/api/simulate/flow-control", methods=["POST"])
def simulate_flow_control_route():
    """
    API endpoint for Flow Control simulation (Stop-and-Wait & Stop-and-Wait ARQ).

    Expects a JSON body like:
        {
            "variant": "stop-and-wait",       # or "stop-and-wait-arq"
            "frame_count": 4,                 # integer 2-6 (optional, default 4)
            "scenario": "normal"              # "normal", "frame_loss", "ack_loss", "delayed_ack"
        }

    Validates inputs and calls the appropriate simulator module, returning
    the ordered protocol event sequence for the visualizer.
    """
    data = request.get_json(silent=True) or {}

    variant = (data.get("variant") or "").strip().lower()
    if variant not in SUPPORTED_FLOW_VARIANTS:
        return jsonify({
            "error": f"Please choose a supported flow control variant: {', '.join(SUPPORTED_FLOW_VARIANTS)}."
        }), 400

    frame_count = data.get("frame_count", 4)
    scenario = data.get("scenario")
    if variant == "stop-and-wait":
        scenario = scenario or "normal"
    elif scenario is None:
        scenario = "normal"

    try:
        if variant == "stop-and-wait":
            events = simulate_stop_and_wait(frame_count)
        else:
            events = simulate_stop_and_wait_arq(frame_count, scenario)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    return jsonify({
        "activity": "flow-control",
        "variant": variant,
        "frame_count": frame_count,
        "scenario": scenario,
        "events": events,
    })


@app.route("/api/live/flow-control", methods=["POST"])
def live_flow_control_route():
    """
    LIVE MODE API endpoint for Flow Control (Stop-and-Wait & Stop-and-Wait ARQ).

    Transmits data frames and acknowledgments over real OS UDP sockets on loopback.

    Expects a JSON body like:
        {
            "variant": "stop-and-wait",       # or "stop-and-wait-arq"
            "frame_count": 4,                 # integer 2-6 (optional, default 4)
            "scenario": "normal"              # "normal", "frame_loss", "ack_loss", "delayed_ack"
        }

    Validates inputs and calls the live socket module, returning
    the ordered protocol event sequence for the visualizer.
    """
    data = request.get_json(silent=True) or {}

    variant = (data.get("variant") or "").strip().lower()
    if variant not in SUPPORTED_FLOW_VARIANTS:
        return jsonify({
            "error": f"Please choose a supported flow control variant: {', '.join(SUPPORTED_FLOW_VARIANTS)}."
        }), 400

    frame_count = data.get("frame_count", 4)
    scenario = data.get("scenario")
    if variant == "stop-and-wait":
        scenario = scenario or "normal"
    elif scenario is None:
        scenario = "normal"

    try:
        if variant == "stop-and-wait":
            events = live_stop_and_wait(frame_count)
        else:
            events = live_stop_and_wait_arq(frame_count, scenario)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except LiveFlowControlError as exc:
        return jsonify({"error": str(exc)}), 502

    return jsonify({
        "activity": "flow-control",
        "mode": "live",
        "variant": variant,
        "frame_count": frame_count,
        "scenario": scenario,
        "events": events,
    })


# This block only runs if you execute "python app.py" directly
# (it does NOT run if this file is imported by something else).
if __name__ == "__main__":
    # debug=True gives helpful error pages and auto-reloads the server
    # whenever you save a change to this file -- very useful while learning.
    app.run(debug=True)
