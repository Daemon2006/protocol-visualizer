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
    const STEP_DELAY_MS = 1400; // pause between automatic steps

    // Grab the DOM elements once, so we don't re-query them every render.
    const stepIndicator = document.getElementById("protocol-step-indicator");
    const eventBox = document.getElementById("protocol-event");
    const btnPrevious = document.getElementById("btn-previous");
    const btnPause = document.getElementById("btn-pause");
    const btnNext = document.getElementById("btn-next");
    const btnReplay = document.getElementById("btn-replay");

    // NOTE on event.protocol / event.direction: these are only ever set by
    // our own backend simulator code to one of a small fixed set of values
    // ("DNS"/"HTTP", "client-to-server"/"server-to-client") -- they never
    // contain user-typed text, so they're safe to use directly in a CSS
    // class name. Anything that CAN contain user-typed text (event.raw,
    // event.summary, and the field keys/values, which derive from the
    // domain/path the user entered) is passed through escapeHtml() below
    // before being inserted into the page.

    function directionLabel(direction) {
        return direction === "client-to-server" ? "Client \u2192 Server" : "Server \u2192 Client";
    }

    // Escapes special HTML characters (<, >, &, quotes) in a value before
    // it gets inserted via innerHTML. This matters because event.raw and
    // event.fields can contain text that ultimately came from the user's
    // own URL input (the domain/path). Without this, someone could type
    // a URL containing HTML/script-like text and have it interpreted as
    // real markup instead of being shown as plain text.
    //
    // The trick: setting .textContent on a throwaway <div> always treats
    // the value as plain text, then reading .innerHTML back out gives us
    // that same text with any special characters safely HTML-encoded.
    function escapeHtml(value) {
        const holder = document.createElement("div");
        holder.textContent = String(value);
        return holder.innerHTML;
    }

    // Maps a protocol name to its badge color class. DNS/HTTP already
    // existed from Phase 1; SMTP is added here for Phase 2 (Mail) so
    // the visualizer can clearly tell the two apart, as required.
    function badgeClassFor(protocol) {
        if (protocol === "DNS") return "protocol-badge--dns";
        if (protocol === "SMTP") return "protocol-badge--smtp";
        return "protocol-badge--http";
    }

    // Turn one event object into HTML and drop it into the event box.
    function renderEvent(event) {
        const fieldRows = Object.entries(event.fields).map(([key, value]) => {
            const highlighted = event.highlight.includes(key);
            const rowClass = "protocol-field" + (highlighted ? " protocol-field--highlight" : "");
            return `
                <div class="${rowClass}">
                    <span class="protocol-field__key">${escapeHtml(key)}</span>
                    <span class="protocol-field__value">${escapeHtml(value)}</span>
                </div>`;
        }).join("");

        const badgeClass = badgeClassFor(event.protocol);

        eventBox.innerHTML = `
            <div class="protocol-message protocol-message--${event.direction}">
                <div class="protocol-message__meta">
                    <span class="protocol-badge ${badgeClass}">${escapeHtml(event.protocol)}</span>
                    <span class="protocol-direction">${directionLabel(event.direction)}</span>
                    <span class="protocol-timing">t = ${event.timing_ms} ms</span>
                </div>
                <h4 class="protocol-message__summary">${escapeHtml(event.summary)}</h4>
                <pre class="protocol-message__raw">${escapeHtml(event.raw)}</pre>
                <div class="protocol-fields">${fieldRows}</div>
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
        renderEvent(events[currentIndex]);
        updateStepIndicator();
        updateButtonStates();
    }

    function stopAutoPlay() {
        if (playTimer) {
            clearInterval(playTimer);
            playTimer = null;
        }
        btnPause.textContent = "\u2759\u2759 Pause";
    }

    function startAutoPlay() {
        stopAutoPlay();
        btnPause.textContent = "\u23F8 Playing\u2026";
        playTimer = setInterval(() => {
            if (currentIndex >= events.length - 1) {
                stopAutoPlay();
                return;
            }
            currentIndex += 1;
            showCurrentEvent();
        }, STEP_DELAY_MS);
    }

    let liveFollow = true;      // when true, auto-display newly arrived live events

    // Called by activity_panel.js after a successful fetch().
    function loadEvents(newEvents) {
        events = newEvents;
        currentIndex = -1;
        liveFollow = true;
        stopAutoPlay();

        if (events.length > 0) {
            currentIndex = 0;
            showCurrentEvent();
            startAutoPlay();
        }
    }

    // Progressively appends a live event (e.g. from live HLS playback)
    // without disturbing simulation playback controls.
    function appendLiveEvent(newEvent) {
        newEvent.step = events.length + 1;
        events.push(newEvent);

        if (liveFollow || currentIndex === events.length - 2 || currentIndex === -1) {
            currentIndex = events.length - 1;
            showCurrentEvent();
        } else {
            updateStepIndicator();
            updateButtonStates();
        }
    }

    function goNext() {
        if (currentIndex < events.length - 1) {
            currentIndex += 1;
            if (currentIndex === events.length - 1) {
                liveFollow = true;
            }
            showCurrentEvent();
        }
        stopAutoPlay(); // manual stepping takes over from auto-play
    }

    function goPrevious() {
        if (currentIndex > 0) {
            liveFollow = false;
            currentIndex -= 1;
            showCurrentEvent();
        }
        stopAutoPlay();
    }

    function togglePause() {
        if (playTimer) {
            stopAutoPlay();
        } else if (currentIndex < events.length - 1) {
            startAutoPlay();
        }
    }

    function replay() {
        if (events.length === 0) return;
        currentIndex = 0;
        showCurrentEvent();
        startAutoPlay();
    }

    // Clears the panel back to its "waiting" placeholder and drops any
    // loaded events. Used when the person switches activity tabs WITHOUT
    // submitting a new simulation -- without this, the previous
    // activity's last event and enabled controls would stay on screen,
    // which is misleading (e.g. switching to the Mail tab but still
    // seeing a Browsing HTTP response with working Previous/Next).
    function reset() {
        events = [];
        currentIndex = -1;
        liveFollow = true;
        stopAutoPlay();
        eventBox.innerHTML = '<p class="placeholder-note">Waiting for an activity on the left panel&hellip;</p>';
        updateStepIndicator();
        updateButtonStates();
    }

    btnNext.addEventListener("click", goNext);
    btnPrevious.addEventListener("click", goPrevious);
    btnPause.addEventListener("click", togglePause);
    btnReplay.addEventListener("click", replay);

    // loadEvents() starts a new sequence; appendLiveEvent() appends real-time events;
    // reset() clears the panel without starting one.
    return { loadEvents, appendLiveEvent, reset };
})();
