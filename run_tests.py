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
from live.flow_control_live import LiveFlowControlError


class ProtocolVisualizerTests(unittest.TestCase):

    def setUp(self):
        self.client = app.test_client()

    # =========================================================================
    # 1. SIMULATION MODE REGRESSIONS
    # =========================================================================
    def test_simulation_browsing(self):
        """Simulation Browsing must return exactly 4 deterministic events with UDP/TCP transport."""
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
        # Transport layer mapping: DNS -> UDP, HTTP -> TCP
        self.assertEqual([e["transport"] for e in data["events"]], ["UDP", "UDP", "TCP", "TCP"])

    def test_simulation_browsing_404(self):
        """Simulation Browsing with 'notfound' in domain simulates a 404 response."""
        res = self.client.post("/api/simulate/browsing", json={"url": "notfound.test"})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn("404", data["events"][3]["fields"]["Status"])

    def test_simulation_mail(self):
        """Simulation Mail must return exactly 15 deterministic events with UDP/TCP transport."""
        res = self.client.post(
            "/api/simulate/mail",
            json={"to": "alice@example.com", "subject": "Test", "body": "Hello world!"}
        )
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["activity"], "mail")
        self.assertEqual(len(data["events"]), 15)
        self.assertEqual([e["step"] for e in data["events"]], list(range(1, 16)))
        # Every event must be DNS (UDP) or SMTP (TCP)
        for e in data["events"]:
            self.assertIn(e["protocol"], ["DNS", "SMTP"])
            expected_transport = "UDP" if e["protocol"] == "DNS" else "TCP"
            self.assertEqual(e["transport"], expected_transport)
        # Check standard reply codes
        self.assertEqual(data["events"][2]["fields"]["Code"], "220")
        self.assertEqual(data["events"][14]["fields"]["Code"], "221 2.0.0")

    def test_simulation_streaming_qualities(self):
        """Simulation Streaming must return exactly 10 events for 360p, 720p, 1080p with UDP/TCP transport."""
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
            # Transport layer mapping: first 2 DNS -> UDP, remaining 8 HTTP -> TCP
            self.assertEqual(
                [e["transport"] for e in data["events"]],
                ["UDP", "UDP"] + ["TCP"] * 8
            )

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
                    # and transport metadata is UDP for DNS and TCP for SMTP
                    for e in events:
                        self.assertNotIn("supersecretpassword123", e["raw"])
                        self.assertNotIn("supersecretpassword123", str(e["fields"]))
                        expected_transport = "UDP" if e["protocol"] == "DNS" else "TCP"
                        self.assertEqual(e["transport"], expected_transport)
                        if e.get("summary") == "SMTP Authentication Request (Live)":
                            self.assertIn("<redacted>", e["raw"])

    def test_transport_layer_live_and_frontend(self):
        """Verify Live DNS/HTTP transport metadata and frontend TCP/UDP visualizer rules."""
        with patch("live.dns_live.resolve_domain", return_value=("93.184.216.34", 12.0)):
            res_dns = self.client.post("/api/live/dns", json={"url": "example.com"})
            self.assertEqual(res_dns.status_code, 200)
            dns_events = res_dns.get_json()["events"]
            self.assertEqual([e["transport"] for e in dns_events], ["UDP", "UDP"])

            with patch("live.http_live.fetch_live", return_value=(200, "OK", {"Content-Type": "text/html"}, 28.0)):
                res = self.client.post("/api/live/browsing", json={"url": "example.com"})
                self.assertEqual(res.status_code, 200)
                data = res.get_json()
                self.assertEqual([e["transport"] for e in data["events"]], ["UDP", "UDP", "TCP", "TCP"])

        with open("static/js/visualizer.js", "r", encoding="utf-8") as f:
            viz_js = f.read()

        # Verify dynamic TCP connection start detection (no hardcoded step === 3 or index === 2)
        self.assertIn("isTcpConnectionStart", viz_js)
        self.assertIn('current.transport !== "TCP"', viz_js)
        self.assertIn('prev.transport !== "TCP"', viz_js)
        self.assertNotIn("step === 3", viz_js)
        self.assertNotIn("index === 2", viz_js)

        # Verify reusable transport renderer, TCP handshake, UDP datagram, direction, and fallback
        self.assertIn("renderTransportLayer", viz_js)
        self.assertIn("transport-handshake--animate", viz_js)
        self.assertIn("transport-handshake--established", viz_js)
        self.assertIn("transport-layer--udp", viz_js)
        self.assertIn("transport-layer--tcp", viz_js)
        self.assertIn("transport-arrow--c2s", viz_js)
        self.assertIn("transport-arrow--s2c", viz_js)
        self.assertIn("Not specified", viz_js)

        # Verify Pause/Resume freezes CSS animation via transport-viz--paused
        self.assertIn("transport-viz--paused", viz_js)
        self.assertIn("remainingStepMs", viz_js)

        with open("static/css/style.css", "r", encoding="utf-8") as f:
            css = f.read()
        self.assertIn("animation-play-state: paused !important", css)
        self.assertIn("--color-dns", css)
        self.assertIn("--color-http", css)
        self.assertIn("--color-smtp", css)
        self.assertIn("--color-tcp", css)
        self.assertIn("--color-udp", css)
        self.assertIn("--color-success", css)
        self.assertIn("--color-error", css)

    def test_invalid_inputs_regression(self):
        """Verify all existing input validation and error handling remain intact."""
        # Browsing empty URL
        self.assertEqual(self.client.post("/api/simulate/browsing", json={"url": "   "}).status_code, 400)
        # Mail validation
        self.assertEqual(self.client.post("/api/simulate/mail", json={"to": "", "subject": "S", "body": "B"}).status_code, 400)
        self.assertEqual(self.client.post("/api/simulate/mail", json={"to": "invalid-email", "subject": "S", "body": "B"}).status_code, 400)
        self.assertEqual(self.client.post("/api/simulate/mail", json={"to": "a@b.com", "subject": "", "body": "B"}).status_code, 400)
        self.assertEqual(self.client.post("/api/simulate/mail", json={"to": "a@b.com", "subject": "S", "body": ""}).status_code, 400)
        # Streaming invalid quality
        self.assertEqual(self.client.post("/api/simulate/streaming", json={"quality": "4K"}).status_code, 400)

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

    # =========================================================================
    # 5. FLOW CONTROL TESTS
    # =========================================================================
    def test_simulation_stop_and_wait(self):
        """Stop-and-Wait must return 8 deterministic events with alternating bits 0->1->0->1."""
        res = self.client.post(
            "/api/simulate/flow-control",
            json={"variant": "stop-and-wait", "frame_count": 4, "scenario": "normal"}
        )
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["activity"], "flow-control")
        self.assertEqual(data["variant"], "stop-and-wait")
        events = data["events"]
        self.assertEqual(len(events), 8)

        expected_summaries = [
            "Frame 0 Transmitted (Seq 0)",
            "ACK 0 Received",
            "Frame 1 Transmitted (Seq 1)",
            "ACK 1 Received",
            "Frame 2 Transmitted (Seq 0)",
            "ACK 0 Received",
            "Frame 3 Transmitted (Seq 1)",
            "ACK 1 Received",
        ]
        self.assertEqual([e["summary"] for e in events], expected_summaries)

        # Verify sequence numbers alternate 0 -> 1 -> 0 -> 1 and each frame is ACKed before the next
        for i in range(4):
            frame_event = events[i * 2]
            ack_event = events[i * 2 + 1]
            expected_seq = str(i % 2)

            self.assertEqual(frame_event["direction"], "client-to-server")
            self.assertEqual(frame_event["fields"]["Seq No"], expected_seq)
            self.assertEqual(frame_event["fields"]["Ack No"], "-")

            self.assertEqual(ack_event["direction"], "server-to-client")
            self.assertEqual(ack_event["fields"]["Seq No"], "-")
            self.assertEqual(ack_event["fields"]["Ack No"], expected_seq)

    def test_simulation_stop_and_wait_arq_normal(self):
        """Stop-and-Wait ARQ Normal must return 8 events with alternating sequence bits."""
        res = self.client.post(
            "/api/simulate/flow-control",
            json={"variant": "stop-and-wait-arq", "frame_count": 4, "scenario": "normal"}
        )
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["activity"], "flow-control")
        self.assertEqual(data["variant"], "stop-and-wait-arq")
        events = data["events"]
        self.assertEqual(len(events), 8)

        expected_summaries = [
            "Frame 0 Transmitted",
            "ACK 0 Received",
            "Frame 1 Transmitted",
            "ACK 1 Received",
            "Frame 2 Transmitted",
            "ACK 0 Received",
            "Frame 3 Transmitted",
            "ACK 1 Received",
        ]
        self.assertEqual([e["summary"] for e in events], expected_summaries)

        for i in range(4):
            frame_evt = events[i * 2]
            ack_evt = events[i * 2 + 1]
            exp_seq = str(i % 2)
            self.assertEqual(frame_evt["fields"]["Seq No"], exp_seq)
            self.assertEqual(ack_evt["fields"]["Ack No"], exp_seq)

    def test_simulation_stop_and_wait_arq_frame_loss(self):
        """Stop-and-Wait ARQ Frame Loss must show dropped frame, timeout, retransmission with same Seq, and recovery."""
        res = self.client.post(
            "/api/simulate/flow-control",
            json={"variant": "stop-and-wait-arq", "frame_count": 4, "scenario": "frame_loss"}
        )
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        events = data["events"]
        summaries = [e["summary"] for e in events]

        self.assertIn("Frame 1 Lost in Transit", summaries)
        self.assertIn("Timeout Waiting for ACK 1", summaries)
        self.assertIn("Retransmitting Frame 1", summaries)
        self.assertIn("ACK 1 Received", summaries)

        lost_idx = summaries.index("Frame 1 Lost in Transit")
        timeout_idx = summaries.index("Timeout Waiting for ACK 1")
        retrans_idx = summaries.index("Retransmitting Frame 1")
        ack_idx = summaries.index("ACK 1 Received")

        self.assertTrue(lost_idx < timeout_idx < retrans_idx < ack_idx)

        lost_evt = events[lost_idx]
        timeout_evt = events[timeout_idx]
        retrans_evt = events[retrans_idx]

        self.assertEqual(lost_evt["fields"]["Seq No"], "1")
        self.assertIn("lost", lost_evt["fields"]["Status"].lower())

        self.assertEqual(timeout_evt["fields"]["Seq No"], "1")
        self.assertEqual(timeout_evt["fields"]["Timer"].lower(), "expired")

        # Retransmission must retain the exact same Seq No: 1
        self.assertEqual(retrans_evt["fields"]["Seq No"], "1")
        self.assertIn("retransmitting", retrans_evt["fields"]["Status"].lower())

        # Recovery succeeds: last frame is Frame 3 ACK
        self.assertEqual(events[-1]["summary"], "ACK 1 Received")
        self.assertEqual(events[-2]["summary"], "Frame 3 Transmitted")

    def test_simulation_stop_and_wait_arq_ack_loss(self):
        """Stop-and-Wait ARQ ACK Loss must verify lost ACK, timeout, retransmission, duplicate detection, discard, and re-ACK."""
        res = self.client.post(
            "/api/simulate/flow-control",
            json={"variant": "stop-and-wait-arq", "frame_count": 4, "scenario": "ack_loss"}
        )
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        events = data["events"]
        summaries = [e["summary"] for e in events]

        expected_subset = [
            "ACK 1 Lost in Transit",
            "Timeout Waiting for ACK 1",
            "Retransmitting Frame 1",
            "Duplicate Frame 1 Detected",
            "Duplicate Discarded",
            "ACK 1 Re-sent",
            "ACK 1 Received",
        ]
        for item in expected_subset:
            self.assertIn(item, summaries)

        indices = [summaries.index(item) for item in expected_subset]
        self.assertEqual(indices, sorted(indices), "Semantic events must occur in chronological order")

        # Retransmitted frame retains Seq No 1
        retrans_evt = events[summaries.index("Retransmitting Frame 1")]
        self.assertEqual(retrans_evt["fields"]["Seq No"], "1")

        # Duplicate identified as same Seq No
        dup_evt = events[summaries.index("Duplicate Frame 1 Detected")]
        self.assertEqual(dup_evt["fields"]["Seq No"], "1")
        self.assertEqual(dup_evt["fields"]["Receiver State"], "DUPLICATE_DETECTED")

        # Duplicate payload discarded
        discard_evt = events[summaries.index("Duplicate Discarded")]
        self.assertEqual(discard_evt["fields"]["Receiver State"], "DUPLICATE_DISCARDED")
        self.assertIn("discarded", discard_evt["fields"]["Status"].lower())

        # Receiver re-sends ACK 1
        resend_evt = events[summaries.index("ACK 1 Re-sent")]
        self.assertEqual(resend_evt["fields"]["Ack No"], "1")

        # Recovery completes
        recovery_evt = events[summaries.index("ACK 1 Received")]
        self.assertEqual(recovery_evt["fields"]["Ack No"], "1")
        self.assertEqual(recovery_evt["fields"]["Sender State"], "READY_FOR_NEXT")

    def test_simulation_stop_and_wait_arq_delayed_ack(self):
        """Stop-and-Wait ARQ Delayed ACK must show timeout, retransmission, duplicate handling, and recovery."""
        res = self.client.post(
            "/api/simulate/flow-control",
            json={"variant": "stop-and-wait-arq", "frame_count": 4, "scenario": "delayed_ack"}
        )
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        events = data["events"]
        summaries = [e["summary"] for e in events]

        has_timeout = any("timeout" in s.lower() or e["fields"].get("Timer") == "Expired" for e, s in zip(events, summaries))
        has_retrans = any("retransmitting" in s.lower() for s in summaries)
        has_duplicate = any("duplicate" in s.lower() and "detected" in s.lower() for s in summaries)
        has_discard = any("discard" in s.lower() for s in summaries)
        has_recovery = any("ack 1 received" in s.lower() for s in summaries)

        self.assertTrue(has_timeout, "Expected timeout event in delayed ACK scenario")
        self.assertTrue(has_retrans, "Expected retransmission event in delayed ACK scenario")
        self.assertTrue(has_duplicate, "Expected duplicate detection in delayed ACK scenario")
        self.assertTrue(has_discard, "Expected duplicate discard in delayed ACK scenario")
        self.assertTrue(has_recovery, "Expected ACK recovery in delayed ACK scenario")

        # Retransmission keeps Seq No 1
        retrans_evts = [e for e in events if "retransmitting" in e["summary"].lower()]
        self.assertTrue(len(retrans_evts) > 0)
        self.assertEqual(retrans_evts[0]["fields"]["Seq No"], "1")

    def test_flow_control_invalid_inputs(self):
        """Verify invalid Flow Control inputs return 400 with a descriptive JSON error."""
        invalid_payloads = [
            {"variant": "go-back-n"},
            {},
            {"variant": "stop-and-wait", "frame_count": 1},
            {"variant": "stop-and-wait", "frame_count": 7},
            {"variant": "stop-and-wait", "frame_count": "four"},
            {"variant": "stop-and-wait-arq", "scenario": "chaos"},
        ]
        for payload in invalid_payloads:
            res = self.client.post("/api/simulate/flow-control", json=payload)
            self.assertEqual(res.status_code, 400, f"Expected 400 for payload: {payload}")
            self.assertTrue(res.is_json, f"Response should be JSON for payload: {payload}")
            data = res.get_json()
            self.assertIn("error", data, f"Missing 'error' field in response for payload: {payload}")
            self.assertTrue(len(data["error"]) > 0)

    def test_flow_control_event_schema(self):
        """Verify Flow Control events adhere strictly to the visualizer schema and DATA LINK layer transport."""
        for variant in ["stop-and-wait", "stop-and-wait-arq"]:
            res = self.client.post("/api/simulate/flow-control", json={"variant": variant, "frame_count": 4})
            self.assertEqual(res.status_code, 200)
            events = res.get_json()["events"]
            expected_keys = {
                "step", "protocol", "transport", "direction",
                "summary", "raw", "fields", "highlight", "timing_ms"
            }
            expected_proto = "STOP-AND-WAIT" if variant == "stop-and-wait" else "SW-ARQ"

            for i, evt in enumerate(events, start=1):
                self.assertTrue(expected_keys.issubset(evt.keys()), f"Event missing required schema keys: {evt}")
                self.assertEqual(evt["step"], i, "Step numbers must be strictly sequential (1, 2, 3, ...)")
                self.assertEqual(evt["protocol"], expected_proto)
                self.assertEqual(evt["transport"], "DATA LINK", "Flow Control transport must be DATA LINK, not TCP/UDP")
                self.assertIn(evt["direction"], ["client-to-server", "server-to-client"])
                self.assertIsInstance(evt["fields"], dict)
                self.assertIsInstance(evt["highlight"], list)
                self.assertIsInstance(evt["timing_ms"], (int, float))

    # =========================================================================
    # 6. LIVE FLOW CONTROL TESTS
    # =========================================================================
    def test_live_flow_control_stop_and_wait(self):
        """Live Stop-and-Wait over real OS UDP sockets must return 8 events with alternating bits 0->1->0->1."""
        res = self.client.post(
            "/api/live/flow-control",
            json={"variant": "stop-and-wait", "frame_count": 4, "scenario": "normal"}
        )
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["activity"], "flow-control")
        self.assertEqual(data["mode"], "live")
        self.assertEqual(data["variant"], "stop-and-wait")
        events = data["events"]
        self.assertEqual(len(events), 8)

        expected_summaries = [
            "Frame 0 Transmitted (Seq 0)",
            "ACK 0 Received",
            "Frame 1 Transmitted (Seq 1)",
            "ACK 1 Received",
            "Frame 2 Transmitted (Seq 0)",
            "ACK 0 Received",
            "Frame 3 Transmitted (Seq 1)",
            "ACK 1 Received",
        ]
        self.assertEqual([e["summary"] for e in events], expected_summaries)
        self.assertEqual([e["step"] for e in events], list(range(1, 9)))
        self.assertEqual(set(e["protocol"] for e in events), {"STOP-AND-WAIT"})
        self.assertEqual(set(e["transport"] for e in events), {"DATA LINK"})

        for i in range(4):
            frame_event = events[i * 2]
            ack_event = events[i * 2 + 1]
            expected_seq = str(i % 2)

            self.assertEqual(frame_event["direction"], "client-to-server")
            self.assertEqual(frame_event["fields"]["Seq No"], expected_seq)
            self.assertEqual(frame_event["fields"]["Ack No"], "-")
            self.assertIn("Local Endpoint", frame_event["fields"])

            self.assertEqual(ack_event["direction"], "server-to-client")
            self.assertEqual(ack_event["fields"]["Seq No"], "-")
            self.assertEqual(ack_event["fields"]["Ack No"], expected_seq)
            self.assertIn("Local Endpoint", ack_event["fields"])

    def test_live_flow_control_arq_normal(self):
        """Live Stop-and-Wait ARQ Normal over real UDP sockets must return 8 events with alternating 0/1 sequence."""
        res = self.client.post(
            "/api/live/flow-control",
            json={"variant": "stop-and-wait-arq", "frame_count": 4, "scenario": "normal"}
        )
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["activity"], "flow-control")
        self.assertEqual(data["mode"], "live")
        self.assertEqual(data["variant"], "stop-and-wait-arq")
        events = data["events"]
        self.assertEqual(len(events), 8)
        self.assertEqual(set(e["protocol"] for e in events), {"SW-ARQ"})
        self.assertEqual(set(e["transport"] for e in events), {"DATA LINK"})

        for i in range(4):
            frame_evt = events[i * 2]
            ack_evt = events[i * 2 + 1]
            exp_seq = str(i % 2)
            self.assertEqual(frame_evt["fields"]["Seq No"], exp_seq)
            self.assertEqual(ack_evt["fields"]["Ack No"], exp_seq)

    def test_live_flow_control_arq_frame_loss(self):
        """Live ARQ Frame Loss over real sockets must show frame loss, socket timeout, retransmission, and recovery."""
        res = self.client.post(
            "/api/live/flow-control",
            json={"variant": "stop-and-wait-arq", "frame_count": 4, "scenario": "frame_loss"}
        )
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["mode"], "live")
        events = data["events"]
        summaries = [e["summary"] for e in events]

        # Verify semantic order: Frame 1 Lost in Transit -> Timeout Waiting for ACK 1 -> Retransmitting Frame 1 -> ACK 1 Received
        self.assertIn("Frame 1 Lost in Transit", summaries)
        self.assertIn("Timeout Waiting for ACK 1", summaries)
        self.assertIn("Retransmitting Frame 1", summaries)
        self.assertIn("ACK 1 Received", summaries)

        loss_idx = summaries.index("Frame 1 Lost in Transit")
        timeout_idx = summaries.index("Timeout Waiting for ACK 1")
        retrans_idx = summaries.index("Retransmitting Frame 1")
        ack_idx = summaries.index("ACK 1 Received")

        self.assertTrue(loss_idx < timeout_idx < retrans_idx < ack_idx)

        # Structured field assertions
        lost_evt = events[loss_idx]
        self.assertEqual(lost_evt["fields"]["Seq No"], "1")

        timeout_evt = events[timeout_idx]
        self.assertEqual(timeout_evt["fields"]["Timer"], "Expired")
        self.assertEqual(timeout_evt["fields"]["Sender State"], "TIMEOUT_EXPIRED")

        retrans_evt = events[retrans_idx]
        self.assertEqual(retrans_evt["fields"]["Seq No"], "1")

        recovery_evt = events[ack_idx]
        self.assertEqual(recovery_evt["fields"]["Ack No"], "1")
        self.assertEqual(recovery_evt["fields"]["Sender State"], "READY_FOR_NEXT")

    def test_live_flow_control_arq_ack_loss(self):
        """Live ARQ ACK Loss over real sockets must verify lost ACK, timeout, duplicate detection, discard, and re-ACK."""
        res = self.client.post(
            "/api/live/flow-control",
            json={"variant": "stop-and-wait-arq", "frame_count": 4, "scenario": "ack_loss"}
        )
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["mode"], "live")
        events = data["events"]
        summaries = [e["summary"] for e in events]

        self.assertIn("ACK 1 Lost in Transit", summaries)
        self.assertIn("Timeout Waiting for ACK 1", summaries)
        self.assertIn("Retransmitting Frame 1", summaries)
        self.assertIn("Duplicate Frame 1 Detected", summaries)
        self.assertIn("Duplicate Discarded", summaries)
        self.assertIn("ACK 1 Re-sent", summaries)
        self.assertIn("ACK 1 Received", summaries)

        ack_loss_idx = summaries.index("ACK 1 Lost in Transit")
        timeout_idx = summaries.index("Timeout Waiting for ACK 1")
        retrans_idx = summaries.index("Retransmitting Frame 1")
        dup_detect_idx = summaries.index("Duplicate Frame 1 Detected")
        dup_discard_idx = summaries.index("Duplicate Discarded")
        re_ack_idx = summaries.index("ACK 1 Re-sent")
        recovery_idx = summaries.index("ACK 1 Received")

        self.assertTrue(
            ack_loss_idx < timeout_idx < retrans_idx < dup_detect_idx < dup_discard_idx < re_ack_idx < recovery_idx
        )

        retrans_evt = events[retrans_idx]
        self.assertEqual(retrans_evt["fields"]["Seq No"], "1")

        dup_evt = events[dup_detect_idx]
        self.assertEqual(dup_evt["fields"]["Receiver State"], "DUPLICATE_DETECTED")

        discard_evt = events[dup_discard_idx]
        self.assertEqual(discard_evt["fields"]["Receiver State"], "DUPLICATE_DISCARDED")

        re_ack_evt = events[re_ack_idx]
        self.assertEqual(re_ack_evt["fields"]["Ack No"], "1")

        recovery_evt = events[recovery_idx]
        self.assertEqual(recovery_evt["fields"]["Ack No"], "1")
        self.assertEqual(recovery_evt["fields"]["Sender State"], "READY_FOR_NEXT")

    def test_live_flow_control_arq_delayed_ack(self):
        """Live ARQ Delayed ACK over real sockets must show timeout, retransmission, duplicate handling, and recovery."""
        res = self.client.post(
            "/api/live/flow-control",
            json={"variant": "stop-and-wait-arq", "frame_count": 4, "scenario": "delayed_ack"}
        )
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["mode"], "live")
        events = data["events"]
        summaries = [e["summary"] for e in events]

        has_timeout = any("timeout" in s.lower() or e["fields"].get("Timer") == "Expired" for e, s in zip(events, summaries))
        has_retrans = any("retransmitting" in s.lower() for s in summaries)
        has_duplicate = any("duplicate" in s.lower() and "detected" in s.lower() for s in summaries)
        has_discard = any("discard" in s.lower() for s in summaries)
        has_recovery = any("ack 1 received" in s.lower() for s in summaries)

        self.assertTrue(has_timeout, "Expected timeout event in delayed ACK scenario")
        self.assertTrue(has_retrans, "Expected retransmission event in delayed ACK scenario")
        self.assertTrue(has_duplicate, "Expected duplicate detection in delayed ACK scenario")
        self.assertTrue(has_discard, "Expected duplicate discard in delayed ACK scenario")
        self.assertTrue(has_recovery, "Expected ACK recovery in delayed ACK scenario")

        retrans_evts = [e for e in events if "retransmitting" in e["summary"].lower()]
        self.assertTrue(len(retrans_evts) > 0)
        self.assertEqual(retrans_evts[0]["fields"]["Seq No"], "1")

    def test_live_flow_control_event_schema(self):
        """Verify Live Flow Control events adhere strictly to schema, sequential steps, and DATA LINK transport."""
        for variant in ["stop-and-wait", "stop-and-wait-arq"]:
            res = self.client.post("/api/live/flow-control", json={"variant": variant, "frame_count": 4})
            self.assertEqual(res.status_code, 200)
            events = res.get_json()["events"]
            expected_keys = {
                "step", "protocol", "transport", "direction",
                "summary", "raw", "fields", "highlight", "timing_ms"
            }
            expected_proto = "STOP-AND-WAIT" if variant == "stop-and-wait" else "SW-ARQ"

            prev_timing = -1.0
            for i, evt in enumerate(events, start=1):
                self.assertTrue(expected_keys.issubset(evt.keys()), f"Event missing required schema keys: {evt}")
                self.assertEqual(evt["step"], i, "Step numbers must be strictly sequential (1, 2, 3, ...)")
                self.assertEqual(evt["protocol"], expected_proto)
                self.assertEqual(evt["transport"], "DATA LINK", "Flow Control transport must be DATA LINK, not TCP/UDP")
                self.assertIn(evt["direction"], ["client-to-server", "server-to-client"])
                self.assertIsInstance(evt["fields"], dict)
                self.assertIsInstance(evt["highlight"], list)
                self.assertIsInstance(evt["timing_ms"], (int, float))
                self.assertGreaterEqual(evt["timing_ms"], prev_timing, "timing_ms must be non-decreasing")
                prev_timing = evt["timing_ms"]

    def test_live_flow_control_invalid_inputs(self):
        """Verify invalid Live Flow Control inputs return 400 with a descriptive JSON error."""
        invalid_payloads = [
            {"variant": "invalid"},
            {},
            {"variant": "stop-and-wait", "frame_count": 1},
            {"variant": "stop-and-wait", "frame_count": 7},
            {"variant": "stop-and-wait-arq", "scenario": "chaos"},
        ]
        for payload in invalid_payloads:
            res = self.client.post("/api/live/flow-control", json=payload)
            self.assertEqual(res.status_code, 400, f"Expected 400 for payload: {payload}")
            self.assertTrue(res.is_json, f"Response should be JSON for payload: {payload}")
            data = res.get_json()
            self.assertIn("error", data, f"Missing 'error' field in response for payload: {payload}")
            self.assertTrue(len(data["error"]) > 0)

    def test_live_flow_control_socket_failure_handling(self):
        """Live socket failures (LiveFlowControlError) must be converted into HTTP 502 with JSON error."""
        with patch("app.live_stop_and_wait", side_effect=LiveFlowControlError("OS socket allocation failed")):
            res = self.client.post("/api/live/flow-control", json={"variant": "stop-and-wait"})
            self.assertEqual(res.status_code, 502)
            self.assertTrue(res.is_json)
            data = res.get_json()
            self.assertIn("error", data)
            self.assertEqual(data["error"], "OS socket allocation failed")

    def test_live_and_simulation_flow_control_separation(self):
        """Verify Live Flow Control returns mode == 'live' while Simulation does not."""
        res_live = self.client.post("/api/live/flow-control", json={"variant": "stop-and-wait"})
        self.assertEqual(res_live.status_code, 200)
        data_live = res_live.get_json()
        self.assertEqual(data_live.get("mode"), "live")
        self.assertEqual(data_live.get("activity"), "flow-control")

        res_sim = self.client.post("/api/simulate/flow-control", json={"variant": "stop-and-wait"})
        self.assertEqual(res_sim.status_code, 200)
        data_sim = res_sim.get_json()
        self.assertEqual(data_sim.get("activity"), "flow-control")
        self.assertNotEqual(data_sim.get("mode"), "live")

    # =========================================================================
    # 7. TRANSPORT LAYER ASSIGNMENT 2 TESTS
    # =========================================================================
    def test_simulation_browsing_transport_stream(self):
        """Browsing Simulation returns 4 application events and 11 discrete TCP transport events."""
        res = self.client.post("/api/simulate/browsing", json={"url": "example.com"})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(len(data["events"]), 4)
        self.assertIn("transport_events", data)
        tb = data["transport_events"]
        self.assertEqual(len(tb), 11)

        # 3-Way Handshake
        self.assertEqual([e["fields"]["Flags"] for e in tb[:3]], ["SYN", "SYN,ACK", "ACK"])
        self.assertEqual([e["application_ref"] for e in tb[:3]], ["connection-establish"] * 3)

        # HTTP GET Request & Server ACK
        self.assertEqual(tb[3]["fields"]["Flags"], "PSH,ACK")
        self.assertEqual(tb[3]["application_ref"], "http-request")
        self.assertEqual(tb[4]["fields"]["Flags"], "ACK")
        self.assertEqual(tb[4]["application_ref"], "http-request")

        # HTTP Response & Client ACK
        self.assertEqual(tb[5]["fields"]["Flags"], "PSH,ACK")
        self.assertEqual(tb[5]["application_ref"], "http-response")
        self.assertEqual(tb[6]["fields"]["Flags"], "ACK")
        self.assertEqual(tb[6]["application_ref"], "http-response")

        # 4-Way Teardown
        self.assertEqual([e["fields"]["Flags"] for e in tb[-4:]], ["FIN,ACK", "ACK", "FIN,ACK", "ACK"])
        self.assertEqual([e["application_ref"] for e in tb[-4:]], ["connection-teardown"] * 4)

        # Conceptually verify DNS remains pure UDP application-layer lookup (not TCP handshake)
        self.assertEqual(data["events"][0]["protocol"], "DNS")
        self.assertEqual(data["events"][0]["transport"], "UDP")
        self.assertNotIn("application_ref", data["events"][0])

    def test_simulation_mail_transport_stream(self):
        """Mail Simulation returns 15 application events and 33 discrete TCP transport events."""
        res = self.client.post(
            "/api/simulate/mail",
            json={"to": "bob@example.com", "subject": "Test", "body": "Message"}
        )
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(len(data["events"]), 15)
        self.assertIn("transport_events", data)
        tm = data["transport_events"]
        self.assertEqual(len(tm), 33)

        # Handshake
        self.assertEqual([e["fields"]["Flags"] for e in tm[:3]], ["SYN", "SYN,ACK", "ACK"])
        self.assertEqual([e["application_ref"] for e in tm[:3]], ["connection-establish"] * 3)

        # All 13 SMTP messages must be represented as TCP PSH,ACK segments + ACKs (26 events)
        smtp_data_events = [e for e in tm[3:-4] if e["fields"]["Flags"] == "PSH,ACK"]
        self.assertEqual(len(smtp_data_events), 13)
        for ev in tm[3:-4]:
            self.assertTrue(ev["application_ref"].startswith("smtp-"))

        # Teardown
        self.assertEqual([e["fields"]["Flags"] for e in tm[-4:]], ["FIN,ACK", "ACK", "FIN,ACK", "ACK"])
        self.assertEqual([e["application_ref"] for e in tm[-4:]], ["connection-teardown"] * 4)

    def test_simulation_streaming_transport_stream(self):
        """Streaming Simulation returns 10 application events and 23 discrete TCP transport events."""
        res = self.client.post("/api/simulate/streaming", json={"quality": "720p"})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(len(data["events"]), 10)
        self.assertIn("transport_events", data)
        ts = data["transport_events"]
        self.assertEqual(len(ts), 23)

        # Handshake
        self.assertEqual([e["fields"]["Flags"] for e in ts[:3]], ["SYN", "SYN,ACK", "ACK"])
        self.assertEqual([e["application_ref"] for e in ts[:3]], ["connection-establish"] * 3)

        # Manifest and 3 Segment request/response exchanges
        self.assertEqual(ts[3]["application_ref"], "manifest-request")
        self.assertEqual(ts[5]["application_ref"], "manifest-response")
        self.assertEqual(ts[7]["application_ref"], "segment-1-request")
        self.assertEqual(ts[9]["application_ref"], "segment-1-response")
        self.assertEqual(ts[11]["application_ref"], "segment-2-request")
        self.assertEqual(ts[13]["application_ref"], "segment-2-response")
        self.assertEqual(ts[15]["application_ref"], "segment-3-request")
        self.assertEqual(ts[17]["application_ref"], "segment-3-response")

        # Teardown
        self.assertEqual([e["fields"]["Flags"] for e in ts[-4:]], ["FIN,ACK", "ACK", "FIN,ACK", "ACK"])
        self.assertEqual([e["application_ref"] for e in ts[-4:]], ["connection-teardown"] * 4)

    def test_tcp_correctness_and_arithmetic(self):
        """Verify RFC 793 sequence numbers, ACK calculations, length, and flag state arithmetic."""
        res_b = self.client.post("/api/simulate/browsing", json={"url": "example.com"})
        res_m = self.client.post("/api/simulate/mail", json={"to": "a@b.com", "subject": "S", "body": "B"})
        res_s = self.client.post("/api/simulate/streaming", json={"quality": "1080p"})

        for stream in [res_b.get_json()["transport_events"], res_m.get_json()["transport_events"], res_s.get_json()["transport_events"]]:
            # SYN: Seq = client ISN, Ack = 0, Length = 0
            syn = stream[0]
            c_isn = syn["fields"]["Seq"]
            self.assertEqual(syn["fields"]["Ack"], 0)
            self.assertEqual(syn["fields"]["Length"], 0)
            self.assertEqual(syn["fields"]["Flags"], "SYN")

            # SYN-ACK: Seq = server ISN, Ack = client ISN + 1, Length = 0
            syn_ack = stream[1]
            s_isn = syn_ack["fields"]["Seq"]
            self.assertEqual(syn_ack["fields"]["Ack"], c_isn + 1)
            self.assertEqual(syn_ack["fields"]["Length"], 0)
            self.assertEqual(syn_ack["fields"]["Flags"], "SYN,ACK")

            # Final Handshake ACK: Seq = client ISN + 1, Ack = server ISN + 1, Length = 0
            f_ack = stream[2]
            self.assertEqual(f_ack["fields"]["Seq"], c_isn + 1)
            self.assertEqual(f_ack["fields"]["Ack"], s_isn + 1)
            self.assertEqual(f_ack["fields"]["Length"], 0)
            self.assertEqual(f_ack["fields"]["Flags"], "ACK")

            # Data segment advances Seq by payload length; Receiver ACK matches sender Seq + length
            pair_count = (len(stream) - 7) // 2
            for i in range(pair_count):
                d_ev = stream[3 + i * 2]
                a_ev = stream[3 + i * 2 + 1]
                self.assertEqual(d_ev["fields"]["Flags"], "PSH,ACK")
                d_len = d_ev["fields"]["Length"]
                self.assertGreater(d_len, 0)
                self.assertEqual(a_ev["fields"]["Flags"], "ACK")
                self.assertEqual(a_ev["fields"]["Length"], 0)
                self.assertEqual(a_ev["fields"]["Ack"], d_ev["fields"]["Seq"] + d_len)

            # Teardown: FIN advances sender Seq by exactly 1
            fin1 = stream[-4]
            ack1 = stream[-3]
            fin2 = stream[-2]
            ack2 = stream[-1]
            self.assertEqual(fin1["fields"]["Flags"], "FIN,ACK")
            self.assertEqual(ack1["fields"]["Flags"], "ACK")
            self.assertEqual(fin2["fields"]["Flags"], "FIN,ACK")
            self.assertEqual(ack2["fields"]["Flags"], "ACK")
            self.assertEqual(ack1["fields"]["Ack"], fin1["fields"]["Seq"] + 1)
            self.assertEqual(ack2["fields"]["Ack"], fin2["fields"]["Seq"] + 1)

    def test_tcp_transport_event_schema(self):
        """Verify every TCP transport event satisfies the visualizer schema, sequential steps, and monotonicity."""
        schema_keys = {
            "step", "layer", "protocol", "transport", "direction",
            "summary", "raw", "fields", "highlight", "timing_ms", "application_ref"
        }
        res_b = self.client.post("/api/simulate/browsing", json={"url": "example.com"})
        res_m = self.client.post("/api/simulate/mail", json={"to": "a@b.com", "subject": "S", "body": "B"})
        res_s = self.client.post("/api/simulate/streaming", json={"quality": "360p"})

        for stream in [res_b.get_json()["transport_events"], res_m.get_json()["transport_events"], res_s.get_json()["transport_events"]]:
            prev_timing = -1
            for idx, ev in enumerate(stream, start=1):
                self.assertTrue(schema_keys.issubset(ev.keys()), f"Missing keys in {ev}")
                self.assertEqual(ev["layer"], "transport")
                self.assertEqual(ev["protocol"], "TCP")
                self.assertEqual(ev["transport"], "TCP")
                self.assertIn(ev["direction"], ("client-to-server", "server-to-client"))
                self.assertEqual(ev["step"], idx)
                self.assertGreaterEqual(ev["timing_ms"], prev_timing)
                prev_timing = ev["timing_ms"]

                f = ev["fields"]
                for fk in ["Seq", "Ack", "Win", "Flags", "Length", "Client State", "Server State", "TCP State"]:
                    self.assertIn(fk, f)
                self.assertIsInstance(f["Seq"], int)
                self.assertIsInstance(f["Ack"], int)
                self.assertIsInstance(f["Win"], int)
                self.assertIsInstance(f["Length"], int)

    def test_view_switching_dom_and_tab_states(self):
        """Verify DOM elements, IDs, and initial tab states for Application vs Transport Layer views."""
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        html = res.get_data(as_text=True)

        self.assertIn('id="protocol-view-tabs"', html)
        self.assertIn('id="protocol-view-application"', html)
        self.assertIn('id="protocol-view-transport"', html)

        # Count view tab buttons
        view_tabs = re.findall(r'class="[^"]*\bprotocol-view-tab\b[^"]*"', html)
        self.assertEqual(len(view_tabs), 2, f"Expected exactly 2 protocol-view-tab buttons, got {len(view_tabs)}")

        # Application tab is active & aria-selected="true"
        app_match = re.search(r'<button[^>]*id="protocol-view-application"[^>]*>', html)
        self.assertIsNotNone(app_match)
        app_tag = app_match.group(0)
        self.assertIn('aria-selected="true"', app_tag)
        self.assertIn('protocol-view-tab--active', app_tag)

        # Transport tab is unselected & aria-selected="false"
        trans_match = re.search(r'<button[^>]*id="protocol-view-transport"[^>]*>', html)
        self.assertIsNotNone(trans_match)
        trans_tag = trans_match.group(0)
        self.assertIn('aria-selected="false"', trans_tag)
        self.assertNotIn('protocol-view-tab--active', trans_tag)

    def test_flow_control_transport_safety(self):
        """Verify Flow Control remains DATA LINK layer and is never classified as TCP."""
        for endpoint in ["/api/simulate/flow-control", "/api/live/flow-control"]:
            res = self.client.post(endpoint, json={"variant": "stop-and-wait"})
            self.assertEqual(res.status_code, 200)
            data = res.get_json()
            # Transport events stream should not be returned or empty
            self.assertTrue("transport_events" not in data or len(data.get("transport_events") or []) == 0)
            for ev in data["events"]:
                self.assertEqual(ev["transport"], "DATA LINK")
                self.assertEqual(ev["protocol"], "STOP-AND-WAIT")


if __name__ == "__main__":
    unittest.main()


