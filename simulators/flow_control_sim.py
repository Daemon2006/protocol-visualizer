"""
flow_control_sim.py
-------------------
Deterministic protocol simulator for Transport / Data Link Flow Control:
    1. Stop-and-Wait (noiseless ideal channel)
    2. Stop-and-Wait ARQ (Automatic Repeat reQuest with error recovery)

Supported ARQ Scenarios:
    - "normal": clean transmission with alternating bits (0 -> 1 -> 0 -> 1)
    - "frame_loss": frame dropped in transit, timeout expiration, retransmission
    - "ack_loss": acknowledgment dropped, timeout, duplicate detection, discard, re-ACK
    - "delayed_ack": late ACK arrival, premature timeout, retransmission, duplicate handling

All events conform to the standard Protocol Visualizer event schema:
    - step (1-based integer)
    - protocol ("STOP-AND-WAIT" or "SW-ARQ")
    - transport ("DATA LINK")
    - direction ("client-to-server" or "server-to-client")
    - summary (concise human-readable title)
    - raw (formatted frame wire representation)
    - fields (key-value metadata dictionary)
    - highlight (keys to emphasize in UI)
    - timing_ms (relative timeline offset in milliseconds)
"""

SUPPORTED_SCENARIOS = ("normal", "frame_loss", "ack_loss", "delayed_ack")


def _validate_inputs(frame_count: int, scenario: str = None):
    """Validate frame_count and scenario according to specification constraints."""
    if not isinstance(frame_count, int) or isinstance(frame_count, bool):
        raise ValueError(f"frame_count must be an integer from 2 to 6 (got {type(frame_count).__name__}).")

    if frame_count < 2 or frame_count > 6:
        raise ValueError(f"frame_count must be an integer from 2 to 6 (got {frame_count}).")

    if scenario is not None:
        if not isinstance(scenario, str) or scenario.lower() not in SUPPORTED_SCENARIOS:
            raise ValueError(
                f"scenario must be one of {SUPPORTED_SCENARIOS} (got '{scenario}')."
            )


def simulate_stop_and_wait(frame_count: int = 4):
    """
    Simulate the standard Stop-and-Wait flow control protocol on a noiseless channel.

    Alternates 1-bit sequence numbers: 0 -> 1 -> 0 -> 1.
    Each frame must be acknowledged by the receiver before the sender is permitted
    to transmit the subsequent frame.
    """
    _validate_inputs(frame_count)

    events = []
    t = 0
    step = 1

    for i in range(frame_count):
        seq = i % 2
        next_seq = 1 - seq
        crc_val = f"0x{(0x1A00 + i * 0x37):04X}"

        # 1. Sender transmits Frame i (Seq seq)
        events.append({
            "step": step,
            "protocol": "STOP-AND-WAIT",
            "transport": "DATA LINK",
            "direction": "client-to-server",
            "summary": f"Frame {i} Transmitted (Seq {seq})",
            "raw": (
                f"[DATA FRAME] Frame={i} | Seq={seq} | Length=64B\n"
                f"Payload: 'Packet {i}: Data Chunk {i}' | CRC={crc_val}\n"
                f"Sender Window: [Frame {i}] (Size=1)"
            ),
            "fields": {
                "Frame Type": "Data Frame",
                "Seq No": str(seq),
                "Ack No": "-",
                "Sender State": "WAIT_FOR_ACK",
                "Receiver State": f"EXPECT_{seq}",
                "Window Size": "1",
                "Status": f"Frame {i} in transit to Receiver",
                "Timer": "Started (150ms)",
            },
            "highlight": ["Frame Type", "Seq No", "Sender State", "Status"],
            "timing_ms": t,
        })
        step += 1
        t += 50

        # 2. Receiver transmits ACK seq
        events.append({
            "step": step,
            "protocol": "STOP-AND-WAIT",
            "transport": "DATA LINK",
            "direction": "server-to-client",
            "summary": f"ACK {seq} Received",
            "raw": (
                f"[ACK FRAME] Ack={seq} | Next Expected Seq={next_seq}\n"
                f"Status: Frame {i} accepted without error\n"
                f"Receiver Window: [Ready for Seq {next_seq}]"
            ),
            "fields": {
                "Frame Type": "ACK Frame",
                "Seq No": "-",
                "Ack No": str(seq),
                "Sender State": "READY_FOR_NEXT",
                "Receiver State": f"EXPECT_{next_seq}",
                "Window Size": "1",
                "Status": f"Frame {i} acknowledged, sliding window",
                "Timer": "Stopped",
            },
            "highlight": ["Frame Type", "Ack No", "Receiver State", "Status"],
            "timing_ms": t,
        })
        step += 1
        t += 50

    return events


def simulate_stop_and_wait_arq(frame_count: int = 4, scenario: str = "normal"):
    """
    Simulate Stop-and-Wait ARQ (Automatic Repeat reQuest) flow control.

    Uses alternating-bit sequence numbers (0 and 1).
    Supports:
        - "normal": clean transmission with alternating bits
        - "frame_loss": frame dropped in transit, timeout, retransmission, recovery
        - "ack_loss": ACK dropped, timeout, duplicate frame detected & discarded, re-ACK
        - "delayed_ack": late ACK arrival, timeout, duplicate handling, recovery

    Rules enforced:
        1. Sequence number changes only after a successful ACK.
        2. Retransmissions keep the exact same sequence number.
        3. Frame loss causes timeout and retransmission.
        4. ACK loss causes timeout and retransmission.
        5. Receiver detects duplicate frames by inspecting expected sequence bit.
        6. Duplicate data payload is discarded (not delivered to upper layer twice).
        7. Receiver re-sends the appropriate ACK after duplicate detection.
        8. Transmission eventually recovers successfully.
    """
    _validate_inputs(frame_count, scenario)
    scenario = scenario.lower()

    events = []
    t = 0
    step = 1

    # Frame 0 is always transmitted cleanly to establish baseline protocol operation
    events.append({
        "step": step,
        "protocol": "SW-ARQ",
        "transport": "DATA LINK",
        "direction": "client-to-server",
        "summary": "Frame 0 Transmitted",
        "raw": (
            "[DATA FRAME] Frame=0 | Seq=0 | Length=64B\n"
            "Payload: 'Packet 0: Data Chunk 0' | CRC=0x1A00\n"
            "Sender Window: [Frame 0] (Size=1)"
        ),
        "fields": {
            "Frame Type": "Data Frame",
            "Seq No": "0",
            "Ack No": "-",
            "Sender State": "WAIT_FOR_ACK",
            "Receiver State": "EXPECT_0",
            "Window Size": "1",
            "Status": "Transmitted, waiting for ACK 0",
            "Timer": "Started (150ms)",
        },
        "highlight": ["Frame Type", "Seq No", "Sender State", "Status"],
        "timing_ms": t,
    })
    step += 1
    t += 50

    events.append({
        "step": step,
        "protocol": "SW-ARQ",
        "transport": "DATA LINK",
        "direction": "server-to-client",
        "summary": "ACK 0 Received",
        "raw": (
            "[ACK FRAME] Ack=0 | Next Expected Seq=1\n"
            "Status: Frame 0 delivered to network layer\n"
            "Receiver Window: [Ready for Seq 1]"
        ),
        "fields": {
            "Frame Type": "ACK Frame",
            "Seq No": "-",
            "Ack No": "0",
            "Sender State": "READY_FOR_NEXT",
            "Receiver State": "EXPECT_1",
            "Window Size": "1",
            "Status": "Frame 0 delivered, sliding window to Seq 1",
            "Timer": "Stopped",
        },
        "highlight": ["Frame Type", "Ack No", "Receiver State", "Status"],
        "timing_ms": t,
    })
    step += 1
    t += 50

    # -----------------------------------------------------------------
    # Frame 1: Scenario branch (normal / frame_loss / ack_loss / delayed_ack)
    # -----------------------------------------------------------------
    if scenario == "normal":
        events.append({
            "step": step,
            "protocol": "SW-ARQ",
            "transport": "DATA LINK",
            "direction": "client-to-server",
            "summary": "Frame 1 Transmitted",
            "raw": (
                "[DATA FRAME] Frame=1 | Seq=1 | Length=64B\n"
                "Payload: 'Packet 1: Data Chunk 1' | CRC=0x1A37\n"
                "Sender Window: [Frame 1] (Size=1)"
            ),
            "fields": {
                "Frame Type": "Data Frame",
                "Seq No": "1",
                "Ack No": "-",
                "Sender State": "WAIT_FOR_ACK",
                "Receiver State": "EXPECT_1",
                "Window Size": "1",
                "Status": "Transmitted, waiting for ACK 1",
                "Timer": "Started (150ms)",
            },
            "highlight": ["Frame Type", "Seq No", "Sender State", "Status"],
            "timing_ms": t,
        })
        step += 1
        t += 50

        events.append({
            "step": step,
            "protocol": "SW-ARQ",
            "transport": "DATA LINK",
            "direction": "server-to-client",
            "summary": "ACK 1 Received",
            "raw": (
                "[ACK FRAME] Ack=1 | Next Expected Seq=0\n"
                "Status: Frame 1 delivered to network layer\n"
                "Receiver Window: [Ready for Seq 0]"
            ),
            "fields": {
                "Frame Type": "ACK Frame",
                "Seq No": "-",
                "Ack No": "1",
                "Sender State": "READY_FOR_NEXT",
                "Receiver State": "EXPECT_0",
                "Window Size": "1",
                "Status": "Frame 1 delivered, sliding window to Seq 0",
                "Timer": "Stopped",
            },
            "highlight": ["Frame Type", "Ack No", "Receiver State", "Status"],
            "timing_ms": t,
        })
        step += 1
        t += 50

    elif scenario == "frame_loss":
        # 1. Sender transmits Frame 1
        events.append({
            "step": step,
            "protocol": "SW-ARQ",
            "transport": "DATA LINK",
            "direction": "client-to-server",
            "summary": "Frame 1 Transmitted",
            "raw": (
                "[DATA FRAME] Frame=1 | Seq=1 | Length=64B\n"
                "Payload: 'Packet 1: Data Chunk 1' | CRC=0x1A37\n"
                "Sender Window: [Frame 1] (Size=1)"
            ),
            "fields": {
                "Frame Type": "Data Frame",
                "Seq No": "1",
                "Ack No": "-",
                "Sender State": "WAIT_FOR_ACK",
                "Receiver State": "EXPECT_1",
                "Window Size": "1",
                "Status": "Transmitted, in flight",
                "Timer": "Started (150ms)",
            },
            "highlight": ["Frame Type", "Seq No", "Sender State", "Status"],
            "timing_ms": t,
        })
        step += 1
        t += 30

        # 2. Frame 1 Lost in Transit
        events.append({
            "step": step,
            "protocol": "SW-ARQ",
            "transport": "DATA LINK",
            "direction": "client-to-server",
            "summary": "Frame 1 Lost in Transit",
            "raw": (
                "[TRANSMISSION ERROR] Frame 1 dropped in physical channel!\n"
                "Cause: Noise burst / CRC checksum corruption.\n"
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
                "Timer": "Running (120ms remaining)",
            },
            "highlight": ["Frame Type", "Seq No", "Status", "Timer"],
            "timing_ms": t,
        })
        step += 1
        t += 120

        # 3. Timeout Waiting for ACK 1
        events.append({
            "step": step,
            "protocol": "SW-ARQ",
            "transport": "DATA LINK",
            "direction": "client-to-server",
            "summary": "Timeout Waiting for ACK 1",
            "raw": (
                "[TIMEOUT] Sender ACK timer expired (150ms elapsed).\n"
                "No ACK 1 was received. Retransmission triggered for Frame 1."
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
            },
            "highlight": ["Frame Type", "Sender State", "Status", "Timer"],
            "timing_ms": t,
        })
        step += 1
        t += 30

        # 4. Retransmitting Frame 1
        events.append({
            "step": step,
            "protocol": "SW-ARQ",
            "transport": "DATA LINK",
            "direction": "client-to-server",
            "summary": "Retransmitting Frame 1",
            "raw": (
                "[RETRANSMISSION] Frame=1 | Seq=1 | Length=64B\n"
                "Payload: 'Packet 1: Data Chunk 1' | CRC=0x1A37\n"
                "Sequence number MUST remain unchanged (Seq 1)."
            ),
            "fields": {
                "Frame Type": "Data Frame (Retransmission)",
                "Seq No": "1",
                "Ack No": "-",
                "Sender State": "WAIT_FOR_ACK",
                "Receiver State": "EXPECT_1",
                "Window Size": "1",
                "Status": "Retransmitting Frame 1 with Seq 1",
                "Timer": "Restarted (150ms)",
            },
            "highlight": ["Frame Type", "Seq No", "Sender State", "Status"],
            "timing_ms": t,
        })
        step += 1
        t += 50

        # 5. Receiver accepts Frame 1 and emits ACK 1
        events.append({
            "step": step,
            "protocol": "SW-ARQ",
            "transport": "DATA LINK",
            "direction": "server-to-client",
            "summary": "ACK 1 Received",
            "raw": (
                "[ACK FRAME] Ack=1 | Next Expected Seq=0\n"
                "Receiver received Frame 1, verified CRC, delivered to network layer.\n"
                "ACK 1 delivered to Sender; recovery complete."
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
            },
            "highlight": ["Frame Type", "Ack No", "Receiver State", "Status"],
            "timing_ms": t,
        })
        step += 1
        t += 50

    elif scenario == "ack_loss":
        # 1. Sender transmits Frame 1
        events.append({
            "step": step,
            "protocol": "SW-ARQ",
            "transport": "DATA LINK",
            "direction": "client-to-server",
            "summary": "Frame 1 Transmitted",
            "raw": (
                "[DATA FRAME] Frame=1 | Seq=1 | Length=64B\n"
                "Payload: 'Packet 1: Data Chunk 1' | CRC=0x1A37\n"
                "Sender Window: [Frame 1] (Size=1)"
            ),
            "fields": {
                "Frame Type": "Data Frame",
                "Seq No": "1",
                "Ack No": "-",
                "Sender State": "WAIT_FOR_ACK",
                "Receiver State": "EXPECT_1",
                "Window Size": "1",
                "Status": "Transmitted, delivered to Receiver",
                "Timer": "Started (150ms)",
            },
            "highlight": ["Frame Type", "Seq No", "Sender State", "Status"],
            "timing_ms": t,
        })
        step += 1
        t += 40

        # 2. Receiver emits ACK 1, but it is lost in transit
        events.append({
            "step": step,
            "protocol": "SW-ARQ",
            "transport": "DATA LINK",
            "direction": "server-to-client",
            "summary": "ACK 1 Lost in Transit",
            "raw": (
                "[ACK ERROR] ACK 1 generated by Receiver was dropped in reverse channel!\n"
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
                "Timer": "Running (110ms remaining)",
            },
            "highlight": ["Frame Type", "Ack No", "Status", "Timer"],
            "timing_ms": t,
        })
        step += 1
        t += 110

        # 3. Timeout Waiting for ACK 1
        events.append({
            "step": step,
            "protocol": "SW-ARQ",
            "transport": "DATA LINK",
            "direction": "client-to-server",
            "summary": "Timeout Waiting for ACK 1",
            "raw": (
                "[TIMEOUT] Sender timer expired (150ms elapsed without ACK 1).\n"
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
            },
            "highlight": ["Frame Type", "Sender State", "Status", "Timer"],
            "timing_ms": t,
        })
        step += 1
        t += 30

        # 4. Retransmitting Frame 1
        events.append({
            "step": step,
            "protocol": "SW-ARQ",
            "transport": "DATA LINK",
            "direction": "client-to-server",
            "summary": "Retransmitting Frame 1",
            "raw": (
                "[RETRANSMISSION] Frame=1 | Seq=1 | Length=64B\n"
                "Sender resends unacknowledged Frame 1 with same Seq No = 1."
            ),
            "fields": {
                "Frame Type": "Data Frame (Retransmission)",
                "Seq No": "1",
                "Ack No": "-",
                "Sender State": "WAIT_FOR_ACK",
                "Receiver State": "EXPECT_0",
                "Window Size": "1",
                "Status": "Retransmitting Frame 1 (Seq 1)",
                "Timer": "Restarted (150ms)",
            },
            "highlight": ["Frame Type", "Seq No", "Sender State", "Status"],
            "timing_ms": t,
        })
        step += 1
        t += 35

        # 5. Duplicate Frame 1 Detected
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
            },
            "highlight": ["Frame Type", "Seq No", "Receiver State", "Status"],
            "timing_ms": t,
        })
        step += 1
        t += 20

        # 6. Duplicate Discarded
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
            },
            "highlight": ["Frame Type", "Receiver State", "Status"],
            "timing_ms": t,
        })
        step += 1
        t += 25

        # 7. ACK 1 Re-sent
        events.append({
            "step": step,
            "protocol": "SW-ARQ",
            "transport": "DATA LINK",
            "direction": "server-to-client",
            "summary": "ACK 1 Re-sent",
            "raw": (
                "[ACK RE-SEND] Ack=1 | Next Expected Seq=0\n"
                "Receiver re-sends ACK 1 so sender can recover and advance window."
            ),
            "fields": {
                "Frame Type": "ACK Frame (Re-sent)",
                "Seq No": "-",
                "Ack No": "1",
                "Sender State": "WAIT_FOR_ACK",
                "Receiver State": "EXPECT_0",
                "Window Size": "1",
                "Status": "ACK 1 re-sent by receiver",
                "Timer": "Running",
            },
            "highlight": ["Frame Type", "Ack No", "Receiver State", "Status"],
            "timing_ms": t,
        })
        step += 1
        t += 40

        # 8. ACK 1 Received
        events.append({
            "step": step,
            "protocol": "SW-ARQ",
            "transport": "DATA LINK",
            "direction": "server-to-client",
            "summary": "ACK 1 Received",
            "raw": (
                "[ACK DELIVERED] Sender received re-sent ACK 1!\n"
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
            },
            "highlight": ["Frame Type", "Ack No", "Sender State", "Status"],
            "timing_ms": t,
        })
        step += 1
        t += 50

    elif scenario == "delayed_ack":
        # 1. Sender transmits Frame 1
        events.append({
            "step": step,
            "protocol": "SW-ARQ",
            "transport": "DATA LINK",
            "direction": "client-to-server",
            "summary": "Frame 1 Transmitted",
            "raw": (
                "[DATA FRAME] Frame=1 | Seq=1 | Length=64B\n"
                "Payload: 'Packet 1: Data Chunk 1' | CRC=0x1A37\n"
                "Receiver accepts Frame 1 and emits ACK 1, but network latency delays it."
            ),
            "fields": {
                "Frame Type": "Data Frame",
                "Seq No": "1",
                "Ack No": "-",
                "Sender State": "WAIT_FOR_ACK",
                "Receiver State": "EXPECT_1",
                "Window Size": "1",
                "Status": "Transmitted (ACK delayed in transit)",
                "Timer": "Started (150ms)",
            },
            "highlight": ["Frame Type", "Seq No", "Sender State", "Status"],
            "timing_ms": t,
        })
        step += 1
        t += 150

        # 2. Timeout Waiting for ACK 1
        events.append({
            "step": step,
            "protocol": "SW-ARQ",
            "transport": "DATA LINK",
            "direction": "client-to-server",
            "summary": "Timeout Waiting for ACK 1",
            "raw": (
                "[TIMEOUT] Premature timeout! ACK 1 delayed by congestion.\n"
                "Sender timer expires before delayed ACK 1 arrives."
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
            },
            "highlight": ["Frame Type", "Sender State", "Status", "Timer"],
            "timing_ms": t,
        })
        step += 1
        t += 20

        # 3. Retransmitting Frame 1
        events.append({
            "step": step,
            "protocol": "SW-ARQ",
            "transport": "DATA LINK",
            "direction": "client-to-server",
            "summary": "Retransmitting Frame 1",
            "raw": (
                "[RETRANSMISSION] Frame=1 | Seq=1 | Length=64B\n"
                "Sender retransmits Frame 1 while delayed ACK 1 is still in transit."
            ),
            "fields": {
                "Frame Type": "Data Frame (Retransmission)",
                "Seq No": "1",
                "Ack No": "-",
                "Sender State": "WAIT_FOR_ACK",
                "Receiver State": "EXPECT_0",
                "Window Size": "1",
                "Status": "Retransmitting Frame 1 (Seq 1)",
                "Timer": "Restarted (150ms)",
            },
            "highlight": ["Frame Type", "Seq No", "Sender State", "Status"],
            "timing_ms": t,
        })
        step += 1
        t += 30

        # 4. Delayed ACK 1 Received
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
            },
            "highlight": ["Frame Type", "Ack No", "Sender State", "Status"],
            "timing_ms": t,
        })
        step += 1
        t += 30

        # 5. Duplicate Frame 1 reaches Receiver
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
            },
            "highlight": ["Frame Type", "Seq No", "Receiver State", "Status"],
            "timing_ms": t,
        })
        step += 1
        t += 20

        # 6. Duplicate Discarded
        events.append({
            "step": step,
            "protocol": "SW-ARQ",
            "transport": "DATA LINK",
            "direction": "server-to-client",
            "summary": "Duplicate Discarded",
            "raw": (
                "[RECEIVER ACTION] Duplicate Frame 1 payload discarded.\n"
                "Data integrity preserved; no duplicate chunk delivered."
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
            },
            "highlight": ["Frame Type", "Receiver State", "Status"],
            "timing_ms": t,
        })
        step += 1
        t += 20

        # 7. ACK 1 Re-sent
        events.append({
            "step": step,
            "protocol": "SW-ARQ",
            "transport": "DATA LINK",
            "direction": "server-to-client",
            "summary": "ACK 1 Re-sent",
            "raw": (
                "[ACK RE-SEND] Ack=1 | Next Expected Seq=0\n"
                "Receiver re-sends ACK 1 to acknowledge duplicate."
            ),
            "fields": {
                "Frame Type": "ACK Frame (Re-sent)",
                "Seq No": "-",
                "Ack No": "1",
                "Sender State": "READY_FOR_NEXT",
                "Receiver State": "EXPECT_0",
                "Window Size": "1",
                "Status": "ACK 1 re-sent, channel synchronized",
                "Timer": "Stopped",
            },
            "highlight": ["Frame Type", "Ack No", "Receiver State", "Status"],
            "timing_ms": t,
        })
        step += 1
        t += 40

    # -----------------------------------------------------------------
    # Remaining Frames: Frame 2 .. frame_count - 1
    # -----------------------------------------------------------------
    for i in range(2, frame_count):
        seq = i % 2
        next_seq = 1 - seq
        crc_val = f"0x{(0x1A00 + i * 0x37):04X}"

        events.append({
            "step": step,
            "protocol": "SW-ARQ",
            "transport": "DATA LINK",
            "direction": "client-to-server",
            "summary": f"Frame {i} Transmitted",
            "raw": (
                f"[DATA FRAME] Frame={i} | Seq={seq} | Length=64B\n"
                f"Payload: 'Packet {i}: Data Chunk {i}' | CRC={crc_val}\n"
                f"Sender Window: [Frame {i}] (Size=1)"
            ),
            "fields": {
                "Frame Type": "Data Frame",
                "Seq No": str(seq),
                "Ack No": "-",
                "Sender State": "WAIT_FOR_ACK",
                "Receiver State": f"EXPECT_{seq}",
                "Window Size": "1",
                "Status": f"Frame {i} in transit to Receiver",
                "Timer": "Started (150ms)",
            },
            "highlight": ["Frame Type", "Seq No", "Sender State", "Status"],
            "timing_ms": t,
        })
        step += 1
        t += 50

        events.append({
            "step": step,
            "protocol": "SW-ARQ",
            "transport": "DATA LINK",
            "direction": "server-to-client",
            "summary": f"ACK {seq} Received",
            "raw": (
                f"[ACK FRAME] Ack={seq} | Next Expected Seq={next_seq}\n"
                f"Status: Frame {i} delivered to network layer\n"
                f"Receiver Window: [Ready for Seq {next_seq}]"
            ),
            "fields": {
                "Frame Type": "ACK Frame",
                "Seq No": "-",
                "Ack No": str(seq),
                "Sender State": "READY_FOR_NEXT",
                "Receiver State": f"EXPECT_{next_seq}",
                "Window Size": "1",
                "Status": f"Frame {i} acknowledged, sliding window",
                "Timer": "Stopped",
            },
            "highlight": ["Frame Type", "Ack No", "Receiver State", "Status"],
            "timing_ms": t,
        })
        step += 1
        t += 50

    return events
