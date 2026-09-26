"""
smtp_sim.py
-----------
Builds a simulated DNS/MX lookup followed by a full SMTP conversation
for sending one email.

This does NOT connect to any real mail server and does NOT send a
real email. Every line of protocol text is built from fixed templates
using real SMTP command/response codes, so the *shape* of the exchange
is accurate even though nothing actually leaves the machine.

The sequence mirrors a real mail submission:
    1) DNS Query  (MX)      -- "which server handles mail for this domain?"
    2) DNS Response (MX)    -- "here's the mail server"
    3) SMTP Greeting        -- server says hello
    4) EHLO / response      -- client introduces itself, server lists features
    5) MAIL FROM / response -- who the mail is from
    6) RCPT TO / response   -- who the mail is to
    7) DATA / response      -- "ok, send the message"
    8) message data / response -- the actual headers + body, then "queued"
    9) QUIT / response      -- close the connection
"""

# Fixed simulated sender, as specified by the assignment. This does NOT
# change based on user input -- only the recipient (To), Subject, and
# Body come from the Mail form.
FIXED_SENDER = "student@example.edu"
CLIENT_HOSTNAME = "client.example.com"


def _extract_domain(email: str) -> str:
    """Pull the part after '@' out of an email address."""
    return email.split("@", 1)[1] if "@" in email else email


def simulate_mail(to: str, subject: str, body: str):
    """
    Return the full ordered list of protocol events for sending one
    simulated email to `to` with the given `subject` and `body`.

    The recipient's mail server is derived from their domain (e.g.
    alice@example.com -> mail.example.com), matching how a real MX
    lookup would route mail for that domain -- it is not hardcoded to
    always be "example.com".
    """
    recipient_domain = _extract_domain(to)
    mail_server = f"mail.{recipient_domain}"

    events = []

    # ---------- 1-2: DNS / MX lookup ----------
    events.append({
        "protocol": "DNS",
        "transport": "UDP",
        "direction": "client-to-server",
        "summary": "DNS Query (MX)",
        "raw": f"Query: {recipient_domain}  Type: MX",
        "fields": {"Domain": recipient_domain, "Type": "MX"},
        "highlight": ["Domain", "Type"],
        "timing_ms": 0,
    })
    events.append({
        "protocol": "DNS",
        "transport": "UDP",
        "direction": "server-to-client",
        "summary": "DNS Response (MX)",
        "raw": f"{recipient_domain} -> MX 10 {mail_server}",
        "fields": {"Domain": recipient_domain, "Mail Server": mail_server, "Priority": "10"},
        "highlight": ["Mail Server"],
        "timing_ms": 40,
    })

    # ---------- 3: SMTP greeting ----------
    events.append({
        "protocol": "SMTP",
        "transport": "TCP",
        "direction": "server-to-client",
        "summary": "SMTP Greeting",
        "raw": f"220 {mail_server} ESMTP Service Ready",
        "fields": {"Code": "220", "Server": mail_server},
        "highlight": ["Code"],
        "timing_ms": 80,
    })

    # ---------- 4: EHLO ----------
    events.append({
        "protocol": "SMTP",
        "transport": "TCP",
        "direction": "client-to-server",
        "summary": "EHLO",
        "raw": f"EHLO {CLIENT_HOSTNAME}",
        "fields": {"Command": "EHLO", "Client Hostname": CLIENT_HOSTNAME},
        "highlight": ["Command"],
        "timing_ms": 120,
    })
    events.append({
        "protocol": "SMTP",
        "transport": "TCP",
        "direction": "server-to-client",
        "summary": "EHLO Response",
        "raw": (
            f"250-{mail_server}\n"
            "250-SIZE 35882577\n"
            "250-8BITMIME\n"
            "250-STARTTLS\n"
            "250 OK"
        ),
        "fields": {"Code": "250", "Server": mail_server},
        "highlight": ["Code"],
        "timing_ms": 160,
    })

    # ---------- 5: MAIL FROM ----------
    events.append({
        "protocol": "SMTP",
        "transport": "TCP",
        "direction": "client-to-server",
        "summary": "MAIL FROM",
        "raw": f"MAIL FROM:<{FIXED_SENDER}>",
        "fields": {"Command": "MAIL FROM", "Sender": FIXED_SENDER},
        "highlight": ["Sender"],
        "timing_ms": 200,
    })
    events.append({
        "protocol": "SMTP",
        "transport": "TCP",
        "direction": "server-to-client",
        "summary": "MAIL FROM Response",
        "raw": "250 2.1.0 OK",
        "fields": {"Code": "250 2.1.0"},
        "highlight": ["Code"],
        "timing_ms": 240,
    })

    # ---------- 6: RCPT TO ----------
    events.append({
        "protocol": "SMTP",
        "transport": "TCP",
        "direction": "client-to-server",
        "summary": "RCPT TO",
        "raw": f"RCPT TO:<{to}>",
        "fields": {"Command": "RCPT TO", "Recipient": to},
        "highlight": ["Recipient"],
        "timing_ms": 280,
    })
    events.append({
        "protocol": "SMTP",
        "transport": "TCP",
        "direction": "server-to-client",
        "summary": "RCPT TO Response",
        "raw": "250 2.1.5 OK",
        "fields": {"Code": "250 2.1.5"},
        "highlight": ["Code"],
        "timing_ms": 320,
    })

    # ---------- 7: DATA ----------
    events.append({
        "protocol": "SMTP",
        "transport": "TCP",
        "direction": "client-to-server",
        "summary": "DATA",
        "raw": "DATA",
        "fields": {"Command": "DATA"},
        "highlight": ["Command"],
        "timing_ms": 360,
    })
    events.append({
        "protocol": "SMTP",
        "transport": "TCP",
        "direction": "server-to-client",
        "summary": "DATA Response",
        "raw": "354 End data with <CR><LF>.<CR><LF>",
        "fields": {"Code": "354"},
        "highlight": ["Code"],
        "timing_ms": 400,
    })

    # ---------- 8: message data (headers + blank line + body) ----------
    message_data = (
        f"From: {FIXED_SENDER}\n"
        f"To: {to}\n"
        f"Subject: {subject}\n"
        "\n"
        f"{body}"
    )
    events.append({
        "protocol": "SMTP",
        "transport": "TCP",
        "direction": "client-to-server",
        "summary": "Message Data",
        "raw": message_data,
        "fields": {"From": FIXED_SENDER, "To": to, "Subject": subject},
        "highlight": ["Subject"],
        "timing_ms": 440,
    })
    events.append({
        "protocol": "SMTP",
        "transport": "TCP",
        "direction": "server-to-client",
        "summary": "Message Queued",
        "raw": "250 2.0.0 OK: queued",
        "fields": {"Code": "250 2.0.0"},
        "highlight": ["Code"],
        "timing_ms": 480,
    })

    # ---------- 9: QUIT ----------
    events.append({
        "protocol": "SMTP",
        "transport": "TCP",
        "direction": "client-to-server",
        "summary": "QUIT",
        "raw": "QUIT",
        "fields": {"Command": "QUIT"},
        "highlight": ["Command"],
        "timing_ms": 520,
    })
    events.append({
        "protocol": "SMTP",
        "transport": "TCP",
        "direction": "server-to-client",
        "summary": "Connection Closed",
        "raw": "221 2.0.0 Bye",
        "fields": {"Code": "221 2.0.0"},
        "highlight": ["Code"],
        "timing_ms": 560,
    })

    return events
