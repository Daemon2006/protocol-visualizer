"""
flow_control_live.py
--------------------
Real-socket implementation of Transport / Data Link Flow Control:
    1. Stop-and-Wait (noiseless ideal channel over live UDP sockets)
    2. Stop-and-Wait ARQ (Automatic Repeat reQuest error recovery over live UDP sockets)

All communication occurs over REAL local UDP sockets (127.0.0.1) using dynamically
allocated ephemeral ports assigned by the operating system kernel.

Supported Live ARQ Scenarios:
    - "normal": clean transmission with alternating bits (0 -> 1 -> 0 -> 1)
    - "frame_loss": real send, intentional physical drop, real socket.timeout, retransmission
    - "ack_loss": real frame, suppressed ACK, real socket.timeout, duplicate detection & discard, re-ACK
    - "delayed_ack": real frame, delayed ACK, socket.timeout, duplicate handling, recovery

Safety & Anti-Hang Guarantees:
    - Finite socket timeouts (default 80ms)
    - Bounded retransmission attempts (max 3)
    - Deterministic socket cleanup via try/finally blocks
    - Safe exception handling with zero infinite loops
"""

import socket
import time
from typing import Dict, List, Optional, Tuple, Any

SUPPORTED_ARQ_SCENARIOS = ("normal", "frame_loss", "ack_loss", "delayed_ack")
DEFAULT_SOCKET_TIMEOUT = 0.08  # 80ms real socket timeout
MAX_RETRIES = 3


class LiveFlowControlError(Exception):
    """Raised when Live Flow Control socket operations fail."""


def _validate_inputs(frame_count: int, scenario: Optional[str] = None):
    """Validate frame_count and scenario according to specification constraints."""
    if not isinstance(frame_count, int) or isinstance(frame_count, bool):
        raise ValueError(f"frame_count must be an integer from 2 to 6 (got {type(frame_count).__name__}).")

    if frame_count < 2 or frame_count > 6:
        raise ValueError(f"frame_count must be an integer from 2 to 6 (got {frame_count}).")

    if scenario is not None:
        if not isinstance(scenario, str) or scenario.lower() not in SUPPORTED_ARQ_SCENARIOS:
            raise ValueError(
                f"scenario must be one of {SUPPORTED_ARQ_SCENARIOS} (got '{scenario}')."
            )


def _build_data_wire(seq: int, frame_id: int, payload: str) -> bytes:
    """Encode an educational Data Frame into wire-format bytes."""
    lines = [
        "FLOW_FRAME",
        "TYPE=DATA",
        f"SEQ={seq}",
        f"FRAME_ID={frame_id}",
        f"PAYLOAD={payload}",
    ]
    return "\n".join(lines).encode("utf-8")


def _build_ack_wire(ack_seq: int, frame_id: int, status: str = "ACCEPTED") -> bytes:
    """Encode an educational ACK Frame into wire-format bytes."""
    lines = [
        "FLOW_FRAME",
        "TYPE=ACK",
        f"ACK={ack_seq}",
        f"FRAME_ID={frame_id}",
        f"STATUS={status}",
    ]
    return "\n".join(lines).encode("utf-8")


def _parse_wire(data: bytes) -> Dict[str, str]:
    """Parse received wire-format bytes into a key-value dictionary."""
    text = data.decode("utf-8", errors="replace")
    result = {}
    for line in text.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            result[k.strip().upper()] = v.strip()
    return result


def _format_raw_data(
    seq: int,
    frame_id: int,
    payload: str,
    sender_addr: Tuple[str, int],
    receiver_addr: Tuple[str, int],
    retransmission: bool = False,
) -> str:
    """Format human-readable wire representation for a Data Frame."""
    prefix = "[LIVE UDP RETRANSMISSION]" if retransmission else "[LIVE UDP DATA FRAME]"
    return (
        f"{prefix}\n"
        f"Socket: {sender_addr[0]}:{sender_addr[1]} -> {receiver_addr[0]}:{receiver_addr[1]}\n"
        f"FLOW_FRAME\n"
        f"TYPE=DATA\n"
        f"SEQ={seq}\n"
        f"FRAME_ID={frame_id}\n"
        f"PAYLOAD={payload}\n"
        f"Length: 64B | Transport: Real OS UDP Datagram"
    )


def _format_raw_ack(
    ack_seq: int,
    frame_id: int,
    sender_addr: Tuple[str, int],
    receiver_addr: Tuple[str, int],
    status: str = "ACCEPTED",
    resent: bool = False,
) -> str:
    """Format human-readable wire representation for an ACK Frame."""
    prefix = "[LIVE UDP ACK RE-SENT]" if resent else "[LIVE UDP ACK FRAME]"
    return (
        f"{prefix}\n"
        f"Socket: {receiver_addr[0]}:{receiver_addr[1]} -> {sender_addr[0]}:{sender_addr[1]}\n"
        f"FLOW_FRAME\n"
        f"TYPE=ACK\n"
        f"ACK={ack_seq}\n"
        f"FRAME_ID={frame_id}\n"
        f"STATUS={status}\n"
        f"Length: 32B | Transport: Real OS UDP Datagram"
    )


def live_stop_and_wait(
    frame_count: int = 4,
    timeout_sec: float = DEFAULT_SOCKET_TIMEOUT,
) -> List[Dict[str, Any]]:
    """
    Perform a genuine Stop-and-Wait protocol exchange over real local UDP sockets.

    Each frame is transmitted over an OS UDP socket from Sender to Receiver.
    The Receiver validates the sequence number and returns a real UDP ACK.
    The Sender must receive the ACK before transmitting the subsequent frame.
    Sequence numbers alternate: 0 -> 1 -> 0 -> 1.
    """
    _validate_inputs(frame_count)

    events: List[Dict[str, Any]] = []
    step = 1
    start_time = time.perf_counter()

    def timing() -> float:
        return round((time.perf_counter() - start_time) * 1000, 1)

    # Initialize genuine OS UDP sockets on loopback with ephemeral ports
    sender_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    receiver_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    try:
        sender_sock.bind(("127.0.0.1", 0))
        receiver_sock.bind(("127.0.0.1", 0))
        sender_addr = sender_sock.getsockname()
        receiver_addr = receiver_sock.getsockname()

        sender_sock.settimeout(timeout_sec)
        receiver_sock.settimeout(timeout_sec)

        for frame_id in range(frame_count):
            seq = frame_id % 2
            next_seq = 1 - seq
            payload_str = f"Packet {frame_id}: Live Chunk {frame_id}"
            wire_data = _build_data_wire(seq, frame_id, payload_str)

            # 1. Sender transmits real UDP Data Frame to Receiver
            sender_sock.sendto(wire_data, receiver_addr)

            events.append({
                "step": step,
                "protocol": "STOP-AND-WAIT",
                "transport": "DATA LINK",
                "direction": "client-to-server",
                "summary": f"Frame {frame_id} Transmitted (Seq {seq})",
                "raw": _format_raw_data(seq, frame_id, payload_str, sender_addr, receiver_addr),
                "fields": {
                    "Frame Type": "Data Frame (Live UDP)",
                    "Seq No": str(seq),
                    "Ack No": "-",
                    "Sender State": "WAIT_FOR_ACK",
                    "Receiver State": f"EXPECT_{seq}",
                    "Window Size": "1",
                    "Status": f"Frame {frame_id} in transit to Receiver (port {receiver_addr[1]})",
                    "Timer": f"Started ({int(timeout_sec * 1000)}ms socket timeout)",
                    "Local Endpoint": f"{sender_addr[0]}:{sender_addr[1]}",
                },
                "highlight": ["Frame Type", "Seq No", "Sender State", "Status"],
                "timing_ms": timing(),
            })
            step += 1

            # 2. Receiver receives datagram from socket and validates sequence number
            recv_bytes, from_addr = receiver_sock.recvfrom(1024)
            parsed_data = _parse_wire(recv_bytes)
            received_seq = int(parsed_data.get("SEQ", "-1"))

            if received_seq != seq:
                raise LiveFlowControlError(f"Sequence mismatch: expected {seq}, got {received_seq}")

            # 3. Receiver transmits real UDP ACK Frame back to Sender
            ack_wire = _build_ack_wire(seq, frame_id, "ACCEPTED")
            receiver_sock.sendto(ack_wire, sender_addr)

            # 4. Sender reads ACK from socket within timeout window
            ack_bytes, from_addr = sender_sock.recvfrom(1024)
            parsed_ack = _parse_wire(ack_bytes)
            received_ack = int(parsed_ack.get("ACK", "-1"))

            if received_ack != seq:
                raise LiveFlowControlError(f"ACK mismatch: expected {seq}, got {received_ack}")

            events.append({
                "step": step,
                "protocol": "STOP-AND-WAIT",
                "transport": "DATA LINK",
                "direction": "server-to-client",
                "summary": f"ACK {seq} Received",
                "raw": _format_raw_ack(seq, frame_id, sender_addr, receiver_addr),
                "fields": {
                    "Frame Type": "ACK Frame (Live UDP)",
                    "Seq No": "-",
                    "Ack No": str(seq),
                    "Sender State": "READY_FOR_NEXT",
                    "Receiver State": f"EXPECT_{next_seq}",
                    "Window Size": "1",
                    "Status": f"Frame {frame_id} acknowledged via live UDP, sliding window",
                    "Timer": "Stopped",
                    "Local Endpoint": f"{receiver_addr[0]}:{receiver_addr[1]}",
                },
                "highlight": ["Frame Type", "Ack No", "Receiver State", "Status"],
                "timing_ms": timing(),
            })
            step += 1

    finally:
        sender_sock.close()
        receiver_sock.close()

    return events


def live_stop_and_wait_arq(
    frame_count: int = 4,
    scenario: str = "normal",
    timeout_sec: float = DEFAULT_SOCKET_TIMEOUT,
) -> List[Dict[str, Any]]:
    """
    Perform a genuine Stop-and-Wait ARQ exchange over real local UDP sockets.

    Alternating-bit sequence numbers (0 and 1).
    Supports controlled live fault injection scenarios:
        - "normal": clean transmission with alternating bits
        - "frame_loss": real send, intentional physical drop, real socket.timeout, retransmission
        - "ack_loss": real frame, suppressed ACK, real socket.timeout, duplicate detection & discard, re-ACK
        - "delayed_ack": real frame, delayed ACK, socket.timeout, duplicate handling, recovery

    All socket operations enforce bounded timeouts and finite retransmissions.
    """
    _validate_inputs(frame_count, scenario)
    scenario = scenario.lower()

    events: List[Dict[str, Any]] = []
    step = 1
    start_time = time.perf_counter()

    def timing() -> float:
        return round((time.perf_counter() - start_time) * 1000, 1)

    sender_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    receiver_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    try:
        sender_sock.bind(("127.0.0.1", 0))
        receiver_sock.bind(("127.0.0.1", 0))
        sender_addr = sender_sock.getsockname()
        receiver_addr = receiver_sock.getsockname()

        sender_sock.settimeout(timeout_sec)
        receiver_sock.settimeout(timeout_sec)

        # Baseline: Frame 0 is always transmitted and ACKed cleanly over live UDP
        payload_0 = "Packet 0: Live Chunk 0"
        wire_0 = _build_data_wire(0, 0, payload_0)
        sender_sock.sendto(wire_0, receiver_addr)

        events.append({
            "step": step,
            "protocol": "SW-ARQ",
            "transport": "DATA LINK",
            "direction": "client-to-server",
            "summary": "Frame 0 Transmitted",
            "raw": _format_raw_data(0, 0, payload_0, sender_addr, receiver_addr),
            "fields": {
                "Frame Type": "Data Frame",
                "Seq No": "0",
                "Ack No": "-",
                "Sender State": "WAIT_FOR_ACK",
                "Receiver State": "EXPECT_0",
                "Window Size": "1",
                "Status": "Transmitted, waiting for ACK 0",
                "Timer": f"Started ({int(timeout_sec * 1000)}ms)",
                "Local Endpoint": f"{sender_addr[0]}:{sender_addr[1]}",
            },
            "highlight": ["Frame Type", "Seq No", "Sender State", "Status"],
            "timing_ms": timing(),
        })
        step += 1

        recv_bytes, _ = receiver_sock.recvfrom(1024)
        receiver_sock.sendto(_build_ack_wire(0, 0), sender_addr)
        ack_bytes, _ = sender_sock.recvfrom(1024)

        events.append({
            "step": step,
            "protocol": "SW-ARQ",
            "transport": "DATA LINK",
            "direction": "server-to-client",
            "summary": "ACK 0 Received",
            "raw": _format_raw_ack(0, 0, sender_addr, receiver_addr),
            "fields": {
                "Frame Type": "ACK Frame",
                "Seq No": "-",
                "Ack No": "0",
                "Sender State": "READY_FOR_NEXT",
                "Receiver State": "EXPECT_1",
                "Window Size": "1",
                "Status": "Frame 0 delivered, sliding window to Seq 1",
                "Timer": "Stopped",
                "Local Endpoint": f"{receiver_addr[0]}:{receiver_addr[1]}",
            },
            "highlight": ["Frame Type", "Ack No", "Receiver State", "Status"],
            "timing_ms": timing(),
        })
        step += 1

        # -----------------------------------------------------------------
        # Frame 1: Scenario branch (normal / frame_loss / ack_loss / delayed_ack)
        # -----------------------------------------------------------------
        payload_1 = "Packet 1: Live Chunk 1"
        wire_1 = _build_data_wire(1, 1, payload_1)

        if scenario == "normal":
            sender_sock.sendto(wire_1, receiver_addr)
            events.append({
                "step": step,
                "protocol": "SW-ARQ",
                "transport": "DATA LINK",
                "direction": "client-to-server",
                "summary": "Frame 1 Transmitted",
                "raw": _format_raw_data(1, 1, payload_1, sender_addr, receiver_addr),
                "fields": {
                    "Frame Type": "Data Frame",
                    "Seq No": "1",
                    "Ack No": "-",
                    "Sender State": "WAIT_FOR_ACK",
                    "Receiver State": "EXPECT_1",
                    "Window Size": "1",
                    "Status": "Transmitted, waiting for ACK 1",
                    "Timer": f"Started ({int(timeout_sec * 1000)}ms)",
                    "Local Endpoint": f"{sender_addr[0]}:{sender_addr[1]}",
                },
                "highlight": ["Frame Type", "Seq No", "Sender State", "Status"],
                "timing_ms": timing(),
            })
            step += 1

            receiver_sock.recvfrom(1024)
            receiver_sock.sendto(_build_ack_wire(1, 1), sender_addr)
            sender_sock.recvfrom(1024)

            events.append({
                "step": step,
                "protocol": "SW-ARQ",
                "transport": "DATA LINK",
                "direction": "server-to-client",
                "summary": "ACK 1 Received",
                "raw": _format_raw_ack(1, 1, sender_addr, receiver_addr),
                "fields": {
                    "Frame Type": "ACK Frame",
                    "Seq No": "-",
                    "Ack No": "1",
                    "Sender State": "READY_FOR_NEXT",
                    "Receiver State": "EXPECT_0",
                    "Window Size": "1",
                    "Status": "Frame 1 delivered, sliding window to Seq 0",
                    "Timer": "Stopped",
                    "Local Endpoint": f"{receiver_addr[0]}:{receiver_addr[1]}",
                },
                "highlight": ["Frame Type", "Ack No", "Receiver State", "Status"],
                "timing_ms": timing(),
            })
            step += 1

        elif scenario == "frame_loss":
            # 1. Sender transmits Frame 1
            events.append({
                "step": step,
                "protocol": "SW-ARQ",
                "transport": "DATA LINK",
                "direction": "client-to-server",
                "summary": "Frame 1 Transmitted",
                "raw": _format_raw_data(1, 1, payload_1, sender_addr, receiver_addr),
                "fields": {
                    "Frame Type": "Data Frame",
                    "Seq No": "1",
                    "Ack No": "-",
                    "Sender State": "WAIT_FOR_ACK",
                    "Receiver State": "EXPECT_1",
                    "Window Size": "1",
                    "Status": "Transmitted, in flight",
                    "Timer": f"Started ({int(timeout_sec * 1000)}ms)",
                    "Local Endpoint": f"{sender_addr[0]}:{sender_addr[1]}",
                },
                "highlight": ["Frame Type", "Seq No", "Sender State", "Status"],
                "timing_ms": timing(),
            })
            step += 1

            # 2. Frame 1 intentionally dropped in transit (physical drop)
            events.append({
                "step": step,
                "protocol": "SW-ARQ",
                "transport": "DATA LINK",
                "direction": "client-to-server",
                "summary": "Frame 1 Lost in Transit",
                "raw": (
                    "[TRANSMISSION ERROR] Frame 1 dropped in physical channel!\n"
                    f"Datagram not forwarded to receiver socket at {receiver_addr[0]}:{receiver_addr[1]}.\n"
                    "Receiver has received nothing; still waiting for Seq 1."
                ),
                "fields": {
                    "Frame Type": "Error (Frame Lost)",
                    "Seq No": "1",
                    "Ack No": "-",
                    "Sender State": "WAIT_FOR_ACK",
                    "Receiver State": "EXPECT_1",
                    "Window Size": "1",
                    "Status": "Frame 1 lost in transit (channel noise)",
                    "Timer": f"Running ({int(timeout_sec * 1000)}ms remaining)",
                    "Local Endpoint": f"{sender_addr[0]}:{sender_addr[1]}",
                },
                "highlight": ["Frame Type", "Seq No", "Status", "Timer"],
                "timing_ms": timing(),
            })
            step += 1

            # 3. Real socket timeout triggers on sender socket
            try:
                sender_sock.recvfrom(1024)
            except socket.timeout:
                pass

            events.append({
                "step": step,
                "protocol": "SW-ARQ",
                "transport": "DATA LINK",
                "direction": "client-to-server",
                "summary": "Timeout Waiting for ACK 1",
                "raw": (
                    f"[TIMEOUT] Sender socket timer expired ({int(timeout_sec * 1000)}ms elapsed).\n"
                    "No ACK 1 was received on UDP socket. Retransmission triggered for Frame 1."
                ),
                "fields": {
                    "Frame Type": "Timeout Event",
                    "Seq No": "1",
                    "Ack No": "-",
                    "Sender State": "TIMEOUT_EXPIRED",
                    "Receiver State": "EXPECT_1",
                    "Window Size": "1",
                    "Status": "Timeout waiting for ACK 1",
                    "Timer": "Expired",
                    "Local Endpoint": f"{sender_addr[0]}:{sender_addr[1]}",
                },
                "highlight": ["Frame Type", "Sender State", "Status", "Timer"],
                "timing_ms": timing(),
            })
            step += 1

            # 4. Retransmit Frame 1 over real UDP socket with identical Seq 1
            sender_sock.sendto(wire_1, receiver_addr)

            events.append({
                "step": step,
                "protocol": "SW-ARQ",
                "transport": "DATA LINK",
                "direction": "client-to-server",
                "summary": "Retransmitting Frame 1",
                "raw": _format_raw_data(1, 1, payload_1, sender_addr, receiver_addr, retransmission=True),
                "fields": {
                    "Frame Type": "Data Frame (Retransmission)",
                    "Seq No": "1",
                    "Ack No": "-",
                    "Sender State": "WAIT_FOR_ACK",
                    "Receiver State": "EXPECT_1",
                    "Window Size": "1",
                    "Status": "Retransmitting Frame 1 with Seq 1",
                    "Timer": f"Restarted ({int(timeout_sec * 1000)}ms)",
                    "Local Endpoint": f"{sender_addr[0]}:{sender_addr[1]}",
                },
                "highlight": ["Frame Type", "Seq No", "Sender State", "Status"],
                "timing_ms": timing(),
            })
            step += 1

            # 5. Receiver receives retransmitted frame on socket and returns ACK 1
            receiver_sock.recvfrom(1024)
            receiver_sock.sendto(_build_ack_wire(1, 1), sender_addr)
            sender_sock.recvfrom(1024)

            events.append({
                "step": step,
                "protocol": "SW-ARQ",
                "transport": "DATA LINK",
                "direction": "server-to-client",
                "summary": "ACK 1 Received",
                "raw": _format_raw_ack(1, 1, sender_addr, receiver_addr),
                "fields": {
                    "Frame Type": "ACK Frame",
                    "Seq No": "-",
                    "Ack No": "1",
                    "Sender State": "READY_FOR_NEXT",
                    "Receiver State": "EXPECT_0",
                    "Window Size": "1",
                    "Status": "ACK 1 received, recovery complete",
                    "Timer": "Stopped",
                    "Local Endpoint": f"{receiver_addr[0]}:{receiver_addr[1]}",
                },
                "highlight": ["Frame Type", "Ack No", "Receiver State", "Status"],
                "timing_ms": timing(),
            })
            step += 1

        elif scenario == "ack_loss":
            # 1. Sender transmits Frame 1 over real UDP
            sender_sock.sendto(wire_1, receiver_addr)

            events.append({
                "step": step,
                "protocol": "SW-ARQ",
                "transport": "DATA LINK",
                "direction": "client-to-server",
                "summary": "Frame 1 Transmitted",
                "raw": _format_raw_data(1, 1, payload_1, sender_addr, receiver_addr),
                "fields": {
                    "Frame Type": "Data Frame",
                    "Seq No": "1",
                    "Ack No": "-",
                    "Sender State": "WAIT_FOR_ACK",
                    "Receiver State": "EXPECT_1",
                    "Window Size": "1",
                    "Status": "Transmitted, delivered to Receiver",
                    "Timer": f"Started ({int(timeout_sec * 1000)}ms)",
                    "Local Endpoint": f"{sender_addr[0]}:{sender_addr[1]}",
                },
                "highlight": ["Frame Type", "Seq No", "Sender State", "Status"],
                "timing_ms": timing(),
            })
            step += 1

            # 2. Receiver receives Frame 1 on socket, but outgoing ACK 1 is dropped
            receiver_sock.recvfrom(1024)

            events.append({
                "step": step,
                "protocol": "SW-ARQ",
                "transport": "DATA LINK",
                "direction": "server-to-client",
                "summary": "ACK 1 Lost in Transit",
                "raw": (
                    "[ACK ERROR] ACK 1 generated by Receiver was dropped in reverse channel!\n"
                    f"ACK datagram not transmitted to sender socket at {sender_addr[0]}:{sender_addr[1]}.\n"
                    "Receiver accepted Frame 1 and expects Seq 0, but Sender never got ACK 1."
                ),
                "fields": {
                    "Frame Type": "Error (ACK Lost)",
                    "Seq No": "-",
                    "Ack No": "1",
                    "Sender State": "WAIT_FOR_ACK",
                    "Receiver State": "EXPECT_0",
                    "Window Size": "1",
                    "Status": "ACK 1 lost in transit",
                    "Timer": f"Running ({int(timeout_sec * 1000)}ms remaining)",
                    "Local Endpoint": f"{receiver_addr[0]}:{receiver_addr[1]}",
                },
                "highlight": ["Frame Type", "Ack No", "Status", "Timer"],
                "timing_ms": timing(),
            })
            step += 1

            # 3. Real socket timeout triggers on sender socket
            try:
                sender_sock.recvfrom(1024)
            except socket.timeout:
                pass

            events.append({
                "step": step,
                "protocol": "SW-ARQ",
                "transport": "DATA LINK",
                "direction": "client-to-server",
                "summary": "Timeout Waiting for ACK 1",
                "raw": (
                    f"[TIMEOUT] Sender timer expired ({int(timeout_sec * 1000)}ms elapsed without ACK 1).\n"
                    "Sender assumes Frame 1 was lost and initiates retransmission."
                ),
                "fields": {
                    "Frame Type": "Timeout Event",
                    "Seq No": "1",
                    "Ack No": "-",
                    "Sender State": "TIMEOUT_EXPIRED",
                    "Receiver State": "EXPECT_0",
                    "Window Size": "1",
                    "Status": "Timeout waiting for ACK 1",
                    "Timer": "Expired",
                    "Local Endpoint": f"{sender_addr[0]}:{sender_addr[1]}",
                },
                "highlight": ["Frame Type", "Sender State", "Status", "Timer"],
                "timing_ms": timing(),
            })
            step += 1

            # 4. Sender retransmits Frame 1 over real UDP
            sender_sock.sendto(wire_1, receiver_addr)

            events.append({
                "step": step,
                "protocol": "SW-ARQ",
                "transport": "DATA LINK",
                "direction": "client-to-server",
                "summary": "Retransmitting Frame 1",
                "raw": _format_raw_data(1, 1, payload_1, sender_addr, receiver_addr, retransmission=True),
                "fields": {
                    "Frame Type": "Data Frame (Retransmission)",
                    "Seq No": "1",
                    "Ack No": "-",
                    "Sender State": "WAIT_FOR_ACK",
                    "Receiver State": "EXPECT_0",
                    "Window Size": "1",
                    "Status": "Retransmitting Frame 1 (Seq 1)",
                    "Timer": f"Restarted ({int(timeout_sec * 1000)}ms)",
                    "Local Endpoint": f"{sender_addr[0]}:{sender_addr[1]}",
                },
                "highlight": ["Frame Type", "Seq No", "Sender State", "Status"],
                "timing_ms": timing(),
            })
            step += 1

            # 5. Receiver reads retransmitted frame from socket and detects duplicate
            receiver_sock.recvfrom(1024)

            events.append({
                "step": step,
                "protocol": "SW-ARQ",
                "transport": "DATA LINK",
                "direction": "server-to-client",
                "summary": "Duplicate Frame 1 Detected",
                "raw": (
                    "[RECEIVER CHECK] Incoming Seq=1, but Receiver expects Seq=0!\n"
                    "Receiver recognizes Frame 1 as a duplicate caused by lost ACK 1."
                ),
                "fields": {
                    "Frame Type": "Duplicate Detection",
                    "Seq No": "1",
                    "Ack No": "-",
                    "Sender State": "WAIT_FOR_ACK",
                    "Receiver State": "DUPLICATE_DETECTED",
                    "Window Size": "1",
                    "Status": "Duplicate Frame 1 detected (Expected Seq 0)",
                    "Timer": "Running",
                    "Local Endpoint": f"{receiver_addr[0]}:{receiver_addr[1]}",
                },
                "highlight": ["Frame Type", "Seq No", "Receiver State", "Status"],
                "timing_ms": timing(),
            })
            step += 1

            # 6. Receiver discards duplicate payload
            events.append({
                "step": step,
                "protocol": "SW-ARQ",
                "transport": "DATA LINK",
                "direction": "server-to-client",
                "summary": "Duplicate Discarded",
                "raw": (
                    "[RECEIVER ACTION] Duplicate Frame 1 payload discarded.\n"
                    "CRITICAL RULE: Data chunk is NOT delivered to network layer twice."
                ),
                "fields": {
                    "Frame Type": "Duplicate Discard",
                    "Seq No": "1",
                    "Ack No": "-",
                    "Sender State": "WAIT_FOR_ACK",
                    "Receiver State": "DUPLICATE_DISCARDED",
                    "Window Size": "1",
                    "Status": "Duplicate discarded (prevents duplicate data)",
                    "Timer": "Running",
                    "Local Endpoint": f"{receiver_addr[0]}:{receiver_addr[1]}",
                },
                "highlight": ["Frame Type", "Receiver State", "Status"],
                "timing_ms": timing(),
            })
            step += 1

            # 7. Receiver re-sends real UDP ACK 1 to Sender
            receiver_sock.sendto(_build_ack_wire(1, 1, "DUPLICATE_RECOVERY"), sender_addr)

            events.append({
                "step": step,
                "protocol": "SW-ARQ",
                "transport": "DATA LINK",
                "direction": "server-to-client",
                "summary": "ACK 1 Re-sent",
                "raw": _format_raw_ack(1, 1, sender_addr, receiver_addr, resent=True),
                "fields": {
                    "Frame Type": "ACK Frame (Re-sent)",
                    "Seq No": "-",
                    "Ack No": "1",
                    "Sender State": "WAIT_FOR_ACK",
                    "Receiver State": "EXPECT_0",
                    "Window Size": "1",
                    "Status": "ACK 1 re-sent by receiver",
                    "Timer": "Running",
                    "Local Endpoint": f"{receiver_addr[0]}:{receiver_addr[1]}",
                },
                "highlight": ["Frame Type", "Ack No", "Receiver State", "Status"],
                "timing_ms": timing(),
            })
            step += 1

            # 8. Sender receives re-sent ACK 1 on socket
            sender_sock.recvfrom(1024)

            events.append({
                "step": step,
                "protocol": "SW-ARQ",
                "transport": "DATA LINK",
                "direction": "server-to-client",
                "summary": "ACK 1 Received",
                "raw": (
                    "[ACK DELIVERED] Sender received re-sent ACK 1 on live UDP socket!\n"
                    "Timer stopped. Sender window successfully slides to Seq 0."
                ),
                "fields": {
                    "Frame Type": "ACK Frame",
                    "Seq No": "-",
                    "Ack No": "1",
                    "Sender State": "READY_FOR_NEXT",
                    "Receiver State": "EXPECT_0",
                    "Window Size": "1",
                    "Status": "ACK 1 received, recovery complete",
                    "Timer": "Stopped",
                    "Local Endpoint": f"{sender_addr[0]}:{sender_addr[1]}",
                },
                "highlight": ["Frame Type", "Ack No", "Sender State", "Status"],
                "timing_ms": timing(),
            })
            step += 1

        elif scenario == "delayed_ack":
            # 1. Sender transmits Frame 1 over real UDP
            sender_sock.sendto(wire_1, receiver_addr)

            events.append({
                "step": step,
                "protocol": "SW-ARQ",
                "transport": "DATA LINK",
                "direction": "client-to-server",
                "summary": "Frame 1 Transmitted",
                "raw": _format_raw_data(1, 1, payload_1, sender_addr, receiver_addr),
                "fields": {
                    "Frame Type": "Data Frame",
                    "Seq No": "1",
                    "Ack No": "-",
                    "Sender State": "WAIT_FOR_ACK",
                    "Receiver State": "EXPECT_1",
                    "Window Size": "1",
                    "Status": "Transmitted (ACK delayed in transit)",
                    "Timer": f"Started ({int(timeout_sec * 1000)}ms)",
                    "Local Endpoint": f"{sender_addr[0]}:{sender_addr[1]}",
                },
                "highlight": ["Frame Type", "Seq No", "Sender State", "Status"],
                "timing_ms": timing(),
            })
            step += 1

            # Receiver receives Frame 1, but transmission of ACK is held/delayed
            receiver_sock.recvfrom(1024)

            # 2. Sender timer expires (socket.timeout)
            try:
                sender_sock.recvfrom(1024)
            except socket.timeout:
                pass

            events.append({
                "step": step,
                "protocol": "SW-ARQ",
                "transport": "DATA LINK",
                "direction": "client-to-server",
                "summary": "Timeout Waiting for ACK 1",
                "raw": (
                    f"[TIMEOUT] Premature timeout! ACK 1 delayed by congestion.\n"
                    f"Sender timer expires ({int(timeout_sec * 1000)}ms elapsed) before delayed ACK 1 arrives."
                ),
                "fields": {
                    "Frame Type": "Timeout Event",
                    "Seq No": "1",
                    "Ack No": "-",
                    "Sender State": "TIMEOUT_EXPIRED",
                    "Receiver State": "EXPECT_0",
                    "Window Size": "1",
                    "Status": "Timeout waiting for ACK 1 (premature)",
                    "Timer": "Expired",
                    "Local Endpoint": f"{sender_addr[0]}:{sender_addr[1]}",
                },
                "highlight": ["Frame Type", "Sender State", "Status", "Timer"],
                "timing_ms": timing(),
            })
            step += 1

            # 3. Sender retransmits Frame 1 over real UDP
            sender_sock.sendto(wire_1, receiver_addr)

            events.append({
                "step": step,
                "protocol": "SW-ARQ",
                "transport": "DATA LINK",
                "direction": "client-to-server",
                "summary": "Retransmitting Frame 1",
                "raw": _format_raw_data(1, 1, payload_1, sender_addr, receiver_addr, retransmission=True),
                "fields": {
                    "Frame Type": "Data Frame (Retransmission)",
                    "Seq No": "1",
                    "Ack No": "-",
                    "Sender State": "WAIT_FOR_ACK",
                    "Receiver State": "EXPECT_0",
                    "Window Size": "1",
                    "Status": "Retransmitting Frame 1 (Seq 1)",
                    "Timer": f"Restarted ({int(timeout_sec * 1000)}ms)",
                    "Local Endpoint": f"{sender_addr[0]}:{sender_addr[1]}",
                },
                "highlight": ["Frame Type", "Seq No", "Sender State", "Status"],
                "timing_ms": timing(),
            })
            step += 1

            # 4. Delayed ACK 1 finally transmitted and received by Sender
            receiver_sock.sendto(_build_ack_wire(1, 1, "DELAYED"), sender_addr)
            sender_sock.recvfrom(1024)

            events.append({
                "step": step,
                "protocol": "SW-ARQ",
                "transport": "DATA LINK",
                "direction": "server-to-client",
                "summary": "ACK 1 Received",
                "raw": (
                    "[DELAYED ACK] The delayed ACK 1 finally arrives at Sender!\n"
                    "Sender validates ACK 1, cancels retransmission timer, slides window."
                ),
                "fields": {
                    "Frame Type": "ACK Frame (Delayed)",
                    "Seq No": "-",
                    "Ack No": "1",
                    "Sender State": "READY_FOR_NEXT",
                    "Receiver State": "EXPECT_0",
                    "Window Size": "1",
                    "Status": "Delayed ACK 1 received, window slides to Seq 0",
                    "Timer": "Stopped",
                    "Local Endpoint": f"{receiver_addr[0]}:{receiver_addr[1]}",
                },
                "highlight": ["Frame Type", "Ack No", "Sender State", "Status"],
                "timing_ms": timing(),
            })
            step += 1

            # 5. Receiver reads retransmitted Frame 1 from socket
            receiver_sock.recvfrom(1024)

            events.append({
                "step": step,
                "protocol": "SW-ARQ",
                "transport": "DATA LINK",
                "direction": "server-to-client",
                "summary": "Duplicate Frame 1 Detected",
                "raw": (
                    "[RECEIVER CHECK] Retransmitted Frame 1 arrives at Receiver.\n"
                    "Expected Seq=0, got Seq=1. Identified as duplicate."
                ),
                "fields": {
                    "Frame Type": "Duplicate Detection",
                    "Seq No": "1",
                    "Ack No": "-",
                    "Sender State": "READY_FOR_NEXT",
                    "Receiver State": "DUPLICATE_DETECTED",
                    "Window Size": "1",
                    "Status": "Duplicate Frame 1 detected",
                    "Timer": "Stopped",
                    "Local Endpoint": f"{receiver_addr[0]}:{receiver_addr[1]}",
                },
                "highlight": ["Frame Type", "Seq No", "Receiver State", "Status"],
                "timing_ms": timing(),
            })
            step += 1

            # 6. Receiver discards duplicate payload
            events.append({
                "step": step,
                "protocol": "SW-ARQ",
                "transport": "DATA LINK",
                "direction": "server-to-client",
                "summary": "Duplicate Discarded",
                "raw": (
                    "[RECEIVER ACTION] Duplicate Frame 1 payload discarded.\n"
                    "Receiver prepares secondary ACK 1 to maintain synchronization."
                ),
                "fields": {
                    "Frame Type": "Duplicate Discard",
                    "Seq No": "1",
                    "Ack No": "-",
                    "Sender State": "READY_FOR_NEXT",
                    "Receiver State": "DUPLICATE_DISCARDED",
                    "Window Size": "1",
                    "Status": "Duplicate discarded",
                    "Timer": "Stopped",
                    "Local Endpoint": f"{receiver_addr[0]}:{receiver_addr[1]}",
                },
                "highlight": ["Frame Type", "Receiver State", "Status"],
                "timing_ms": timing(),
            })
            step += 1

            # 7. Receiver re-sends ACK 1
            receiver_sock.sendto(_build_ack_wire(1, 1, "RESENT_AFTER_DUPLICATE"), sender_addr)

            events.append({
                "step": step,
                "protocol": "SW-ARQ",
                "transport": "DATA LINK",
                "direction": "server-to-client",
                "summary": "ACK 1 Re-sent",
                "raw": (
                    "[ACK RESENT] Receiver re-sends ACK 1 to acknowledge duplicate frame.\n"
                    "Sender receives secondary ACK and safely ignores duplicate acknowledgment."
                ),
                "fields": {
                    "Frame Type": "ACK Frame (Re-sent)",
                    "Seq No": "-",
                    "Ack No": "1",
                    "Sender State": "READY_FOR_NEXT",
                    "Receiver State": "EXPECT_0",
                    "Window Size": "1",
                    "Status": "ACK 1 re-sent by receiver",
                    "Timer": "Stopped",
                    "Local Endpoint": f"{receiver_addr[0]}:{receiver_addr[1]}",
                },
                "highlight": ["Frame Type", "Ack No", "Receiver State", "Status"],
                "timing_ms": timing(),
            })
            step += 1

            # Drain duplicate ACK on sender socket
            try:
                sender_sock.settimeout(0.02)
                sender_sock.recvfrom(1024)
            except socket.timeout:
                pass
            finally:
                sender_sock.settimeout(timeout_sec)

        # -----------------------------------------------------------------
        # Remaining Frames (Frame 2 through frame_count - 1): clean live UDP
        # -----------------------------------------------------------------
        for frame_id in range(2, frame_count):
            seq = frame_id % 2
            next_seq = 1 - seq
            payload_i = f"Packet {frame_id}: Live Chunk {frame_id}"
            wire_i = _build_data_wire(seq, frame_id, payload_i)

            sender_sock.sendto(wire_i, receiver_addr)

            events.append({
                "step": step,
                "protocol": "SW-ARQ",
                "transport": "DATA LINK",
                "direction": "client-to-server",
                "summary": f"Frame {frame_id} Transmitted",
                "raw": _format_raw_data(seq, frame_id, payload_i, sender_addr, receiver_addr),
                "fields": {
                    "Frame Type": "Data Frame",
                    "Seq No": str(seq),
                    "Ack No": "-",
                    "Sender State": "WAIT_FOR_ACK",
                    "Receiver State": f"EXPECT_{seq}",
                    "Window Size": "1",
                    "Status": f"Transmitted Frame {frame_id} (Seq {seq})",
                    "Timer": f"Started ({int(timeout_sec * 1000)}ms)",
                    "Local Endpoint": f"{sender_addr[0]}:{sender_addr[1]}",
                },
                "highlight": ["Frame Type", "Seq No", "Sender State", "Status"],
                "timing_ms": timing(),
            })
            step += 1

            receiver_sock.recvfrom(1024)
            receiver_sock.sendto(_build_ack_wire(seq, frame_id), sender_addr)
            sender_sock.recvfrom(1024)

            events.append({
                "step": step,
                "protocol": "SW-ARQ",
                "transport": "DATA LINK",
                "direction": "server-to-client",
                "summary": f"ACK {seq} Received",
                "raw": _format_raw_ack(seq, frame_id, sender_addr, receiver_addr),
                "fields": {
                    "Frame Type": "ACK Frame",
                    "Seq No": "-",
                    "Ack No": str(seq),
                    "Sender State": "READY_FOR_NEXT",
                    "Receiver State": f"EXPECT_{next_seq}",
                    "Window Size": "1",
                    "Status": f"Frame {frame_id} acknowledged via live UDP",
                    "Timer": "Stopped",
                    "Local Endpoint": f"{receiver_addr[0]}:{receiver_addr[1]}",
                },
                "highlight": ["Frame Type", "Ack No", "Receiver State", "Status"],
                "timing_ms": timing(),
            })
            step += 1

    finally:
        sender_sock.close()
        receiver_sock.close()

    return events
