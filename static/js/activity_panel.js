// activity_panel.js
//
// Handles the left Activity Panel for all three activities:
//   - Browsing form (Phase 1 Simulation + Live DNS/HTTP + Browser Preview)
//   - Mail form (Phase 2 Simulation + Live authenticated SMTP submission)
//   - Streaming form (Phase 3 Simulation + Live HLS playback & event capture)
//
// Shared responsibilities:
//   1. read the form's input values and mode selection
//   2. send requests to the Flask backend or initialize real browser/player components
//   3. feed protocol events to the single shared Visualizer Engine
//   4. maintain the status text and Activity Log
//
// Exactly TWO main panels are maintained. Browser preview and video player
// live exclusively inside this left Activity Panel.

const statusText = document.getElementById("activity-status");
const logList = document.getElementById("activity-log-list");

function setStatus(message, isError = false) {
    statusText.textContent = message;
    statusText.classList.toggle("activity-status--error", isError);
}

function addLogEntry(message) {
    const emptyItem = logList.querySelector(".activity-log__empty");
    if (emptyItem) {
        emptyItem.remove();
    }

    const item = document.createElement("li");
    const time = new Date().toLocaleTimeString();
    item.textContent = `[${time}] ${message}`;
    logList.prepend(item);
}

// ---------------------------------------------------------------
// Activity tabs: switch which form panel is visible.
// ---------------------------------------------------------------
const tabButtons = document.querySelectorAll(".activity-tab");
const formPanels = {
    browsing: document.getElementById("browsing-panel"),
    mail: document.getElementById("mail-panel"),
    streaming: document.getElementById("streaming-panel"),
    flowControl: document.getElementById("flow-control-panel"),
};
const defaultStatusForActivity = {
    browsing: "Enter a URL and click Visit to begin.",
    mail: "Fill in To, Subject, and Body, then click Send.",
    streaming: "Choose a quality and click Play to begin.",
    "flow-control": "Select a protocol variant and click Simulate to begin.",
    flowControl: "Select a protocol variant and click Simulate to begin.",
};

let activeActivity = "browsing";

// Video and HLS state
let hlsInstance = null;
const videoPlayer = document.getElementById("live-video-player");
const videoContainer = document.getElementById("live-video-container");
const videoError = document.getElementById("live-video-error");
const streamingUrlGroup = document.getElementById("streaming-url-group");
const streamingUrlInput = document.getElementById("streaming-url");

// Browser preview state
const previewContainer = document.getElementById("browser-preview-container");
const previewIframe = document.getElementById("browser-preview-iframe");
const previewAddress = document.getElementById("browser-preview-address");
const previewFallback = document.getElementById("browser-preview-fallback");
const previewLink = document.getElementById("browser-preview-link");
const previewOpenTab = document.getElementById("browser-preview-open-tab");
const btnToggleFallback = document.getElementById("btn-toggle-fallback");

if (btnToggleFallback) {
    btnToggleFallback.addEventListener("click", () => {
        previewFallback.classList.toggle("browser-preview__fallback--hidden");
    });
}

// Major platforms known to strictly block iframe embedding via X-Frame-Options / CSP
const KNOWN_EMBED_BLOCKED = [
    "facebook", "fb.com", "google", "youtube", "twitter", "x.com",
    "instagram", "linkedin", "github", "reddit", "amazon", "netflix",
    "apple.com", "yahoo"
];

function switchActivity(activityName) {
    activeActivity = activityName;

    // Pause video playback if user navigates away from Streaming
    if (videoPlayer && !videoPlayer.paused) {
        videoPlayer.pause();
    }

    tabButtons.forEach((btn) => {
        const isActive = btn.dataset.activity === activityName;
        btn.classList.toggle("activity-tab--active", isActive);
        btn.setAttribute("aria-selected", isActive ? "true" : "false");
    });
    Object.entries(formPanels).forEach(([name, panel]) => {
        const isSelected = name === activityName || (name === "flowControl" && activityName === "flow-control");
        panel.classList.toggle("activity-form-panel--hidden", !isSelected);
    });
    setStatus(defaultStatusForActivity[activityName] || "Select an activity to begin.");

    // Clear any leftover sequence from the previously selected activity
    Visualizer.reset();
}

tabButtons.forEach((btn) => {
    btn.addEventListener("click", () => switchActivity(btn.dataset.activity));
});

// ---------------------------------------------------------------
// Browsing Activity (Simulation + Live Mode + Browser Preview)
// ---------------------------------------------------------------
const browsingForm = document.getElementById("browsing-form");
const urlInput = document.getElementById("url-input");
const visitButton = document.getElementById("visit-button");

function getBrowsingMode() {
    const checked = document.querySelector('input[name="browsing-mode"]:checked');
    return checked ? checked.value : "simulation";
}

document.querySelectorAll('input[name="browsing-mode"]').forEach((radio) => {
    radio.addEventListener("change", () => {
        if (getBrowsingMode() === "simulation") {
            previewContainer.classList.add("browser-preview-container--hidden");
            previewIframe.src = "about:blank";
        }
    });
});

function extractLiveSummary(events) {
    const dnsResponse = events[1];
    const httpResponse = events[3];
    const fields = (httpResponse && httpResponse.fields) ? httpResponse.fields : {};

    let xfo = null;
    let csp = null;
    let location = null;
    for (const [k, v] of Object.entries(fields)) {
        const lower = k.toLowerCase();
        if (lower === "x-frame-options") xfo = v;
        if (lower === "content-security-policy") csp = v;
        if (lower === "location") location = v;
    }

    // Check if CSP contains a restrictive frame-ancestors directive
    let cspBlocksFraming = false;
    if (csp) {
        const cspLower = String(csp).toLowerCase();
        if (cspLower.includes("frame-ancestors")) {
            const match = cspLower.match(/frame-ancestors\s+([^;]+)/);
            const policyVal = match ? match[1].trim() : "";
            if (policyVal !== "*" && policyVal !== "http: https:") {
                cspBlocksFraming = true;
            }
        }
    }

    return {
        ip: dnsResponse && dnsResponse.fields ? dnsResponse.fields["IP Address"] : "unknown",
        status: fields["Status"] || null,
        scheme: fields["Scheme"] || null,
        xFrameOptions: xfo,
        contentSecurityPolicy: csp,
        cspBlocksFraming: cspBlocksFraming,
        location: location,
    };
}

browsingForm.addEventListener("submit", async (event) => {
    event.preventDefault();

    const rawUrl = urlInput.value.trim();
    if (!rawUrl) {
        setStatus("Please enter a URL before clicking Visit.", true);
        return;
    }

    const isLive = getBrowsingMode() === "live";
    const endpoint = isLive ? "/api/live/browsing" : "/api/simulate/browsing";

    // Strict scheme validation for Live Mode
    let liveUrl = rawUrl;
    if (isLive) {
        if (rawUrl.includes("://")) {
            const scheme = rawUrl.split("://")[0].toLowerCase();
            if (scheme !== "http" && scheme !== "https") {
                setStatus(`Live mode only supports http:// and https:// URLs (got '${scheme}://').`, true);
                return;
            }
        } else {
            liveUrl = "https://" + rawUrl;
        }
    }

    visitButton.disabled = true;
    setStatus(isLive ? `Resolving and fetching ${rawUrl} (Live) ...` : `Visiting ${rawUrl} ...`);

    // Prepare Browser Preview container (wait for backend response before setting iframe.src
    // so blocked sites or SSL errors do not trigger broken browser error frames)
    if (isLive) {
        previewContainer.classList.remove("browser-preview-container--hidden");
        previewAddress.textContent = liveUrl;
        if (previewLink) previewLink.href = liveUrl;
        if (previewOpenTab) previewOpenTab.href = liveUrl;
        previewFallback.classList.add("browser-preview__fallback--hidden");
        previewIframe.src = "about:blank";
    } else {
        previewContainer.classList.add("browser-preview-container--hidden");
        previewIframe.src = "about:blank";
    }

    try {
        const response = await fetch(endpoint, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ url: rawUrl }),
        });

        const data = await response.json();

        if (!response.ok) {
            const errMsg = data.error || "Something went wrong.";
            setStatus(errMsg, true);
            if (isLive) {
                addLogEntry(`Live browsing failed for ${rawUrl}: ${errMsg}`);
                previewContainer.classList.add("browser-preview-container--hidden");
                previewIframe.src = "about:blank";
                if (activeActivity === "browsing") {
                    Visualizer.reset();
                }
            }
            return;
        }

        if (isLive) {
            const { ip, status, scheme, xFrameOptions, cspBlocksFraming, location } = extractLiveSummary(data.events);
            addLogEntry(
                `Live browsing completed: ${data.domain} \u2014 resolved IP: ${ip}` +
                `${scheme ? `, protocol: ${scheme}` : ""}${status ? `, status: ${status}` : ""}`
            );

            // Detect iframe refusal from X-Frame-Options, CSP frame-ancestors, or known blocked hosts
            const domainLower = (data.domain || "").toLowerCase();
            const locLower = (location || "").toLowerCase();
            const isBlockedSite = KNOWN_EMBED_BLOCKED.some(site => domainLower.includes(site) || locLower.includes(site));

            if (xFrameOptions || cspBlocksFraming || isBlockedSite) {
                previewIframe.src = "about:blank";
                previewFallback.classList.remove("browser-preview__fallback--hidden");
            } else {
                previewIframe.onerror = () => {
                    previewFallback.classList.remove("browser-preview__fallback--hidden");
                };
                previewIframe.src = liveUrl;
            }
        } else {
            addLogEntry(`Visited ${rawUrl} (${data.events.length} protocol steps)`);
        }

        if (activeActivity === "browsing") {
            if (isLive) {
                const { ip, status, scheme } = extractLiveSummary(data.events);
                setStatus(
                    `Live browsing complete \u2014 ${data.domain} -> ${ip}` +
                    `${scheme ? `, ${scheme}` : ""}${status ? `, status ${status}` : ""}.`
                );
            } else {
                setStatus(`Browsing simulation complete \u2014 visited ${data.domain} (${data.events.length} protocol steps).`);
            }
            Visualizer.loadEvents(data.events);
        }

    } catch (err) {
        setStatus("Could not reach the server. Is the Flask app running?", true);
    } finally {
        visitButton.disabled = false;
    }
});

// ---------------------------------------------------------------
// Mail Activity (Simulation + Live authenticated SMTP submission)
// ---------------------------------------------------------------
const mailForm = document.getElementById("mail-form");
const mailToInput = document.getElementById("mail-to");
const mailSubjectInput = document.getElementById("mail-subject");
const mailBodyInput = document.getElementById("mail-body");
const sendButton = document.getElementById("send-button");

function getMailMode() {
    const checked = document.querySelector('input[name="mail-mode"]:checked');
    return checked ? checked.value : "simulation";
}

mailForm.addEventListener("submit", async (event) => {
    event.preventDefault();

    const to = mailToInput.value.trim();
    const subject = mailSubjectInput.value.trim();
    const body = mailBodyInput.value.trim();

    if (!to || !subject || !body) {
        setStatus("Please fill in To, Subject, and Body before clicking Send.", true);
        return;
    }

    const isLive = getMailMode() === "live";
    const endpoint = isLive ? "/api/live/mail" : "/api/simulate/mail";

    sendButton.disabled = true;
    setStatus(isLive ? `Submitting live mail to ${to} (SMTP) ...` : `Sending mail to ${to} ...`);

    try {
        const response = await fetch(endpoint, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ to, subject, body }),
        });

        const data = await response.json();

        if (!response.ok) {
            setStatus(data.error || "Something went wrong.", true);
            if (isLive && activeActivity === "mail") {
                Visualizer.reset();
            }
            return;
        }

        if (isLive) {
            addLogEntry(`Live email sent successfully to ${to} (${data.events.length} protocol steps)`);
            if (activeActivity === "mail") {
                setStatus(`Live email sent successfully \u2014 delivered to ${to} (${data.events.length} protocol steps).`);
                Visualizer.loadEvents(data.events);
            }
        } else {
            addLogEntry(`Sent mail to ${to} (${data.events.length} protocol steps)`);
            if (activeActivity === "mail") {
                setStatus(`Mail simulation complete \u2014 sent to ${data.to} (${data.events.length} protocol steps).`);
                Visualizer.loadEvents(data.events);
            }
        }

    } catch (err) {
        setStatus("Could not reach the server. Is the Flask app running?", true);
    } finally {
        sendButton.disabled = false;
    }
});

// ---------------------------------------------------------------
// Streaming Activity (Simulation + Live HLS Playback & Events)
// ---------------------------------------------------------------
const streamingForm = document.getElementById("streaming-form");
const streamingQualitySelect = document.getElementById("streaming-quality");
const playButton = document.getElementById("play-button");

function getStreamingMode() {
    const checked = document.querySelector('input[name="streaming-mode"]:checked');
    return checked ? checked.value : "simulation";
}

function restoreSimulationQualities() {
    streamingQualitySelect.innerHTML = `
        <option value="360p">360p</option>
        <option value="720p" selected>720p</option>
        <option value="1080p">1080p</option>
    `;
}

document.querySelectorAll('input[name="streaming-mode"]').forEach((radio) => {
    radio.addEventListener("change", () => {
        const mode = getStreamingMode();
        if (mode === "live") {
            streamingUrlGroup.style.display = "block";
            videoContainer.classList.remove("live-video-container--hidden");
            streamingQualitySelect.innerHTML = `<option value="-1">Auto (Adaptive)</option>`;
        } else {
            streamingUrlGroup.style.display = "none";
            videoContainer.classList.add("live-video-container--hidden");
            if (hlsInstance) {
                hlsInstance.destroy();
                hlsInstance = null;
            }
            if (videoPlayer) {
                videoPlayer.pause();
                videoPlayer.removeAttribute("src");
                videoPlayer.load();
            }
            restoreSimulationQualities();
        }
    });
});

// Allow quality switching in Live mode based on stream levels
streamingQualitySelect.addEventListener("change", () => {
    if (getStreamingMode() === "live" && hlsInstance) {
        const chosen = parseInt(streamingQualitySelect.value, 10);
        hlsInstance.currentLevel = chosen;
        const label = streamingQualitySelect.options[streamingQualitySelect.selectedIndex].text;
        setStatus(`Switched live stream quality to ${label}. Next segments will adapt.`);
        addLogEntry(`Quality switch requested: ${label}`);
    }
});

streamingForm.addEventListener("submit", async (event) => {
    event.preventDefault();

    const isLive = getStreamingMode() === "live";

    if (!isLive) {
        // ---------- Simulation Mode (Unchanged, 10 deterministic events) ----------
        const quality = streamingQualitySelect.value;
        playButton.disabled = true;
        setStatus(`Starting stream at ${quality} ...`);

        try {
            const response = await fetch("/api/simulate/streaming", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ quality }),
            });

            const data = await response.json();
            if (!response.ok) {
                setStatus(data.error || "Something went wrong.", true);
                return;
            }

            addLogEntry(`Streamed at ${data.quality} (${data.events.length} protocol steps)`);
            if (activeActivity === "streaming") {
                setStatus(`Streaming simulation complete at ${data.quality} (${data.events.length} protocol steps).`);
                Visualizer.loadEvents(data.events);
            }
        } catch (err) {
            setStatus("Could not reach the server. Is the Flask app running?", true);
        } finally {
            playButton.disabled = false;
        }
        return;
    }

    // ---------- Live Mode (Real HLS playback + Lifecycle events) ----------
    const streamUrl = (streamingUrlInput.value || "").trim();
    if (!streamUrl) {
        setStatus("Please enter a valid HLS stream URL (.m3u8).", true);
        return;
    }

    if (!streamUrl.startsWith("http://") && !streamUrl.startsWith("https://")) {
        setStatus("Live streaming requires an http:// or https:// URL.", true);
        return;
    }

    let streamDomain = "";
    let streamPath = "";
    try {
        const parsed = new URL(streamUrl);
        streamDomain = parsed.hostname;
        streamPath = parsed.pathname || "/playlist.m3u8";
    } catch (e) {
        setStatus("Could not parse stream URL.", true);
        return;
    }

    playButton.disabled = true;
    setStatus(`Resolving stream host ${streamDomain} (Live) ...`);
    videoError.classList.add("live-video-error--hidden");

    if (hlsInstance) {
        hlsInstance.destroy();
        hlsInstance = null;
    }

    // Step 1: Real DNS Lookup for the streaming host via Flask
    try {
        const dnsResp = await fetch("/api/live/dns", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ url: streamUrl }),
        });

        const dnsData = await dnsResp.json();
        if (!dnsResp.ok) {
            setStatus(dnsData.error || "DNS resolution failed for streaming host.", true);
            Visualizer.reset();
            playButton.disabled = false;
            return;
        }

        addLogEntry(`Live stream DNS resolved: ${streamDomain} -> ${dnsData.events[1].fields["IP Address"]}`);

        // Seed the visualizer with the real DNS Query & Response events
        Visualizer.loadEvents(dnsData.events);

    } catch (err) {
        setStatus("Could not reach Flask backend for DNS resolution.", true);
        playButton.disabled = false;
        return;
    }

    // Step 2: Initialize real HLS playback & capture lifecycle events
    if (window.Hls && Hls.isSupported()) {
        hlsInstance = new Hls({
            enableWorker: true,
            lowLatencyMode: false,
        });

        let manifestStartTime = performance.now();

        // 2a. Manifest loading event (client -> server)
        hlsInstance.on(Hls.Events.MANIFEST_LOADING, () => {
            manifestStartTime = performance.now();
            Visualizer.appendLiveEvent({
                protocol: "HTTP",
                transport: "TCP",
                direction: "client-to-server",
                summary: "HTTP Manifest Request (Live)",
                raw: `GET ${streamPath} HTTP/1.1\nHost: ${streamDomain}\nAccept: application/vnd.apple.mpegurl, */*`,
                fields: { Method: "GET", Host: streamDomain, Type: "HLS Playlist / Manifest", URL: streamUrl },
                highlight: ["Method", "Type"],
                timing_ms: 0,
            });
            setStatus(`Fetching live HLS playlist from ${streamDomain} ...`);
        });

        // 2b. Manifest loaded event (server -> client)
        hlsInstance.on(Hls.Events.MANIFEST_PARSED, (_event, data) => {
            const duration = Math.round(performance.now() - manifestStartTime);
            const levels = data.levels || hlsInstance.levels || [];
            const levelCount = levels.length;

            // Populate quality dropdown dynamically from the master playlist
            streamingQualitySelect.innerHTML = `<option value="-1">Auto (Adaptive)</option>`;
            levels.forEach((lvl, idx) => {
                const opt = document.createElement("option");
                opt.value = String(idx);
                const res = lvl.height ? `${lvl.height}p` : `${Math.round(lvl.bitrate / 1000)}k`;
                opt.textContent = `${res} (${Math.round(lvl.bitrate / 1000)} kbps)`;
                streamingQualitySelect.appendChild(opt);
            });

            Visualizer.appendLiveEvent({
                protocol: "HTTP",
                transport: "TCP",
                direction: "server-to-client",
                summary: "HTTP Manifest Response (Live)",
                raw: `HTTP/1.1 200 OK\nContent-Type: application/vnd.apple.mpegurl\nStreams: ${levelCount} bitrate levels`,
                fields: {
                    Status: "200 OK",
                    Type: "HLS Playlist",
                    "Bitrate Levels": `${levelCount} qualities detected`,
                    "Fetch Time (ms)": String(duration),
                },
                highlight: ["Status", "Bitrate Levels"],
                timing_ms: duration,
            });

            setStatus(`Live HLS stream playing \u2014 ${streamDomain} (${levelCount} quality levels available).`);
            addLogEntry(`Live HLS manifest parsed: ${levelCount} quality levels`);

            videoPlayer.play().catch(() => {
                // Autoplay restrictions may require explicit user click on video controls
            });
        });

        // 2c. Segment request event (client -> server)
        hlsInstance.on(Hls.Events.FRAG_LOADING, (_event, data) => {
            data.frag._reqTime = performance.now();
            let fragPath = data.frag.url;
            try {
                fragPath = new URL(data.frag.url, streamUrl).pathname;
            } catch (e) {}

            const currentLvl = hlsInstance.levels ? hlsInstance.levels[hlsInstance.currentLevel] : null;
            const qualityLabel = currentLvl && currentLvl.height ? `${currentLvl.height}p` : "Adaptive";

            Visualizer.appendLiveEvent({
                protocol: "HTTP",
                transport: "TCP",
                direction: "client-to-server",
                summary: `HTTP Segment Request (Live - ${qualityLabel})`,
                raw: `GET ${fragPath} HTTP/1.1\nHost: ${streamDomain}\nAccept: video/mp2t, video/mp4, */*`,
                fields: {
                    Method: "GET",
                    Type: "Media Segment",
                    "Segment SN": String(data.frag.sn),
                    Quality: qualityLabel,
                },
                highlight: ["Method", "Segment SN"],
                timing_ms: 0,
            });
        });

        // 2d. Segment response event (server -> client)
        hlsInstance.on(Hls.Events.FRAG_LOADED, (_event, data) => {
            const loadDuration = data.frag._reqTime ? Math.round(performance.now() - data.frag._reqTime) : 35;
            const currentLvl = hlsInstance.levels ? hlsInstance.levels[hlsInstance.currentLevel] : null;
            const qualityLabel = currentLvl && currentLvl.height ? `${currentLvl.height}p` : "Adaptive";
            const bytesLoaded = data.stats && data.stats.total ? `${Math.round(data.stats.total / 1024)} KB` : "chunk";
            const segDuration = data.frag.duration ? `${data.frag.duration.toFixed(1)}s` : "media";

            Visualizer.appendLiveEvent({
                protocol: "HTTP",
                transport: "TCP",
                direction: "server-to-client",
                summary: `HTTP Segment Response (Live - ${qualityLabel})`,
                raw: `HTTP/1.1 200 OK\nContent-Type: video/mp2t\nBytes: ${bytesLoaded}\nDuration: ${segDuration}`,
                fields: {
                    Status: "200 OK",
                    "Segment SN": String(data.frag.sn),
                    "Payload Size": bytesLoaded,
                    "Segment Duration": segDuration,
                    "Fetch Time (ms)": String(loadDuration),
                },
                highlight: ["Status"],
                timing_ms: loadDuration,
            });

            addLogEntry(`Live segment ${data.frag.sn} received (${qualityLabel}, ${bytesLoaded})`);
        });

        // 2e. Error handling (CORS / unreachable / media error)
        hlsInstance.on(Hls.Events.ERROR, (_event, data) => {
            if (data.fatal) {
                let errorMsg = "Streaming error encountered.";
                if (data.type === Hls.ErrorTypes.NETWORK_ERROR) {
                    errorMsg = "Network error: stream unreachable or CORS blocked by remote streaming host.";
                } else if (data.type === Hls.ErrorTypes.MEDIA_ERROR) {
                    errorMsg = "Media error: player unable to decode video stream.";
                }
                setStatus(errorMsg, true);
                videoError.textContent = `${errorMsg} (Please check stream URL & ensure CORS headers are allowed).`;
                videoError.classList.remove("live-video-error--hidden");
                addLogEntry(`Streaming error: ${errorMsg}`);
            }
        });

        hlsInstance.loadSource(streamUrl);
        hlsInstance.attachMedia(videoPlayer);

    } else if (videoPlayer.canPlayType("application/vnd.apple.mpegurl")) {
        // Native HLS support (Safari / iOS)
        videoPlayer.src = streamUrl;
        videoPlayer.play().catch(() => {});
        setStatus(`Live HLS stream started via native browser engine: ${streamDomain}`);
    } else {
        setStatus("HLS playback is not supported in this browser without HLS.js library.", true);
    }

    playButton.disabled = false;
});

// ---------------------------------------------------------------
// Flow Control Activity (Stop-and-Wait and Stop-and-Wait ARQ)
// ---------------------------------------------------------------
const flowControlForm = document.getElementById("flow-control-form");
const flowVariantSaw = document.getElementById("flow-variant-stop-and-wait");
const flowVariantArq = document.getElementById("flow-variant-stop-and-wait-arq");
const flowFrameCount = document.getElementById("flow-frame-count");
const flowArqScenario = document.getElementById("flow-arq-scenario");
const flowArqScenarioGroup = document.getElementById("flow-arq-scenario-group");
const flowControlSubmit = document.getElementById("flow-control-submit");

function getFlowVariant() {
    const checked = document.querySelector('input[name="flow-variant"]:checked');
    return checked ? checked.value : "stop-and-wait";
}

function updateFlowScenarioVisibility() {
    const variant = getFlowVariant();
    const isArq = variant === "stop-and-wait-arq";
    if (flowArqScenarioGroup) {
        flowArqScenarioGroup.style.display = isArq ? "block" : "none";
    }
    if (flowArqScenario) {
        flowArqScenario.disabled = !isArq;
    }
}

if (flowVariantSaw) {
    flowVariantSaw.addEventListener("change", updateFlowScenarioVisibility);
}
if (flowVariantArq) {
    flowVariantArq.addEventListener("change", updateFlowScenarioVisibility);
}
updateFlowScenarioVisibility();

if (flowControlForm) {
    flowControlForm.addEventListener("submit", async (event) => {
        event.preventDefault();

        const variant = getFlowVariant();
        const frameCount = parseInt(flowFrameCount.value, 10) || 4;
        const scenario = variant === "stop-and-wait-arq" ? flowArqScenario.value : "normal";

        flowControlSubmit.disabled = true;
        const variantLabel = variant === "stop-and-wait-arq" ? `Stop-and-Wait ARQ (${scenario})` : "Stop-and-Wait";
        setStatus(`Simulating ${variantLabel} with ${frameCount} frames...`);
        addLogEntry(`Flow Control: starting ${variant} simulation (${frameCount} frames, scenario: ${scenario})`);

        try {
            const response = await fetch("/api/simulate/flow-control", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    variant: variant,
                    frame_count: frameCount,
                    scenario: scenario,
                }),
            });

            const data = await response.json();

            if (!response.ok) {
                const errMsg = data.error || "Flow control simulation failed.";
                setStatus(errMsg, true);
                addLogEntry(`Error: ${errMsg}`);
                return;
            }

            addLogEntry(`Flow Control: received ${data.events.length} events for ${data.variant}`);
            if (activeActivity === "flow-control" || activeActivity === "flowControl") {
                setStatus(`Flow control simulation complete \u2014 ${variantLabel} (${data.events.length} steps).`);
                Visualizer.loadEvents(data.events);
            }
        } catch (err) {
            setStatus("Could not reach the server. Is the Flask app running?", true);
            addLogEntry(`Error: Could not reach the server.`);
        } finally {
            flowControlSubmit.disabled = false;
        }
    });
}
