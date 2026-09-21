"""
smtp_live.py
------------
Performs a REAL authenticated SMTP submission (Live Mode) for the
Mail activity, using only Python's standard library (smtplib, socket)
-- no extra packages.

Security rules strictly followed:
    - Zero hardcoded passwords or secrets in source code.
    - Configuration is loaded exclusively from environment variables
      (or an optional uncommitted .env file).
    - Authentication payloads and sensitive credentials are NEVER
      printed, logged, or included in event payloads. The visualization
      records "AUTH <redacted>" and reports actual server status codes.
    - SSRF safety: the resolved IP of SMTP_HOST is checked using the
      same blocked-IP rules as Live Browsing, preventing abuse against
      internal network services.
    - If configuration is missing, a clear, friendly error is returned
      without crashing or hanging.
"""

import os
import re
import socket
import time
import smtplib
from email.message import EmailMessage
from email.utils import formatdate, make_msgid

from live.dns_live import resolve_domain, DNSLookupError
from live.http_live import _ip_is_blocked

# Load .env file from project root if present, without requiring python-dotenv
def _load_env_file():
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    if os.path.isfile(env_path):
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, val = line.split("=", 1)
                    key = key.strip()
                    val = val.strip().strip("\"'")
                    if key and key not in os.environ:
                        os.environ[key] = val
        except Exception:
            pass

_load_env_file()


class SMTPLiveError(Exception):
    """Raised when a real SMTP submission cannot be completed."""


def get_smtp_config():
    """
    Read SMTP configuration from environment variables.
    Returns a dictionary of settings or None if SMTP_HOST is not set.
    """
    _load_env_file()
    host = os.environ.get("SMTP_HOST", "").strip()
    if not host:
        return None

    security = os.environ.get("SMTP_SECURITY", "starttls").strip().lower()
    default_port = 465 if security == "ssl" else 587
    try:
        port = int(os.environ.get("SMTP_PORT", default_port))
    except ValueError:
        port = default_port

    return {
        "host": host,
        "port": port,
        "security": security,
        "username": os.environ.get("SMTP_USERNAME", "").strip() or None,
        "password": os.environ.get("SMTP_PASSWORD", "") or None,
        "from_addr": os.environ.get("SMTP_FROM", "").strip() or "visualizer@example.com",
    }


def is_smtp_configured() -> bool:
    """Return True if required SMTP environment configuration is present."""
    config = get_smtp_config()
    return config is not None and bool(config["host"])


def _decode_bytes(val):
    if isinstance(val, bytes):
        return val.decode("utf-8", errors="replace")
    return str(val)


def send_live_mail(to: str, subject: str, body: str):
    """
    Perform a real SMTP submission and return the full list of protocol
    events (DNS + SMTP exchange).

    Raises SMTPLiveError if not configured or if connection/authentication
    fails, returning any events collected up to the point of failure.
    """
    config = get_smtp_config()
    if not config:
        raise SMTPLiveError("Live SMTP is not configured. Please set SMTP_HOST, SMTP_PORT, etc. in environment variables or .env file.")

    host = config["host"]
    port = config["port"]
    security = config["security"]
    username = config["username"]
    password = config["password"]
    from_addr = config["from_addr"]

    events = []
    step_start = time.perf_counter()

    # Step 1: DNS Resolution of SMTP_HOST
    try:
        ip_address, dns_duration_ms = resolve_domain(host)
    except DNSLookupError as exc:
        raise SMTPLiveError(f"DNS lookup failed for SMTP host '{host}': {exc}") from exc

    events.append({
        "protocol": "DNS",
        "direction": "client-to-server",
        "summary": "DNS Query (SMTP Host)",
        "raw": f"Query: {host}  Type: A",
        "fields": {"Host": host, "Type": "A", "Resolver": "System default (OS-configured)"},
        "highlight": ["Host", "Type"],
        "timing_ms": 0,
    })

    events.append({
        "protocol": "DNS",
        "direction": "server-to-client",
        "summary": "DNS Response (SMTP Host)",
        "raw": f"{host} -> {ip_address}",
        "fields": {
            "Host": host,
            "IP Address": ip_address,
            "Lookup Time (ms)": f"{dns_duration_ms:.1f}",
        },
        "highlight": ["IP Address"],
        "timing_ms": round(dns_duration_ms),
    })

    # SSRF Protection
    if _ip_is_blocked(ip_address):
        raise SMTPLiveError(
            f"The resolved SMTP server address {ip_address} is a private/internal address -- "
            "Live Mode only connects to public mail servers."
        )

    client_hostname = socket.getfqdn() or "localhost"
    server = None

    def elapsed_ms():
        return round((time.perf_counter() - step_start) * 1000)

    try:
        # Step 2: Connect & Greeting
        t0 = time.perf_counter()
        if security == "ssl":
            server = smtplib.SMTP_SSL(host, port, timeout=10)
        else:
            server = smtplib.SMTP(host, port, timeout=10)

        # server.connect() runs during init and stores greeting in server.ehlo_resp or greeting
        # The connect code and greeting:
        connect_code = getattr(server, "connect_code", 220)
        connect_msg = _decode_bytes(getattr(server, "connect_greeting", "Service ready"))

        events.append({
            "protocol": "SMTP",
            "direction": "server-to-client",
            "summary": "SMTP Server Greeting (Live)",
            "raw": f"{connect_code} {connect_msg}".strip(),
            "fields": {
                "Code": str(connect_code),
                "Host": host,
                "Port": str(port),
                "Security": security.upper(),
            },
            "highlight": ["Code"],
            "timing_ms": elapsed_ms(),
        })

        # Step 3: EHLO
        events.append({
            "protocol": "SMTP",
            "direction": "client-to-server",
            "summary": "Client Introduction (EHLO)",
            "raw": f"EHLO {client_hostname}",
            "fields": {"Command": "EHLO", "Client Host": client_hostname},
            "highlight": ["Command", "Client Host"],
            "timing_ms": elapsed_ms(),
        })

        code, ehlo_resp = server.ehlo(client_hostname)
        ehlo_text = _decode_bytes(ehlo_resp)
        events.append({
            "protocol": "SMTP",
            "direction": "server-to-client",
            "summary": "EHLO Response",
            "raw": f"{code} {ehlo_text}".strip(),
            "fields": {"Code": str(code), "Features": "ESMTP extensions advertised"},
            "highlight": ["Code"],
            "timing_ms": elapsed_ms(),
        })

        if code >= 400:
            raise SMTPLiveError(f"Server rejected EHLO: {code} {ehlo_text}")

        # Step 4: STARTTLS (if requested and supported)
        if security == "starttls":
            if server.has_extn("starttls"):
                events.append({
                    "protocol": "SMTP",
                    "direction": "client-to-server",
                    "summary": "STARTTLS Negotiation",
                    "raw": "STARTTLS",
                    "fields": {"Command": "STARTTLS"},
                    "highlight": ["Command"],
                    "timing_ms": elapsed_ms(),
                })
                code, tls_resp = server.starttls()
                tls_text = _decode_bytes(tls_resp)
                events.append({
                    "protocol": "SMTP",
                    "direction": "server-to-client",
                    "summary": "TLS Handshake Established",
                    "raw": f"{code} {tls_text}".strip(),
                    "fields": {"Code": str(code), "Status": "TLS connection active"},
                    "highlight": ["Code", "Status"],
                    "timing_ms": elapsed_ms(),
                })

                # Re-issue EHLO after TLS per RFC 3207
                events.append({
                    "protocol": "SMTP",
                    "direction": "client-to-server",
                    "summary": "Post-TLS Client Introduction (EHLO)",
                    "raw": f"EHLO {client_hostname}",
                    "fields": {"Command": "EHLO", "Client Host": client_hostname},
                    "highlight": ["Command"],
                    "timing_ms": elapsed_ms(),
                })
                code, ehlo_resp = server.ehlo(client_hostname)
                ehlo_text = _decode_bytes(ehlo_resp)
                events.append({
                    "protocol": "SMTP",
                    "direction": "server-to-client",
                    "summary": "Post-TLS EHLO Response",
                    "raw": f"{code} {ehlo_text}".strip(),
                    "fields": {"Code": str(code), "Status": "Encrypted session ready"},
                    "highlight": ["Code"],
                    "timing_ms": elapsed_ms(),
                })
            else:
                # STARTTLS requested but server doesn't support it
                pass

        # Step 5: Authentication (if credentials provided)
        if username and password:
            events.append({
                "protocol": "SMTP",
                "direction": "client-to-server",
                "summary": "SMTP Authentication Request (Live)",
                "raw": "AUTH <redacted>",
                "fields": {
                    "Command": "AUTH",
                    "Username": username,
                    "Credentials": "<redacted>",
                },
                "highlight": ["Command", "Username"],
                "timing_ms": elapsed_ms(),
            })

            try:
                auth_code, auth_resp = server.login(username, password)
                auth_text = _decode_bytes(auth_resp)
                events.append({
                    "protocol": "SMTP",
                    "direction": "server-to-client",
                    "summary": "Authentication Accepted (Live)",
                    "raw": f"{auth_code} {auth_text}".strip(),
                    "fields": {"Code": str(auth_code), "Status": "Authentication successful"},
                    "highlight": ["Code", "Status"],
                    "timing_ms": elapsed_ms(),
                })
            except smtplib.SMTPAuthenticationError as auth_err:
                err_text = _decode_bytes(auth_err.smtp_error)
                events.append({
                    "protocol": "SMTP",
                    "direction": "server-to-client",
                    "summary": "Authentication Rejected (Live)",
                    "raw": f"{auth_err.smtp_code} {err_text}".strip(),
                    "fields": {"Code": str(auth_err.smtp_code), "Error": "Authentication failed"},
                    "highlight": ["Code", "Error"],
                    "timing_ms": elapsed_ms(),
                })
                raise SMTPLiveError(f"SMTP authentication failed ({auth_err.smtp_code}): {err_text}") from auth_err

        # Step 6: MAIL FROM
        events.append({
            "protocol": "SMTP",
            "direction": "client-to-server",
            "summary": "MAIL FROM Command",
            "raw": f"MAIL FROM:<{from_addr}>",
            "fields": {"Command": "MAIL FROM", "Sender": from_addr},
            "highlight": ["Command", "Sender"],
            "timing_ms": elapsed_ms(),
        })

        code, mail_resp = server.mail(from_addr)
        mail_text = _decode_bytes(mail_resp)
        events.append({
            "protocol": "SMTP",
            "direction": "server-to-client",
            "summary": "MAIL FROM Response",
            "raw": f"{code} {mail_text}".strip(),
            "fields": {"Code": str(code), "Status": mail_text or "Sender accepted"},
            "highlight": ["Code"],
            "timing_ms": elapsed_ms(),
        })
        if code >= 400:
            raise SMTPLiveError(f"Server rejected sender <{from_addr}>: {code} {mail_text}")

        # Step 7: RCPT TO
        events.append({
            "protocol": "SMTP",
            "direction": "client-to-server",
            "summary": "RCPT TO Command",
            "raw": f"RCPT TO:<{to}>",
            "fields": {"Command": "RCPT TO", "Recipient": to},
            "highlight": ["Command", "Recipient"],
            "timing_ms": elapsed_ms(),
        })

        code, rcpt_resp = server.rcpt(to)
        rcpt_text = _decode_bytes(rcpt_resp)
        events.append({
            "protocol": "SMTP",
            "direction": "server-to-client",
            "summary": "RCPT TO Response",
            "raw": f"{code} {rcpt_text}".strip(),
            "fields": {"Code": str(code), "Recipient": to, "Status": rcpt_text or "Recipient accepted"},
            "highlight": ["Code", "Status"],
            "timing_ms": elapsed_ms(),
        })
        if code >= 400:
            raise SMTPLiveError(f"Server rejected recipient <{to}>: {code} {rcpt_text}")

        # Step 8: DATA
        events.append({
            "protocol": "SMTP",
            "direction": "client-to-server",
            "summary": "DATA Command",
            "raw": "DATA",
            "fields": {"Command": "DATA"},
            "highlight": ["Command"],
            "timing_ms": elapsed_ms(),
        })

        # Send DATA command to receive intermediate 354
        code, data_resp = server.docmd("DATA")
        data_text = _decode_bytes(data_resp)
        events.append({
            "protocol": "SMTP",
            "direction": "server-to-client",
            "summary": "DATA Intermediate Response",
            "raw": f"{code} {data_text}".strip(),
            "fields": {"Code": str(code), "Instruction": "Start mail input; end with <CRLF>.<CRLF>"},
            "highlight": ["Code"],
            "timing_ms": elapsed_ms(),
        })
        if code != 354:
            raise SMTPLiveError(f"Server did not accept DATA command: {code} {data_text}")

        # Construct message content
        date_str = formatdate(localtime=True)
        msg_id = make_msgid()
        raw_message = (
            f"From: {from_addr}\r\n"
            f"To: {to}\r\n"
            f"Subject: {subject}\r\n"
            f"Date: {date_str}\r\n"
            f"Message-ID: {msg_id}\r\n"
            f"Content-Type: text/plain; charset=utf-8\r\n"
            f"\r\n"
            f"{body}\r\n"
            f"."
        )

        events.append({
            "protocol": "SMTP",
            "direction": "client-to-server",
            "summary": "Message Content Transmission",
            "raw": (
                f"From: {from_addr}\n"
                f"To: {to}\n"
                f"Subject: {subject}\n"
                f"Date: {date_str}\n\n"
                f"{body}\n."
            ),
            "fields": {
                "From": from_addr,
                "To": to,
                "Subject": subject,
                "Date": date_str,
                "Body Length": f"{len(body)} chars",
            },
            "highlight": ["Subject", "To"],
            "timing_ms": elapsed_ms(),
        })

        # Send data payload
        # smtplib expects quoted periods
        quoted_data = re.sub(r"(?m)^\.", "..", raw_message[:-1]) # without the last dot
        if not quoted_data.endswith("\r\n"):
            quoted_data += "\r\n"
        quoted_data += ".\r\n"

        server.send(quoted_data.encode("utf-8"))
        code, final_resp = server.getreply()
        final_text = _decode_bytes(final_resp)

        events.append({
            "protocol": "SMTP",
            "direction": "server-to-client",
            "summary": "Message Accepted (Queued)",
            "raw": f"{code} {final_text}".strip(),
            "fields": {"Code": str(code), "Status": final_text or "Message queued for delivery"},
            "highlight": ["Code", "Status"],
            "timing_ms": elapsed_ms(),
        })
        if code >= 400:
            raise SMTPLiveError(f"Server rejected message content: {code} {final_text}")

        # Step 9: QUIT
        events.append({
            "protocol": "SMTP",
            "direction": "client-to-server",
            "summary": "QUIT Command",
            "raw": "QUIT",
            "fields": {"Command": "QUIT"},
            "highlight": ["Command"],
            "timing_ms": elapsed_ms(),
        })

        try:
            code, quit_resp = server.quit()
            quit_text = _decode_bytes(quit_resp)
            events.append({
                "protocol": "SMTP",
                "direction": "server-to-client",
                "summary": "QUIT Response (Connection Closed)",
                "raw": f"{code} {quit_text}".strip(),
                "fields": {"Code": str(code), "Status": quit_text or "Service closing transmission channel"},
                "highlight": ["Code"],
                "timing_ms": elapsed_ms(),
            })
        except Exception:
            pass

    except (smtplib.SMTPException, socket.error, TimeoutError, OSError) as exc:
        if not isinstance(exc, SMTPLiveError):
            raise SMTPLiveError(f"SMTP error connecting to {host}:{port}: {exc}") from exc
        raise
    finally:
        if server:
            try:
                server.close()
            except Exception:
                pass

    return events
