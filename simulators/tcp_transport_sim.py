"""
tcp_transport_sim.py
--------------------
Deterministic, educational TCP Transport Layer event generator.

Models the complete, discrete lifecycle of a TCP connection:
    1. Three-Way Handshake (SYN -> SYN-ACK -> ACK)
    2. Data Transfer (PSH,ACK segments with explicit byte-count sequence tracking & receiver ACKs)
    3. Four-Way Connection Teardown (FIN,ACK -> ACK -> FIN,ACK -> ACK)

Conforms to standard Protocol Visualizer event schema with layer="transport":
    - step (1-based sequential integer)
    - layer ("transport")
    - protocol ("TCP")
    - transport ("TCP")
    - direction ("client-to-server" or "server-to-client")
    - summary (concise educational title)
    - raw (formatted TCP segment representation)
    - fields (Seq, Ack, Win, Flags, Length, Client State, Server State, TCP State)
    - highlight (keys to emphasize in UI)
    - timing_ms (monotonic timestamp offset)

Educational Model Notes:
    - Sequence numbers are deterministic byte-stream offsets (default Client ISN=1000, Server ISN=5000).
    - Window size defaults to 65535 bytes as an educational maximum receive buffer simulation.
    - Application messages are mapped to discrete TCP data segments where Length is the UTF-8 byte count.
    - SYN and FIN control flags consume exactly 1 sequence number; pure ACKs consume 0.
"""

from typing import Any, Dict, List, Optional, Tuple, Union

# Standard TCP Connection Lifecycle States (RFC 793)
TCP_STATE_CLOSED = "CLOSED"
TCP_STATE_LISTEN = "LISTEN"
TCP_STATE_SYN_SENT = "SYN-SENT"
TCP_STATE_SYN_RECEIVED = "SYN-RECEIVED"
TCP_STATE_ESTABLISHED = "ESTABLISHED"
TCP_STATE_FIN_WAIT_1 = "FIN-WAIT-1"
TCP_STATE_FIN_WAIT_2 = "FIN-WAIT-2"
TCP_STATE_CLOSE_WAIT = "CLOSE-WAIT"
TCP_STATE_LAST_ACK = "LAST-ACK"
TCP_STATE_TIME_WAIT = "TIME-WAIT"

# Standard TCP Control Flags
FLAG_SYN = "SYN"
FLAG_SYN_ACK = "SYN,ACK"
FLAG_ACK = "ACK"
FLAG_PSH_ACK = "PSH,ACK"
FLAG_FIN_ACK = "FIN,ACK"
FLAG_RST = "RST"

DEFAULT_CLIENT_ISN = 1000
DEFAULT_SERVER_ISN = 5000
DEFAULT_WINDOW_SIZE = 65535
DEFAULT_STEP_DELAY_MS = 40


def _validate_isn(val: Any, name: str) -> int:
    """Validate initial sequence number."""
    if not isinstance(val, int) or isinstance(val, bool):
        raise ValueError(f"{name} must be an integer (got {type(val).__name__}).")
    if val < 0:
        raise ValueError(f"{name} must be non-negative (got {val}).")
    return val


def _validate_window(val: Any) -> int:
    """Validate TCP receive window size."""
    if not isinstance(val, int) or isinstance(val, bool):
        raise ValueError(f"win must be an integer (got {type(val).__name__}).")
    if val < 0:
        raise ValueError(f"win must be non-negative (got {val}).")
    return val


def _get_payload_bytes(payload: Union[str, bytes]) -> Tuple[bytes, str, int]:
    """Convert payload to bytes, display text, and byte length."""
    if isinstance(payload, bytes):
        raw_bytes = payload
        text = payload.decode("utf-8", errors="replace")
    elif isinstance(payload, str):
        raw_bytes = payload.encode("utf-8")
        text = payload
    else:
        raise ValueError(f"payload must be str or bytes (got {type(payload).__name__}).")
    return raw_bytes, text, len(raw_bytes)


def _format_raw_tcp(
    src: str,
    dst: str,
    seq: int,
    ack: int,
    win: int,
    flags: str,
    length: int,
    payload_text: str = "",
) -> str:
    """Format human-readable wire representation of a TCP segment."""
    lines = [
        "TCP Segment",
        f"Src: {src}",
        f"Dst: {dst}",
        f"Seq: {seq}",
        f"Ack: {ack}",
        f"Win: {win}",
        f"Flags: [{flags}]",
        f"Length: {length}",
    ]
    if payload_text:
        preview = payload_text.strip()
        if len(preview) > 120:
            preview = preview[:117] + "..."
        lines.append(f"Payload: {preview}")
    return "\n".join(lines)


class TCPConnectionState:
    """
    Tracks the active state, sequence numbers, and acknowledgement numbers
    for a single TCP conversation between Client and Server.
    """

    def __init__(
        self,
        client_isn: int = DEFAULT_CLIENT_ISN,
        server_isn: int = DEFAULT_SERVER_ISN,
        default_win: int = DEFAULT_WINDOW_SIZE,
    ):
        self.client_isn = _validate_isn(client_isn, "client_isn")
        self.server_isn = _validate_isn(server_isn, "server_isn")
        self.default_win = _validate_window(default_win)

        self.client_seq = self.client_isn
        self.server_seq = self.server_isn
        self.client_ack = 0
        self.server_ack = 0

        self.client_win = self.default_win
        self.server_win = self.default_win

        self.client_state = TCP_STATE_CLOSED
        self.server_state = TCP_STATE_LISTEN


# -----------------------------------------------------------------------------
# Handshake, Data Exchange, and Teardown Builders
# -----------------------------------------------------------------------------

def build_tcp_handshake(
    state: Optional[TCPConnectionState] = None,
    client_isn: int = DEFAULT_CLIENT_ISN,
    server_isn: int = DEFAULT_SERVER_ISN,
    win: int = DEFAULT_WINDOW_SIZE,
    start_step: int = 1,
    start_time_ms: int = 0,
    step_delay_ms: int = DEFAULT_STEP_DELAY_MS,
) -> Tuple[List[Dict[str, Any]], TCPConnectionState]:
    """
    Generate the 3 discrete events comprising the TCP Three-Way Handshake:
        1. SYN      (Client -> Server)
        2. SYN-ACK  (Server -> Client)
        3. ACK      (Client -> Server)
    """
    if state is None:
        state = TCPConnectionState(client_isn=client_isn, server_isn=server_isn, default_win=win)

    events: List[Dict[str, Any]] = []
    step = start_step
    timing = start_time_ms

    # 1. SYN (Client -> Server)
    state.client_state = TCP_STATE_SYN_SENT
    events.append({
        "step": step,
        "layer": "transport",
        "protocol": "TCP",
        "transport": "TCP",
        "direction": "client-to-server",
        "summary": "TCP Handshake: SYN",
        "raw": _format_raw_tcp(
            src="CLIENT",
            dst="SERVER",
            seq=state.client_seq,
            ack=0,
            win=state.client_win,
            flags=FLAG_SYN,
            length=0,
        ),
        "fields": {
            "Seq": state.client_seq,
            "Ack": 0,
            "Win": state.client_win,
            "Flags": FLAG_SYN,
            "Length": 0,
            "Client State": state.client_state,
            "Server State": state.server_state,
            "TCP State": state.client_state,
            "Description": f"Client initiates 3-way handshake with ISN={state.client_seq}",
        },
        "highlight": ["Seq", "Flags", "Win"],
        "timing_ms": timing,
    })
    step += 1
    timing += step_delay_ms
    # SYN consumes 1 sequence number
    state.client_seq += 1

    # 2. SYN-ACK (Server -> Client)
    state.server_state = TCP_STATE_SYN_RECEIVED
    state.server_ack = state.client_seq  # Acknowledges client SYN
    events.append({
        "step": step,
        "layer": "transport",
        "protocol": "TCP",
        "transport": "TCP",
        "direction": "server-to-client",
        "summary": "TCP Handshake: SYN-ACK",
        "raw": _format_raw_tcp(
            src="SERVER",
            dst="CLIENT",
            seq=state.server_seq,
            ack=state.server_ack,
            win=state.server_win,
            flags=FLAG_SYN_ACK,
            length=0,
        ),
        "fields": {
            "Seq": state.server_seq,
            "Ack": state.server_ack,
            "Win": state.server_win,
            "Flags": FLAG_SYN_ACK,
            "Length": 0,
            "Client State": state.client_state,
            "Server State": state.server_state,
            "TCP State": state.server_state,
            "Description": f"Server acknowledges client SYN and synchronizes with Server ISN={state.server_seq}",
        },
        "highlight": ["Seq", "Ack", "Flags", "Win"],
        "timing_ms": timing,
    })
    step += 1
    timing += step_delay_ms
    # SYN-ACK consumes 1 sequence number
    state.server_seq += 1

    # 3. ACK (Client -> Server)
    state.client_state = TCP_STATE_ESTABLISHED
    state.server_state = TCP_STATE_ESTABLISHED
    state.client_ack = state.server_seq  # Acknowledges server SYN
    events.append({
        "step": step,
        "layer": "transport",
        "protocol": "TCP",
        "transport": "TCP",
        "direction": "client-to-server",
        "summary": "TCP Handshake: ACK (Connection Established)",
        "raw": _format_raw_tcp(
            src="CLIENT",
            dst="SERVER",
            seq=state.client_seq,
            ack=state.client_ack,
            win=state.client_win,
            flags=FLAG_ACK,
            length=0,
        ),
        "fields": {
            "Seq": state.client_seq,
            "Ack": state.client_ack,
            "Win": state.client_win,
            "Flags": FLAG_ACK,
            "Length": 0,
            "Client State": state.client_state,
            "Server State": state.server_state,
            "TCP State": TCP_STATE_ESTABLISHED,
            "Description": "Client acknowledges server SYN-ACK; full-duplex TCP connection established",
        },
        "highlight": ["Seq", "Ack", "Flags"],
        "timing_ms": timing,
    })

    return events, state


def build_tcp_data_exchange(
    state: TCPConnectionState,
    direction: str,
    payload: Union[str, bytes],
    summary_label: str = "",
    start_step: int = 1,
    start_time_ms: int = 0,
    step_delay_ms: int = DEFAULT_STEP_DELAY_MS,
) -> Tuple[List[Dict[str, Any]], TCPConnectionState]:
    """
    Generate a 2-event TCP data exchange:
        1. PSH,ACK segment carrying application payload from sender to receiver
        2. Receiver ACK acknowledging the payload bytes
    """
    if direction not in ("client-to-server", "server-to-client"):
        raise ValueError(f"direction must be 'client-to-server' or 'server-to-client' (got '{direction}').")

    _, payload_text, length = _get_payload_bytes(payload)
    events: List[Dict[str, Any]] = []
    step = start_step
    timing = start_time_ms

    if direction == "client-to-server":
        src_name = "CLIENT"
        dst_name = "SERVER"
        data_seq = state.client_seq
        data_ack = state.server_seq
        data_win = state.client_win
        ack_dir = "server-to-client"
        ack_src = "SERVER"
        ack_dst = "CLIENT"
        ack_win = state.server_win
        ack_desc_target = "server"
    else:
        src_name = "SERVER"
        dst_name = "CLIENT"
        data_seq = state.server_seq
        data_ack = state.client_seq
        data_win = state.server_win
        ack_dir = "client-to-server"
        ack_src = "CLIENT"
        ack_dst = "SERVER"
        ack_win = state.client_win
        ack_desc_target = "client"

    data_summary = f"TCP Segment: PSH,ACK ({summary_label})" if summary_label else "TCP Data Segment (PSH,ACK)"

    # 1. PSH,ACK Data Segment
    events.append({
        "step": step,
        "layer": "transport",
        "protocol": "TCP",
        "transport": "TCP",
        "direction": direction,
        "summary": data_summary,
        "raw": _format_raw_tcp(
            src=src_name,
            dst=dst_name,
            seq=data_seq,
            ack=data_ack,
            win=data_win,
            flags=FLAG_PSH_ACK,
            length=length,
            payload_text=payload_text,
        ),
        "fields": {
            "Seq": data_seq,
            "Ack": data_ack,
            "Win": data_win,
            "Flags": FLAG_PSH_ACK,
            "Length": length,
            "Client State": state.client_state,
            "Server State": state.server_state,
            "TCP State": TCP_STATE_ESTABLISHED,
            "Description": f"{src_name} transmits {length} bytes of application payload",
        },
        "highlight": ["Seq", "Ack", "Flags", "Win", "Length"],
        "timing_ms": timing,
    })
    step += 1
    timing += step_delay_ms

    # Advance sender's sequence number by the byte length of payload
    expected_ack = data_seq + length
    if direction == "client-to-server":
        state.client_seq = expected_ack
        state.server_ack = expected_ack
    else:
        state.server_seq = expected_ack
        state.client_ack = expected_ack

    # 2. Pure ACK from receiver acknowledging payload
    ack_seq = state.server_seq if direction == "client-to-server" else state.client_seq
    ack_summary = f"TCP ACK: Acknowledging {length} bytes" if length > 0 else "TCP ACK"

    events.append({
        "step": step,
        "layer": "transport",
        "protocol": "TCP",
        "transport": "TCP",
        "direction": ack_dir,
        "summary": ack_summary,
        "raw": _format_raw_tcp(
            src=ack_src,
            dst=ack_dst,
            seq=ack_seq,
            ack=expected_ack,
            win=ack_win,
            flags=FLAG_ACK,
            length=0,
        ),
        "fields": {
            "Seq": ack_seq,
            "Ack": expected_ack,
            "Win": ack_win,
            "Flags": FLAG_ACK,
            "Length": 0,
            "Client State": state.client_state,
            "Server State": state.server_state,
            "TCP State": TCP_STATE_ESTABLISHED,
            "Description": f"{ack_desc_target.capitalize()} acknowledges receipt of bytes up to {expected_ack}",
        },
        "highlight": ["Seq", "Ack", "Flags"],
        "timing_ms": timing,
    })

    return events, state


def build_tcp_teardown(
    state: TCPConnectionState,
    start_step: int = 1,
    start_time_ms: int = 0,
    step_delay_ms: int = DEFAULT_STEP_DELAY_MS,
) -> Tuple[List[Dict[str, Any]], TCPConnectionState]:
    """
    Generate the 4 discrete events comprising the standard TCP Four-Way Teardown:
        1. FIN,ACK  (Client -> Server: Initiates close)
        2. ACK      (Server -> Client: Acknowledges client FIN)
        3. FIN,ACK  (Server -> Client: Server closes its direction)
        4. ACK      (Client -> Server: Acknowledges server FIN)
    """
    events: List[Dict[str, Any]] = []
    step = start_step
    timing = start_time_ms

    # 1. Client FIN,ACK (Client -> Server)
    state.client_state = TCP_STATE_FIN_WAIT_1
    state.server_state = TCP_STATE_CLOSE_WAIT
    events.append({
        "step": step,
        "layer": "transport",
        "protocol": "TCP",
        "transport": "TCP",
        "direction": "client-to-server",
        "summary": "TCP Teardown: FIN-ACK (Client Close)",
        "raw": _format_raw_tcp(
            src="CLIENT",
            dst="SERVER",
            seq=state.client_seq,
            ack=state.server_seq,
            win=state.client_win,
            flags=FLAG_FIN_ACK,
            length=0,
        ),
        "fields": {
            "Seq": state.client_seq,
            "Ack": state.server_seq,
            "Win": state.client_win,
            "Flags": FLAG_FIN_ACK,
            "Length": 0,
            "Client State": state.client_state,
            "Server State": state.server_state,
            "TCP State": TCP_STATE_FIN_WAIT_1,
            "Description": "Client initiates connection termination (FIN)",
        },
        "highlight": ["Seq", "Ack", "Flags"],
        "timing_ms": timing,
    })
    step += 1
    timing += step_delay_ms
    # FIN consumes 1 sequence number
    state.client_seq += 1

    # 2. Server ACK (Server -> Client)
    state.client_state = TCP_STATE_FIN_WAIT_2
    state.server_ack = state.client_seq
    events.append({
        "step": step,
        "layer": "transport",
        "protocol": "TCP",
        "transport": "TCP",
        "direction": "server-to-client",
        "summary": "TCP Teardown: ACK",
        "raw": _format_raw_tcp(
            src="SERVER",
            dst="CLIENT",
            seq=state.server_seq,
            ack=state.server_ack,
            win=state.server_win,
            flags=FLAG_ACK,
            length=0,
        ),
        "fields": {
            "Seq": state.server_seq,
            "Ack": state.server_ack,
            "Win": state.server_win,
            "Flags": FLAG_ACK,
            "Length": 0,
            "Client State": state.client_state,
            "Server State": state.server_state,
            "TCP State": TCP_STATE_FIN_WAIT_2,
            "Description": "Server acknowledges client FIN; half-close in effect",
        },
        "highlight": ["Seq", "Ack", "Flags"],
        "timing_ms": timing,
    })
    step += 1
    timing += step_delay_ms

    # 3. Server FIN,ACK (Server -> Client)
    state.server_state = TCP_STATE_LAST_ACK
    state.client_state = TCP_STATE_TIME_WAIT
    events.append({
        "step": step,
        "layer": "transport",
        "protocol": "TCP",
        "transport": "TCP",
        "direction": "server-to-client",
        "summary": "TCP Teardown: Server FIN-ACK",
        "raw": _format_raw_tcp(
            src="SERVER",
            dst="CLIENT",
            seq=state.server_seq,
            ack=state.server_ack,
            win=state.server_win,
            flags=FLAG_FIN_ACK,
            length=0,
        ),
        "fields": {
            "Seq": state.server_seq,
            "Ack": state.server_ack,
            "Win": state.server_win,
            "Flags": FLAG_FIN_ACK,
            "Length": 0,
            "Client State": state.client_state,
            "Server State": state.server_state,
            "TCP State": TCP_STATE_TIME_WAIT,
            "Description": "Server closes its half of the connection (FIN)",
        },
        "highlight": ["Seq", "Ack", "Flags"],
        "timing_ms": timing,
    })
    step += 1
    timing += step_delay_ms
    # Server FIN consumes 1 sequence number
    state.server_seq += 1

    # 4. Client final ACK (Client -> Server)
    state.server_state = TCP_STATE_CLOSED
    state.client_ack = state.server_seq
    events.append({
        "step": step,
        "layer": "transport",
        "protocol": "TCP",
        "transport": "TCP",
        "direction": "client-to-server",
        "summary": "TCP Teardown: Final ACK (Connection Closed)",
        "raw": _format_raw_tcp(
            src="CLIENT",
            dst="SERVER",
            seq=state.client_seq,
            ack=state.client_ack,
            win=state.client_win,
            flags=FLAG_ACK,
            length=0,
        ),
        "fields": {
            "Seq": state.client_seq,
            "Ack": state.client_ack,
            "Win": state.client_win,
            "Flags": FLAG_ACK,
            "Length": 0,
            "Client State": TCP_STATE_CLOSED,
            "Server State": TCP_STATE_CLOSED,
            "TCP State": TCP_STATE_CLOSED,
            "Description": "Client acknowledges server FIN; connection gracefully closed",
        },
        "highlight": ["Seq", "Ack", "Flags"],
        "timing_ms": timing,
    })
    state.client_state = TCP_STATE_CLOSED

    return events, state


# -----------------------------------------------------------------------------
# Activity-Level Transport Generators
# -----------------------------------------------------------------------------

def simulate_browsing_transport(
    request_payload: Union[str, bytes] = "GET / HTTP/1.1\r\nHost: example.com\r\nUser-Agent: SimBrowser/1.0\r\nAccept: text/html\r\n\r\n",
    response_payload: Union[str, bytes] = "HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nContent-Length: 1256\r\n\r\n<!DOCTYPE html><html><body><h1>Example Domain</h1></body></html>",
    client_isn: int = DEFAULT_CLIENT_ISN,
    server_isn: int = DEFAULT_SERVER_ISN,
    win: int = DEFAULT_WINDOW_SIZE,
    start_step: int = 1,
    start_time_ms: int = 0,
    step_delay_ms: int = DEFAULT_STEP_DELAY_MS,
) -> List[Dict[str, Any]]:
    """
    Generate the complete TCP transport sequence for a Browsing (HTTP) exchange:
        - 3-Way Handshake (3 steps)
        - HTTP Request Segment + Server ACK (2 steps)
        - HTTP Response Segment + Client ACK (2 steps)
        - 4-Way Teardown (4 steps)
    Total: 11 deterministic transport events.
    """
    all_events: List[Dict[str, Any]] = []

    # 1. 3-Way Handshake
    hs_events, state = build_tcp_handshake(
        client_isn=client_isn,
        server_isn=server_isn,
        win=win,
        start_step=start_step,
        start_time_ms=start_time_ms,
        step_delay_ms=step_delay_ms,
    )
    all_events.extend(hs_events)

    # 2. HTTP Request Data Segment + ACK
    req_events, state = build_tcp_data_exchange(
        state=state,
        direction="client-to-server",
        payload=request_payload,
        summary_label="HTTP GET Request",
        start_step=len(all_events) + start_step,
        start_time_ms=all_events[-1]["timing_ms"] + step_delay_ms,
        step_delay_ms=step_delay_ms,
    )
    all_events.extend(req_events)

    # 3. HTTP Response Data Segment + ACK
    resp_events, state = build_tcp_data_exchange(
        state=state,
        direction="server-to-client",
        payload=response_payload,
        summary_label="HTTP 200 Response",
        start_step=len(all_events) + start_step,
        start_time_ms=all_events[-1]["timing_ms"] + step_delay_ms,
        step_delay_ms=step_delay_ms,
    )
    all_events.extend(resp_events)

    # 4. 4-Way Teardown
    close_events, _ = build_tcp_teardown(
        state=state,
        start_step=len(all_events) + start_step,
        start_time_ms=all_events[-1]["timing_ms"] + step_delay_ms,
        step_delay_ms=step_delay_ms,
    )
    all_events.extend(close_events)

    return all_events


def simulate_mail_transport(
    messages: Optional[List[Tuple[str, str, str]]] = None,
    client_isn: int = DEFAULT_CLIENT_ISN,
    server_isn: int = DEFAULT_SERVER_ISN,
    win: int = DEFAULT_WINDOW_SIZE,
    start_step: int = 1,
    start_time_ms: int = 0,
    step_delay_ms: int = DEFAULT_STEP_DELAY_MS,
) -> List[Dict[str, Any]]:
    """
    Generate the complete TCP transport sequence for a Mail (SMTP) exchange:
        - 3-Way Handshake
        - Sequence of SMTP commands / responses carried in TCP data segments with ACKs
        - 4-Way Teardown

    `messages` is an optional list of (summary_label, direction, payload) triples.
    If omitted, a standard RFC 5321 submission sequence is simulated.
    """
    if messages is None:
        messages = [
            ("SMTP Greeting", "server-to-client", "220 mail.example.com ESMTP Service Ready\r\n"),
            ("EHLO Command", "client-to-server", "EHLO client.example.com\r\n"),
            ("EHLO Response", "server-to-client", "250-mail.example.com\r\n250-SIZE 35882577\r\n250 OK\r\n"),
            ("MAIL FROM", "client-to-server", "MAIL FROM:<student@example.edu>\r\n"),
            ("MAIL FROM Response", "server-to-client", "250 2.1.0 OK\r\n"),
            ("RCPT TO", "client-to-server", "RCPT TO:<alice@example.com>\r\n"),
            ("RCPT TO Response", "server-to-client", "250 2.1.5 OK\r\n"),
            ("DATA Command", "client-to-server", "DATA\r\n"),
            ("DATA Intermediate", "server-to-client", "354 End data with <CR><LF>.<CR><LF>\r\n"),
            ("Message Body", "client-to-server", "From: student@example.edu\r\nTo: alice@example.com\r\nSubject: Lab 2\r\n\r\nTCP Transport Verified.\r\n.\r\n"),
            ("Message Queued", "server-to-client", "250 2.0.0 OK: queued as 12345\r\n"),
            ("QUIT Command", "client-to-server", "QUIT\r\n"),
            ("Connection Closed", "server-to-client", "221 2.0.0 Bye\r\n"),
        ]

    all_events: List[Dict[str, Any]] = []

    # 1. 3-Way Handshake
    hs_events, state = build_tcp_handshake(
        client_isn=client_isn,
        server_isn=server_isn,
        win=win,
        start_step=start_step,
        start_time_ms=start_time_ms,
        step_delay_ms=step_delay_ms,
    )
    all_events.extend(hs_events)

    # 2. Iterate through SMTP Application payloads
    for label, direction, payload in messages:
        cur_start_step = len(all_events) + start_step
        cur_start_time = all_events[-1]["timing_ms"] + step_delay_ms
        data_events, state = build_tcp_data_exchange(
            state=state,
            direction=direction,
            payload=payload,
            summary_label=label,
            start_step=cur_start_step,
            start_time_ms=cur_start_time,
            step_delay_ms=step_delay_ms,
        )
        all_events.extend(data_events)

    # 3. 4-Way Teardown
    cur_start_step = len(all_events) + start_step
    cur_start_time = all_events[-1]["timing_ms"] + step_delay_ms
    close_events, _ = build_tcp_teardown(
        state=state,
        start_step=cur_start_step,
        start_time_ms=cur_start_time,
        step_delay_ms=step_delay_ms,
    )
    all_events.extend(close_events)

    return all_events


def simulate_streaming_transport(
    segments: Optional[List[Tuple[str, str, str]]] = None,
    quality: str = "720p",
    client_isn: int = DEFAULT_CLIENT_ISN,
    server_isn: int = DEFAULT_SERVER_ISN,
    win: int = DEFAULT_WINDOW_SIZE,
    start_step: int = 1,
    start_time_ms: int = 0,
    step_delay_ms: int = DEFAULT_STEP_DELAY_MS,
) -> List[Dict[str, Any]]:
    """
    Generate the complete TCP transport sequence for a Streaming (HLS) exchange:
        - 3-Way Handshake
        - Manifest Request + Server ACK
        - Manifest Response + Client ACK
        - Segment Requests + Server ACKs & Responses + Client ACKs
        - 4-Way Teardown
    """
    if segments is None:
        manifest_path = f"/video/{quality}/playlist.m3u8"
        manifest_body = f"#EXTM3U\n#EXT-X-VERSION:3\n#EXTINF:6.0,\nsegment001.ts\n#EXTINF:6.0,\nsegment002.ts\n#EXTINF:6.0,\nsegment003.ts"
        segments = [
            ("Manifest Request", "client-to-server", f"GET {manifest_path} HTTP/1.1\r\nHost: video.example.com\r\n\r\n"),
            ("Manifest Response", "server-to-client", f"HTTP/1.1 200 OK\r\nContent-Type: application/vnd.apple.mpegurl\r\n\r\n{manifest_body}"),
            ("Segment 1 Request", "client-to-server", f"GET /video/{quality}/segment001.ts HTTP/1.1\r\nHost: video.example.com\r\n\r\n"),
            ("Segment 1 Response", "server-to-client", f"HTTP/1.1 200 OK\r\nContent-Type: video/mp2t\r\nContent-Length: 524288\r\n\r\n[TS Media Data 512KB]"),
            ("Segment 2 Request", "client-to-server", f"GET /video/{quality}/segment002.ts HTTP/1.1\r\nHost: video.example.com\r\n\r\n"),
            ("Segment 2 Response", "server-to-client", f"HTTP/1.1 200 OK\r\nContent-Type: video/mp2t\r\nContent-Length: 524288\r\n\r\n[TS Media Data 512KB]"),
            ("Segment 3 Request", "client-to-server", f"GET /video/{quality}/segment003.ts HTTP/1.1\r\nHost: video.example.com\r\n\r\n"),
            ("Segment 3 Response", "server-to-client", f"HTTP/1.1 200 OK\r\nContent-Type: video/mp2t\r\nContent-Length: 524288\r\n\r\n[TS Media Data 512KB]"),
        ]

    all_events: List[Dict[str, Any]] = []

    # 1. 3-Way Handshake
    hs_events, state = build_tcp_handshake(
        client_isn=client_isn,
        server_isn=server_isn,
        win=win,
        start_step=start_step,
        start_time_ms=start_time_ms,
        step_delay_ms=step_delay_ms,
    )
    all_events.extend(hs_events)

    # 2. Manifest + Segment Exchanges
    for label, direction, payload in segments:
        cur_start_step = len(all_events) + start_step
        cur_start_time = all_events[-1]["timing_ms"] + step_delay_ms
        data_events, state = build_tcp_data_exchange(
            state=state,
            direction=direction,
            payload=payload,
            summary_label=label,
            start_step=cur_start_step,
            start_time_ms=cur_start_time,
            step_delay_ms=step_delay_ms,
        )
        all_events.extend(data_events)

    # 3. 4-Way Teardown
    cur_start_step = len(all_events) + start_step
    cur_start_time = all_events[-1]["timing_ms"] + step_delay_ms
    close_events, _ = build_tcp_teardown(
        state=state,
        start_step=cur_start_step,
        start_time_ms=cur_start_time,
        step_delay_ms=step_delay_ms,
    )
    all_events.extend(close_events)

    return all_events
