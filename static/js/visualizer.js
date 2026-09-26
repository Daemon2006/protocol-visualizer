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

    function directionLabel(direction) {
        return isClientToServer(direction) ? "Client \u2192 Server" : "Server \u2192 Client";
    }

    // Escapes special HTML characters (<, >, &, quotes) in a value before
    // it gets inserted via innerHTML.
    function escapeHtml(value) {
        const holder = document.createElement("div");
        holder.textContent = String(value);
        return holder.innerHTML;
    }

    // Maps an Application Layer protocol name to its badge color class.
    function badgeClassFor(protocol) {
        if (protocol === "DNS") return "protocol-badge--dns";
        if (protocol === "SMTP") return "protocol-badge--smtp";
        return "protocol-badge--http";
    }

    // Maps a Transport Layer protocol name to its badge color class.
    function transportBadgeClassFor(transport) {
        if (transport === "TCP") return "transport-badge--tcp";
        if (transport === "UDP") return "transport-badge--udp";
        return "transport-badge--unknown";
    }

    // Determines the right-hand server endpoint label from the application protocol.
    function serverLabelFor(protocol) {
        if (protocol === "DNS") return "DNS SERVER";
        if (protocol === "SMTP") return "MAIL SERVER";
        return "SERVER";
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
                            <span class="transport-endpoint transport-endpoint--client">CLIENT</span>
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
                            <span class="transport-endpoint transport-endpoint--client">CLIENT</span>
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

        eventBox.innerHTML = `
            <div class="protocol-layers">
                <div class="application-layer">
                    <div class="protocol-layer-header">
                        <span class="protocol-layer-title">APPLICATION LAYER</span>
                        <span class="protocol-badge ${badgeClass}">${escapeHtml(event.protocol)}</span>
                    </div>
                    <div class="protocol-message protocol-message--${dirClass}">
                        <div class="protocol-message__meta">
                            <span class="protocol-badge ${badgeClass}">${escapeHtml(event.protocol)}</span>
                            <span class="protocol-direction">${directionLabel(event.direction)}</span>
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
