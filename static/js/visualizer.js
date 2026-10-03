// visualizer.js
//
// The "Visualizer Engine": stores the list of protocol events returned
// by the backend and steps through them one at a time in the Protocol
// panel. Previous / Pause / Next / Replay all just move a single
// "currentIndex" pointer and re-render the current event -- none of
// them make a new request to Flask. The array fetched from the
// backend is the single source of truth for everything the right
// panel shows for a given activity run.

const Visualizer = (() => {
    let events = [];
    let currentIndex = -1;      // -1 means "nothing loaded yet"
    let playTimer = null;       // handle for the auto-advance timer
    let isPaused = false;       // tracks whether playback/animation is currently paused
    let stepStartTime = 0;      // timestamp when the current step timer started
    const STEP_DELAY_MS = 1400; // duration of each automatic step
    let remainingStepMs = STEP_DELAY_MS;

    // Grab the DOM elements once, so we don't re-query them every render.
    const stepIndicator = document.getElementById("protocol-step-indicator");
    const eventBox = document.getElementById("protocol-event");
    const btnPrevious = document.getElementById("btn-previous");
    const btnPause = document.getElementById("btn-pause");
    const btnNext = document.getElementById("btn-next");
    const btnReplay = document.getElementById("btn-replay");

    function isClientToServer(direction) {
        return (
            direction === "client-to-server" ||
            direction === "C\u2192S" ||
            direction === "C->S"
        );
    }

    function directionClassFor(direction) {
        return isClientToServer(direction) ? "client-to-server" : "server-to-client";
    }

    function directionLabel(direction, protocol) {
        const isFlow = isFlowProtocol(protocol);
        if (isClientToServer(direction)) {
            return isFlow ? "Sender \u2192 Receiver" : "Client \u2192 Server";
        }
        return isFlow ? "Receiver \u2192 Sender" : "Server \u2192 Client";
    }

    // Escapes special HTML characters (<, >, &, quotes) in a value before
    // it gets inserted via innerHTML.
    function escapeHtml(value) {
        const holder = document.createElement("div");
        holder.textContent = String(value);
        return holder.innerHTML;
    }

    function isFlowProtocol(protocol) {
        return protocol === "STOP-AND-WAIT" || protocol === "SW-ARQ";
    }

    // Maps an Application / Flow Control Layer protocol name to its badge color class.
    function badgeClassFor(protocol) {
        if (protocol === "DNS") return "protocol-badge--dns";
        if (protocol === "SMTP") return "protocol-badge--smtp";
        if (isFlowProtocol(protocol)) return "protocol-badge--flow";
        return "protocol-badge--http";
    }

    // Maps a Transport / Data Link Layer protocol name to its badge color class.
    function transportBadgeClassFor(transport) {
        if (transport === "TCP") return "transport-badge--tcp";
        if (transport === "UDP") return "transport-badge--udp";
        if (transport === "DATA LINK") return "transport-badge--flow";
        return "transport-badge--unknown";
    }

    // Determines the left-hand source endpoint label.
    function clientLabelFor(protocol) {
        if (isFlowProtocol(protocol)) return "SENDER";
        return "CLIENT";
    }

    // Determines the right-hand destination endpoint label from protocol.
    function serverLabelFor(protocol) {
        if (protocol === "DNS") return "DNS SERVER";
        if (protocol === "SMTP") return "MAIL SERVER";
        if (isFlowProtocol(protocol)) return "RECEIVER";
        return "SERVER";
    }

    // Categorizes a flow control event into its semantic state
    // using structured fields as primary signals and summary as fallback.
    function getFlowEventCategory(event) {
        if (!event) return null;
        const protocol = event.protocol || "";
        if (!isFlowProtocol(protocol)) return null;

        const fields = event.fields || {};
        const frameType = (fields["Frame Type"] || "").toLowerCase();
        const senderState = (fields["Sender State"] || "").toLowerCase();
        const receiverState = (fields["Receiver State"] || "").toLowerCase();
        const status = (fields["Status"] || "").toLowerCase();
        const timer = (fields["Timer"] || "").toLowerCase();
        const summary = (event.summary || "").toLowerCase();

        if (frameType.includes("lost") || status.includes("lost in transit") || summary.includes("lost in transit")) {
            return "lost";
        }
        if (frameType.includes("timeout") || senderState.includes("timeout") || timer === "expired" || summary.includes("timeout")) {
            return "timeout";
        }
        if (frameType.includes("retransmission") || status.includes("retransmitting") || summary.includes("retransmitting")) {
            return "retransmission";
        }
        if (frameType.includes("duplicate discard") || receiverState.includes("duplicate_discarded") || summary.includes("duplicate discarded")) {
            return "duplicate-discard";
        }
        if (frameType.includes("duplicate") || receiverState.includes("duplicate_detected") || summary.includes("duplicate frame")) {
            return "duplicate";
        }
        if (frameType.includes("re-sent") || status.includes("re-sent") || summary.includes("re-sent")) {
            return "ack-resend";
        }
        if (frameType.includes("ack") || (fields["Ack No"] && fields["Ack No"] !== "-") || summary.includes("ack")) {
            return "ack";
        }
        if (frameType.includes("data") || (fields["Seq No"] && fields["Seq No"] !== "-") || summary.includes("frame")) {
            return "data";
        }
        return "normal";
    }

    // Dedicated Data Link / Flow Control layer renderer (distinct from TCP/UDP).
    function renderFlowControlLayer(event, index, clientLabel, serverLabel, arrowDirClass, arrowSymbol) {
        const category = getFlowEventCategory(event);
        const fields = event.fields || {};
        const seq = fields["Seq No"] && fields["Seq No"] !== "-" ? fields["Seq No"] : "";
        const ack = fields["Ack No"] && fields["Ack No"] !== "-" ? fields["Ack No"] : "";
        const timerVal = fields["Timer"] || "";

        let metaNote = "Stop-and-Wait Channel \u2022 Window Size = 1";
        if (category === "lost") {
            metaNote = "Frame Loss \u2022 Error in Channel";
        } else if (category === "timeout") {
            metaNote = "Timer Expired \u2022 Retransmit Triggered";
        } else if (category === "retransmission") {
            metaNote = `Retransmission \u2022 Seq ${seq || "1"} Unchanged`;
        } else if (category === "duplicate") {
            metaNote = "Duplicate Detected \u2022 Expected Seq Mismatch";
        } else if (category === "duplicate-discard") {
            metaNote = "Duplicate Discarded \u2022 Payload Dropped";
        } else if (category === "ack-resend") {
            metaNote = `ACK Recovery \u2022 Re-sent ACK ${ack || "1"}`;
        } else if (category === "ack") {
            metaNote = `ACK ${ack || "0"} Received \u2022 Window Sliding`;
        } else if (category === "data") {
            metaNote = `Data Frame (Seq ${seq || "0"}) \u2022 Window Size = 1`;
        }

        const timerPill = timerVal
            ? `<span class="transport-flow-pill transport-flow-pill--timer">Timer: ${escapeHtml(timerVal)}</span>`
            : "";

        let alertBoxHtml = "";
        let laneHtml = "";
        let statusHtml = "";

        if (category === "lost") {
            const isLossC2S = isClientToServer(event.direction);
            const lossText = isLossC2S ? `Frame ${seq || ""} Lost in Transit` : `ACK ${ack || ""} Lost in Transit`;
            alertBoxHtml = `
                <div class="transport-flow-alert transport-flow-alert--lost">
                    <span class="transport-flow-alert__icon">&#x2716;</span>
                    <div class="transport-flow-alert__body">
                        <strong>FRAME DROPPED IN PHYSICAL CHANNEL</strong>
                        <span>${escapeHtml(event.summary)}</span>
                    </div>
                </div>`;
            laneHtml = `
                <div class="transport-lane transport-lane--flow transport-lane--lost">
                    <div class="transport-packet transport-packet--flow transport-packet--lost ${arrowDirClass}">
                        <span class="transport-packet__label">${escapeHtml(lossText.toUpperCase())}</span>
                        <div class="transport-packet__track">
                            <span class="transport-packet__line">&#x2500;&#x2500;&#x2500; &#x2716; [TRANSMISSION LOST IN TRANSIT] &#x2500;&#x2500;&#x2500;</span>
                        </div>
                    </div>
                </div>`;
            statusHtml = `
                <div class="transport-status transport-status--lost">
                    ${isLossC2S
                        ? "FRAME LOST IN TRANSIT \u2014 RECEIVER WAITING \u2022 SENDER TIMER RUNNING"
                        : "ACK LOST IN REVERSE CHANNEL \u2014 SENDER WAITING UNTIL TIMEOUT"}
                </div>`;
        } else if (category === "timeout") {
            alertBoxHtml = `
                <div class="transport-flow-alert transport-flow-alert--timeout">
                    <span class="transport-flow-alert__icon">&#x23F1;</span>
                    <div class="transport-flow-alert__body">
                        <strong>TIMEOUT EXPIRED: Waiting for ACK ${escapeHtml(seq || "1")}</strong>
                        <span>Sender ACK timer expired (150ms elapsed) \u2014 triggering retransmission</span>
                    </div>
                </div>`;
            laneHtml = `
                <div class="transport-lane transport-lane--flow transport-lane--timeout">
                    <div class="transport-packet transport-packet--flow transport-packet--timeout">
                        <span class="transport-packet__label">SENDER TIMER EXPIRED &rarr; INITIATING RETRANSMISSION</span>
                        <div class="transport-packet__track">
                            <span class="transport-packet__line">&#x23F1; [TIMEOUT: TIMER EXPIRED (150ms)] &#x21BB;</span>
                        </div>
                    </div>
                </div>`;
            statusHtml = `
                <div class="transport-status transport-status--timeout">
                    TIMEOUT EXPIRED \u2014 SENDER ASSUMES FRAME OR ACK LOST \u2014 RETRANSMITTING
                </div>`;
        } else if (category === "retransmission") {
            alertBoxHtml = `
                <div class="transport-flow-alert transport-flow-alert--retransmission">
                    <span class="transport-flow-alert__icon">&#x21BB;</span>
                    <div class="transport-flow-alert__body">
                        <strong>RETRANSMITTING FRAME (SEQ ${escapeHtml(seq || "1")})</strong>
                        <span>Sequence number MUST remain unchanged (Seq ${escapeHtml(seq || "1")})</span>
                    </div>
                </div>`;
            laneHtml = `
                <div class="transport-lane transport-lane--flow transport-lane--retransmission">
                    <div class="transport-packet transport-packet--flow transport-packet--retransmission ${arrowDirClass}">
                        <span class="transport-packet__label">RETRANSMITTING FRAME: Seq ${escapeHtml(seq || "1")}</span>
                        <div class="transport-packet__track">
                            <span class="transport-packet__line">${arrowSymbol}</span>
                        </div>
                    </div>
                </div>`;
            statusHtml = `
                <div class="transport-status transport-status--retransmission">
                    RETRANSMISSION IN PROGRESS (SEQ ${escapeHtml(seq || "1")}) \u2014 TIMER RESTARTED
                </div>`;
        } else if (category === "duplicate") {
            const exp = fields["Receiver State"] ? fields["Receiver State"].replace("EXPECT_", "") : "0";
            alertBoxHtml = `
                <div class="transport-flow-alert transport-flow-alert--duplicate">
                    <span class="transport-flow-alert__icon">&#x26A0;</span>
                    <div class="transport-flow-alert__body">
                        <strong>DUPLICATE FRAME DETECTED</strong>
                        <span>Received Seq ${escapeHtml(seq || "1")}, but Receiver expects Seq ${escapeHtml(exp)}</span>
                    </div>
                </div>`;
            laneHtml = `
                <div class="transport-lane transport-lane--flow transport-lane--duplicate">
                    <div class="transport-packet transport-packet--flow transport-packet--duplicate">
                        <span class="transport-packet__label">DUPLICATE DETECTED AT RECEIVER</span>
                        <div class="transport-packet__track">
                            <span class="transport-packet__line">&#x26A0; [DUPLICATE FRAME ${escapeHtml(seq || "1")} DETECTED] &#x26A0;</span>
                        </div>
                    </div>
                </div>`;
            statusHtml = `
                <div class="transport-status transport-status--duplicate">
                    DUPLICATE FRAME DETECTED BY RECEIVER \u2014 ALTERNATING BIT CHECK
                </div>`;
        } else if (category === "duplicate-discard") {
            alertBoxHtml = `
                <div class="transport-flow-alert transport-flow-alert--discard">
                    <span class="transport-flow-alert__icon">&#x1F5D1;</span>
                    <div class="transport-flow-alert__body">
                        <strong>DUPLICATE PAYLOAD DISCARDED</strong>
                        <span>Critical Rule: Data chunk is NOT delivered to upper network layer twice</span>
                    </div>
                </div>`;
            laneHtml = `
                <div class="transport-lane transport-lane--flow transport-lane--discard">
                    <div class="transport-packet transport-packet--flow transport-packet--discard">
                        <span class="transport-packet__label">PAYLOAD DISCARDED &rarr; PRESERVING DATA INTEGRITY</span>
                        <div class="transport-packet__track">
                            <span class="transport-packet__line">&#x1F5D1; [DUPLICATE DISCARDED \u2014 NOT DELIVERED TWICE]</span>
                        </div>
                    </div>
                </div>`;
            statusHtml = `
                <div class="transport-status transport-status--discard">
                    DUPLICATE DISCARDED \u2014 RECEIVER PREPARING RE-SENT ACK
                </div>`;
        } else if (category === "ack-resend") {
            laneHtml = `
                <div class="transport-lane transport-lane--flow">
                    <div class="transport-packet transport-packet--flow transport-packet--ack-resend ${arrowDirClass}">
                        <span class="transport-packet__label">ACK RE-SENT: ACK ${escapeHtml(ack || "1")} (Recovery)</span>
                        <div class="transport-packet__track">
                            <span class="transport-packet__line">${arrowSymbol}</span>
                        </div>
                    </div>
                </div>`;
            statusHtml = `
                <div class="transport-status transport-status--ack-resend">
                    ACK RE-SENT BY RECEIVER \u2014 SENDER RECOVERY IN PROGRESS
                </div>`;
        } else if (category === "ack") {
            laneHtml = `
                <div class="transport-lane transport-lane--flow">
                    <div class="transport-packet transport-packet--flow ${arrowDirClass}">
                        <span class="transport-packet__label">ACK FRAME: ACK ${escapeHtml(ack || "0")} (Delivered)</span>
                        <div class="transport-packet__track">
                            <span class="transport-packet__line">${arrowSymbol}</span>
                        </div>
                    </div>
                </div>`;
            statusHtml = `
                <div class="transport-status transport-status--flow-ack">
                    ACK RECEIVED \u2014 SENDER ADVANCING WINDOW &middot; TIMER STOPPED
                </div>`;
        } else {
            laneHtml = `
                <div class="transport-lane transport-lane--flow">
                    <div class="transport-packet transport-packet--flow ${arrowDirClass}">
                        <span class="transport-packet__label">DATA FRAME: Seq ${escapeHtml(seq || "0")} &middot; Window: 1</span>
                        <div class="transport-packet__track">
                            <span class="transport-packet__line">${arrowSymbol}</span>
                        </div>
                    </div>
                </div>`;
            statusHtml = `
                <div class="transport-status transport-status--flow">
                    FRAME IN TRANSIT \u2014 SENDER WAITING FOR ACK ${escapeHtml(seq || "0")}
                </div>`;
        }

        return `
            <div class="transport-layer transport-layer--flow">
                <div class="protocol-layer-header">
                    <span class="protocol-layer-title">DATA LINK / FLOW CONTROL</span>
                    <span class="transport-badge ${transportBadgeClassFor("DATA LINK")}">DATA LINK</span>
                    <span class="transport-meta-note">${escapeHtml(metaNote)}</span>
                </div>
                <div class="transport-diagram transport-diagram--flow">
                    <div class="transport-endpoints">
                        <span class="transport-endpoint transport-endpoint--sender">${escapeHtml(clientLabel)}</span>
                        <div class="transport-flow-badges">
                            <span class="transport-flow-pill">Window: 1</span>
                            ${timerPill}
                        </div>
                        <span class="transport-endpoint transport-endpoint--receiver">${escapeHtml(serverLabel)}</span>
                    </div>
                    ${alertBoxHtml}
                    ${laneHtml}
                    ${statusHtml}
                </div>
            </div>`;
    }

    // Dynamically determines whether the event at `index` is the beginning
    // of a TCP conversation/exchange using event metadata and sequence flow
    // (never hardcoded step numbers).
    function isTcpConnectionStart(index) {
        if (index < 0 || index >= events.length) return false;
        const current = events[index];
        if (!current || current.transport !== "TCP") return false;
        if (index === 0) return true;
        const prev = events[index - 1];
        return !prev || prev.transport !== "TCP" || prev.protocol !== current.protocol;
    }

    // Reusable Transport Layer visualization component for TCP, UDP, or unspecified transport.
    function renderTransportLayer(event, index) {
        const transport = event && event.transport ? String(event.transport).toUpperCase() : "";
        const clientLabel = clientLabelFor(event.protocol);
        const serverLabel = serverLabelFor(event.protocol);
        const c2s = isClientToServer(event.direction);
        const arrowDirClass = c2s ? "transport-arrow--c2s" : "transport-arrow--s2c";
        const arrowSymbol = c2s ? "\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2192" : "\u2190\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500";

        if (!transport) {
            return `
                <div class="transport-layer transport-layer--unknown">
                    <div class="protocol-layer-header">
                        <span class="protocol-layer-title">TRANSPORT LAYER</span>
                        <span class="transport-badge transport-badge--unknown">Not specified</span>
                    </div>
                    <p class="transport-layer__empty">Transport Layer: Not specified</p>
                </div>`;
        }

        if (transport === "DATA LINK" || isFlowProtocol(event.protocol)) {
            return renderFlowControlLayer(event, index, clientLabel, serverLabel, arrowDirClass, arrowSymbol);
        }

        if (transport === "UDP") {
            return `
                <div class="transport-layer transport-layer--udp">
                    <div class="protocol-layer-header">
                        <span class="protocol-layer-title">TRANSPORT LAYER</span>
                        <span class="transport-badge ${transportBadgeClassFor("UDP")}">UDP</span>
                        <span class="transport-meta-note">Connectionless &middot; No Handshake</span>
                    </div>
                    <div class="transport-diagram">
                        <div class="transport-endpoints">
                            <span class="transport-endpoint transport-endpoint--client">${escapeHtml(clientLabel)}</span>
                            <span class="transport-endpoint transport-endpoint--server">${escapeHtml(serverLabel)}</span>
                        </div>
                        <div class="transport-udp-note">
                            UDP = Connectionless (No SYN &middot; No SYN-ACK &middot; No ACK)
                        </div>
                        <div class="transport-lane transport-lane--datagram">
                            <div class="transport-packet transport-packet--udp ${arrowDirClass}">
                                <span class="transport-packet__label">UDP DATAGRAM: ${escapeHtml(event.summary)}</span>
                                <div class="transport-packet__track">
                                    <span class="transport-packet__line">${arrowSymbol}</span>
                                </div>
                            </div>
                        </div>
                        <div class="transport-status transport-status--udp">
                            DATAGRAM RECEIVED
                        </div>
                    </div>
                </div>`;
        }

        if (transport === "TCP") {
            const showHandshakeAnim = isTcpConnectionStart(index);
            const handshakeClass = showHandshakeAnim
                ? "transport-handshake transport-handshake--animate"
                : "transport-handshake transport-handshake--established";
            const payloadDelayClass = showHandshakeAnim
                ? "transport-packet--after-handshake"
                : "transport-packet--immediate";

            return `
                <div class="transport-layer transport-layer--tcp">
                    <div class="protocol-layer-header">
                        <span class="protocol-layer-title">TRANSPORT LAYER</span>
                        <span class="transport-badge ${transportBadgeClassFor("TCP")}">TCP</span>
                        <span class="transport-meta-note">${showHandshakeAnim ? "3-Way Handshake + Data Transfer" : "Established TCP Connection"}</span>
                    </div>
                    <div class="transport-diagram">
                        <div class="transport-endpoints">
                            <span class="transport-endpoint transport-endpoint--client">${escapeHtml(clientLabel)}</span>
                            <span class="transport-endpoint transport-endpoint--server">${escapeHtml(serverLabel)}</span>
                        </div>
                        <div class="${handshakeClass}">
                            <div class="transport-handshake__step transport-handshake__step--syn">
                                <span class="transport-handshake__tag">SYN</span>
                                <span class="transport-handshake__arrow transport-handshake__arrow--c2s">\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2192</span>
                            </div>
                            <div class="transport-handshake__step transport-handshake__step--synack">
                                <span class="transport-handshake__arrow transport-handshake__arrow--s2c">\u2190\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500</span>
                                <span class="transport-handshake__tag">SYN-ACK</span>
                            </div>
                            <div class="transport-handshake__step transport-handshake__step--ack">
                                <span class="transport-handshake__tag">ACK</span>
                                <span class="transport-handshake__arrow transport-handshake__arrow--c2s">\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2192</span>
                            </div>
                            <div class="transport-status transport-status--tcp">
                                TCP CONNECTION ESTABLISHED
                            </div>
                        </div>
                        <div class="transport-lane transport-lane--tcp">
                            <div class="transport-packet transport-packet--tcp ${payloadDelayClass} ${arrowDirClass}">
                                <span class="transport-packet__label">${escapeHtml(event.protocol)}: ${escapeHtml(event.summary)}</span>
                                <div class="transport-packet__track">
                                    <span class="transport-packet__line">${arrowSymbol}</span>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>`;
        }

        return `
            <div class="transport-layer transport-layer--unknown">
                <div class="protocol-layer-header">
                    <span class="protocol-layer-title">TRANSPORT LAYER</span>
                    <span class="transport-badge transport-badge--unknown">${escapeHtml(transport)}</span>
                </div>
                <p class="transport-layer__empty">Transport Layer: ${escapeHtml(transport)}</p>
            </div>`;
    }

    // Turn one event object into HTML and drop it into the event box.
    function renderEvent(event, index) {
        const fieldsObj = event.fields || {};
        const highlightList = Array.isArray(event.highlight) ? event.highlight : [];

        const fieldRows = Object.entries(fieldsObj).map(([key, value]) => {
            const highlighted = highlightList.includes(key);
            const rowClass = "protocol-field" + (highlighted ? " protocol-field--highlight" : "");
            return `
                <div class="${rowClass}">
                    <span class="protocol-field__key">${escapeHtml(key)}</span>
                    <span class="protocol-field__value">${escapeHtml(value)}</span>
                </div>`;
        }).join("");

        const badgeClass = badgeClassFor(event.protocol);
        const dirClass = directionClassFor(event.direction);
        const transportHtml = renderTransportLayer(event, index);

        const category = getFlowEventCategory(event);
        const statusClass = category ? ` protocol-message--${category}` : "";
        const isFlow = isFlowProtocol(event.protocol);
        const layerTitle = isFlow ? "DATA LINK / FLOW CONTROL" : "APPLICATION LAYER";

        eventBox.innerHTML = `
            <div class="protocol-layers">
                <div class="application-layer">
                    <div class="protocol-layer-header">
                        <span class="protocol-layer-title">${escapeHtml(layerTitle)}</span>
                        <span class="protocol-badge ${badgeClass}">${escapeHtml(event.protocol)}</span>
                    </div>
                    <div class="protocol-message protocol-message--${dirClass}${statusClass}">
                        <div class="protocol-message__meta">
                            <span class="protocol-badge ${badgeClass}">${escapeHtml(event.protocol)}</span>
                            <span class="protocol-direction">${directionLabel(event.direction, event.protocol)}</span>
                            <span class="protocol-timing">t = ${event.timing_ms} ms</span>
                        </div>
                        <h4 class="protocol-message__summary">${escapeHtml(event.summary)}</h4>
                        <pre class="protocol-message__raw">${escapeHtml(event.raw)}</pre>
                        <div class="protocol-fields">${fieldRows}</div>
                    </div>
                </div>
                ${transportHtml}
            </div>`;
    }

    function updateStepIndicator() {
        stepIndicator.textContent = events.length === 0
            ? "Step 0 of 0"
            : `Step ${currentIndex + 1} of ${events.length}`;
    }

    function updateButtonStates() {
        const hasEvents = events.length > 0;
        btnPrevious.disabled = !hasEvents || currentIndex <= 0;
        btnNext.disabled = !hasEvents || currentIndex >= events.length - 1;
        btnReplay.disabled = !hasEvents;
        btnPause.disabled = !hasEvents;
    }

    function showCurrentEvent() {
        if (currentIndex < 0 || currentIndex >= events.length) {
            return;
        }
        eventBox.classList.remove("transport-viz--paused");
        renderEvent(events[currentIndex], currentIndex);
        updateStepIndicator();
        updateButtonStates();
        remainingStepMs = STEP_DELAY_MS;
        stepStartTime = performance.now();
    }

    function stopAutoPlay(pauseVisuals = false) {
        if (playTimer) {
            clearTimeout(playTimer);
            playTimer = null;
        }
        isPaused = pauseVisuals;
        if (pauseVisuals) {
            eventBox.classList.add("transport-viz--paused");
        } else {
            eventBox.classList.remove("transport-viz--paused");
        }
        btnPause.textContent = "\u2759\u2759 Pause";
    }

    function scheduleNextStep(delayMs) {
        if (playTimer) {
            clearTimeout(playTimer);
            playTimer = null;
        }
        isPaused = false;
        eventBox.classList.remove("transport-viz--paused");
        btnPause.textContent = "\u23F8 Playing\u2026";
        remainingStepMs = delayMs;
        stepStartTime = performance.now();

        playTimer = setTimeout(() => {
            playTimer = null;
            if (currentIndex >= events.length - 1) {
                stopAutoPlay(false);
                return;
            }
            currentIndex += 1;
            showCurrentEvent();
            scheduleNextStep(STEP_DELAY_MS);
        }, delayMs);
    }

    function startAutoPlay() {
        scheduleNextStep(STEP_DELAY_MS);
    }

    let liveFollow = true;      // when true, auto-display newly arrived live events

    // Called by activity_panel.js after a successful fetch().
    function loadEvents(newEvents) {
        events = newEvents;
        currentIndex = -1;
        liveFollow = true;
        stopAutoPlay(false);

        if (events.length > 0) {
            currentIndex = 0;
            showCurrentEvent();
            startAutoPlay();
        }
    }

    // Progressively appends a live event (e.g. from live HLS playback)
    // without disturbing simulation playback controls or skipping in-progress steps.
    function appendLiveEvent(newEvent) {
        newEvent.step = events.length + 1;
        events.push(newEvent);

        if (currentIndex === -1) {
            currentIndex = 0;
            showCurrentEvent();
            startAutoPlay();
        } else if (playTimer || isPaused) {
            // Auto-play is currently stepping through earlier events (such as Live DNS
            // Query/Response -> Manifest Request/Response) or playback is paused.
            // Keep the current event visible so it is not skipped; scheduleNextStep()
            // will naturally advance through each queued event in order.
            updateStepIndicator();
            updateButtonStates();
        } else if (liveFollow && currentIndex < events.length - 1) {
            currentIndex += 1;
            showCurrentEvent();
            startAutoPlay();
        } else {
            updateStepIndicator();
            updateButtonStates();
        }
    }

    function goNext() {
        stopAutoPlay(false); // manual stepping takes over from auto-play
        if (currentIndex < events.length - 1) {
            currentIndex += 1;
            if (currentIndex === events.length - 1) {
                liveFollow = true;
            }
            showCurrentEvent();
        }
    }

    function goPrevious() {
        stopAutoPlay(false);
        if (currentIndex > 0) {
            liveFollow = false;
            currentIndex -= 1;
            showCurrentEvent();
        }
    }

    function togglePause() {
        if (events.length === 0) return;

        if (playTimer) {
            // Currently auto-playing: pause timer and freeze CSS animation in place
            const elapsed = performance.now() - stepStartTime;
            remainingStepMs = Math.max(150, remainingStepMs - elapsed);
            stopAutoPlay(true);
        } else if (isPaused) {
            // Currently paused: resume CSS animation from paused visual state and continue timer
            scheduleNextStep(remainingStepMs);
        } else if (currentIndex < events.length - 1) {
            // Stopped manually before the end: resume auto-play
            scheduleNextStep(STEP_DELAY_MS);
        } else {
            // On the final step after timer finished: toggle CSS animation pause state
            const nowPaused = !eventBox.classList.contains("transport-viz--paused");
            eventBox.classList.toggle("transport-viz--paused", nowPaused);
            isPaused = nowPaused;
        }
    }

    function replay() {
        if (events.length === 0) return;
        stopAutoPlay(false);
        currentIndex = 0;
        showCurrentEvent();
        startAutoPlay();
    }

    // Clears the panel back to its "waiting" placeholder and drops any
    // loaded events.
    function reset() {
        events = [];
        currentIndex = -1;
        liveFollow = true;
        stopAutoPlay(false);
        eventBox.innerHTML = '<p class="placeholder-note">Waiting for an activity on the left panel&hellip;</p>';
        updateStepIndicator();
        updateButtonStates();
    }

    btnNext.addEventListener("click", goNext);
    btnPrevious.addEventListener("click", goPrevious);
    btnPause.addEventListener("click", togglePause);
    btnReplay.addEventListener("click", replay);

    return { loadEvents, appendLiveEvent, reset };
})();
