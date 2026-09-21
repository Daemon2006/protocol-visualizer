"""
run_tests.py
------------
Automated test suite verifying both Simulation Mode and Live Mode features,
protocol event structures, safety constraints (SSRF, scheme validation),
error handling, and structural requirements.
"""

import os
import re
import socket
import unittest
from unittest.mock import patch, MagicMock

from app import app
from live.smtp_live import send_live_mail, is_smtp_configured, SMTPLiveError
from live.dns_live import resolve_domain, DNSLookupError
from live.http_live import _ip_is_blocked


class ProtocolVisualizerTests(unittest.TestCase):

    def setUp(self):
        self.client = app.test_client()

    # =========================================================================
    # 1. SIMULATION MODE REGRESSIONS
    # =========================================================================
    def test_simulation_browsing(self):
        """Simulation Browsing must return exactly 4 deterministic events."""
        res = self.client.post("/api/simulate/browsing", json={"url": "example.com"})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["activity"], "browsing")
        self.assertEqual(len(data["events"]), 4)
        expected_summaries = ["DNS Query", "DNS Response", "HTTP GET Request", "HTTP Response"]
        self.assertEqual([e["summary"] for e in data["events"]], expected_summaries)
        self.assertEqual([e["step"] for e in data["events"]], [1, 2, 3, 4])
        # Protocols must be DNS and HTTP only
        self.assertEqual(set(e["protocol"] for e in data["events"]), {"DNS", "HTTP"})

    def test_simulation_browsing_404(self):
        """Simulation Browsing with 'notfound' in domain simulates a 404 response."""
        res = self.client.post("/api/simulate/browsing", json={"url": "notfound.test"})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn("404", data["events"][3]["fields"]["Status"])

    def test_simulation_mail(self):
        """Simulation Mail must return exactly 15 deterministic events."""
        res = self.client.post(
            "/api/simulate/mail",
            json={"to": "alice@example.com", "subject": "Test", "body": "Hello world!"}
        )
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["activity"], "mail")
        self.assertEqual(len(data["events"]), 15)
        self.assertEqual([e["step"] for e in data["events"]], list(range(1, 16)))
        # Every event must be DNS or SMTP
        for e in data["events"]:
            self.assertIn(e["protocol"], ["DNS", "SMTP"])
        # Check standard reply codes
        self.assertEqual(data["events"][2]["fields"]["Code"], "220")
        self.assertEqual(data["events"][14]["fields"]["Code"], "221 2.0.0")

    def test_simulation_streaming_qualities(self):
        """Simulation Streaming must return exactly 10 events for 360p, 720p, 1080p."""
        for quality in ["360p", "720p", "1080p"]:
            res = self.client.post("/api/simulate/streaming", json={"quality": quality})
            self.assertEqual(res.status_code, 200)
            data = res.get_json()
            self.assertEqual(data["activity"], "streaming")
            self.assertEqual(len(data["events"]), 10)
            self.assertEqual([e["step"] for e in data["events"]], list(range(1, 11)))
            # Quality path must appear in manifest and segment requests
            self.assertIn(f"/video/{quality}/playlist.m3u8", data["events"][2]["raw"])
            for seg_idx in [4, 6, 8]:
                self.assertIn(f"/video/{quality}/", data["events"][seg_idx]["raw"])

    # =========================================================================
    # 2. LIVE BROWSING & SAFETY
    # =========================================================================
    def test_live_browsing_scheme_validation(self):
        """Live Browsing rejects non-http/https schemes with 400."""
        for bad_scheme in ["ftp://example.com", "file:///etc/passwd", "javascript:alert(1)"]:
            res = self.client.post("/api/live/browsing", json={"url": bad_scheme})
            self.assertEqual(res.status_code, 400)

    def test_live_browsing_ssrf(self):
        """Live Browsing rejects loopback and private IP addresses with 502."""
        for private_host in ["http://127.0.0.1", "http://localhost", "http://192.168.1.1"]:
            res = self.client.post("/api/live/browsing", json={"url": private_host})
            self.assertEqual(res.status_code, 502)
            self.assertIn("private/internal", res.get_json()["error"])

    def test_ip_is_blocked(self):
        """Unit test for SSRF blocked IP logic."""
        self.assertTrue(_ip_is_blocked("127.0.0.1"))
        self.assertTrue(_ip_is_blocked("10.0.0.1"))
        self.assertTrue(_ip_is_blocked("192.168.0.1"))
        self.assertTrue(_ip_is_blocked("172.16.0.1"))
        self.assertTrue(_ip_is_blocked("169.254.1.1"))
        self.assertTrue(_ip_is_blocked("::1"))
        self.assertFalse(_ip_is_blocked("93.184.216.34")) # public IP (example.com)
        self.assertFalse(_ip_is_blocked("8.8.8.8"))

    # =========================================================================
    # 3. LIVE MAIL
    # =========================================================================
    def test_live_mail_unconfigured(self):
        """Live Mail when SMTP_HOST is not set returns clear 400 error without crashing."""
        with patch.dict(os.environ, {}, clear=True):
            res = self.client.post(
                "/api/live/mail",
                json={"to": "bob@example.com", "subject": "Test", "body": "Message"}
            )
            self.assertEqual(res.status_code, 400)
            self.assertIn("Live SMTP is not configured", res.get_json()["error"])

    def test_live_mail_full_flow_mock(self):
        """Live Mail execution flow with mocked SMTP server produces valid protocol events with redacted secrets."""
        with patch.dict(os.environ, {
            "SMTP_HOST": "mail.example.org",
            "SMTP_PORT": "587",
            "SMTP_SECURITY": "starttls",
            "SMTP_USERNAME": "testuser",
            "SMTP_PASSWORD": "supersecretpassword123",
            "SMTP_FROM": "sender@example.org"
        }):
            with patch("live.smtp_live.resolve_domain", return_value=("93.184.216.34", 15.2)):
                with patch("smtplib.SMTP") as mock_smtp_class:
                    mock_server = MagicMock()
                    mock_smtp_class.return_value = mock_server
                    mock_server.connect_code = 220
                    mock_server.connect_greeting = b"mail.example.org ESMTP Postfix"
                    mock_server.ehlo.return_value = (250, b"PIPELINING\nSIZE 10240000\nSTARTTLS\nAUTH PLAIN")
                    mock_server.has_extn.return_value = True
                    mock_server.starttls.return_value = (220, b"2.0.0 Ready to start TLS")
                    mock_server.login.return_value = (235, b"2.7.0 Authentication successful")
                    mock_server.mail.return_value = (250, b"2.1.0 Ok")
                    mock_server.rcpt.return_value = (250, b"2.1.5 Ok")
                    mock_server.docmd.return_value = (354, b"End data with <CRLF>.<CRLF>")
                    mock_server.getreply.return_value = (250, b"2.0.0 Ok: queued as 12345")
                    mock_server.quit.return_value = (221, b"2.0.0 Bye")

                    res = self.client.post(
                        "/api/live/mail",
                        json={"to": "recipient@example.com", "subject": "Greetings", "body": "Live test email"}
                    )
                    self.assertEqual(res.status_code, 200)
                    data = res.get_json()
                    self.assertEqual(data["mode"], "live")
                    events = data["events"]
                    self.assertGreater(len(events), 8)

                    # Verify sensitive secrets are NEVER exposed in any event
                    for e in events:
                        self.assertNotIn("supersecretpassword123", e["raw"])
                        self.assertNotIn("supersecretpassword123", str(e["fields"]))
                        if e.get("summary") == "SMTP Authentication Request (Live)":
                            self.assertIn("<redacted>", e["raw"])

    # =========================================================================
    # 4. STRUCTURAL & HTML CHECKS
    # =========================================================================
    def test_html_two_panel_layout(self):
        """Index page must contain exactly two main panels."""
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        html = res.get_data(as_text=True)

        # Count main sections with class 'panel'
        panel_count = len(re.findall(r'<section\s+class="panel\s+panel--', html))
        self.assertEqual(panel_count, 2, f"Expected exactly 2 panels, found {panel_count}")

        # Check that browser preview and live video containers exist
        self.assertIn('id="browser-preview-container"', html)
        self.assertIn('id="browser-preview-iframe"', html)
        self.assertIn('id="browser-preview-fallback"', html)
        self.assertIn('id="live-video-player"', html)
        self.assertIn('id="streaming-url"', html)

        # Check footer text does not claim simulated-only
        self.assertNotIn("No live network activity is used, all protocol behavior is simulated.", html)
        self.assertIn("Simulation + Live networking supported", html)

    def test_dom_ids_and_js_matching(self):
        """Every getElementById in static JS files must exist in index.html."""
        res = self.client.get("/")
        html = res.get_data(as_text=True)
        html_ids = set(re.findall(r'id=["\']([^"\']+)["\']', html))

        for js_file in ["static/js/visualizer.js", "static/js/activity_panel.js"]:
            with open(js_file, "r", encoding="utf-8") as f:
                content = f.read()

            # Find all document.getElementById calls
            js_ids = re.findall(r'getElementById\(["\']([^"\']+)["\']\)', content)
            for target_id in js_ids:
                self.assertIn(
                    target_id,
                    html_ids,
                    f"JavaScript file {js_file} references ID '{target_id}' which is missing in templates/index.html"
                )

            # Balanced brackets check using accurate tokenizer
            state = "CODE"
            line_no = 1
            stack = []
            matching = {')': '(', ']': '[', '}': '{'}
            i = 0
            while i < len(content):
                ch = content[i]
                if ch == "\n":
                    line_no += 1

                if state == "CODE":
                    if ch == "/" and i + 1 < len(content) and content[i + 1] == "/":
                        state = "LINE_COMMENT"
                        i += 1
                    elif ch == "/" and i + 1 < len(content) and content[i + 1] == "*":
                        state = "BLOCK_COMMENT"
                        i += 1
                    elif ch == '"':
                        state = "DOUBLE_QUOTE"
                    elif ch == "'":
                        state = "SINGLE_QUOTE"
                    elif ch == '`':
                        state = "TEMPLATE_STRING"
                    elif ch in "([{":
                        stack.append((ch, line_no))
                    elif ch in ")]}":
                        self.assertTrue(len(stack) > 0, f"Unmatched '{ch}' at line {line_no} in {js_file}")
                        expected = matching[ch]
                        actual, open_line = stack.pop()
                        self.assertEqual(
                            expected,
                            actual,
                            f"Mismatched bracket '{ch}' at line {line_no} (opened '{actual}' at line {open_line}) in {js_file}"
                        )
                elif state == "LINE_COMMENT":
                    if ch == "\n":
                        state = "CODE"
                elif state == "BLOCK_COMMENT":
                    if ch == "*" and i + 1 < len(content) and content[i + 1] == "/":
                        state = "CODE"
                        i += 1
                elif state == "DOUBLE_QUOTE":
                    if ch == "\\" and i + 1 < len(content):
                        i += 1
                    elif ch == '"':
                        state = "CODE"
                elif state == "SINGLE_QUOTE":
                    if ch == "\\" and i + 1 < len(content):
                        i += 1
                    elif ch == "'":
                        state = "CODE"
                elif state == "TEMPLATE_STRING":
                    if ch == "\\" and i + 1 < len(content):
                        i += 1
                    elif ch == '`':
                        state = "CODE"
                i += 1

            self.assertEqual(len(stack), 0, f"Unclosed brackets remaining in {js_file}: {stack}")


if __name__ == "__main__":
    unittest.main()
