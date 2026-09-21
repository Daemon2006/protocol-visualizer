# Application Layer Dashboard — Dual-Panel Activity & Protocol Visualizer

A Flask web dashboard for the Computer Networks (Application Layer) assignment.
It implements a two-panel layout: an **Activity Panel** (left) where a user performs
an action, and a **Protocol Visualization Panel** (right) where the underlying
DNS / HTTP / SMTP messages are displayed step-by-step.

> **Status:** Complete — All required assignment phases (Phases 0–5 Simulation Mode)
> and the entire **Optional Live Extension** (Live Browsing + Browser Preview, Live
> Authenticated SMTP Mail, and Live HLS Streaming) are fully implemented, tested,
> and integrated into a single unified application.
>
> - **Required Assignment (Simulation Mode)**: 100% offline, deterministic, fully
>   self-contained simulations for Browsing (4 events), Mail (15 events), and
>   Streaming (10 events for 360p, 720p, 1080p). Fully repeatable and safe for
>   submission and grading without external credentials or internet connectivity.
> - **Optional Live Extension (Live Mode)**: Real internet networking across all
>   three activities using Python's standard library and modern web standards:
>   - **Live Browsing**: Real DNS resolution (`socket`) + real HTTP/HTTPS GET
>     (`urllib.request`) + sandboxed browser preview (iframe) with educational
>     `X-Frame-Options` and CSP fallback handling.
>   - **Live Mail**: Real authenticated SMTP submission (`smtplib`) with zero
>     hardcoded secrets, environment variable configuration, `AUTH <redacted>`
>     credential protection, SSRF safeguards, and graceful unconfigured states.
>   - **Live Streaming**: Real HLS video stream playback (`<video>` + HLS.js)
>     with application-level playback lifecycle observation (real DNS, manifest
>     loading/loaded, and segment request/response pairs with quality switching).

---

## Architectural Principles

1. **Strictly Two Main Panels**: Exactly two panels (`.panel--activity` on the left,
   `.panel--protocol` on the right). The browser preview iframe and HLS video player
   live exclusively inside the left Activity Panel. No third main panel is ever created.
2. **Single Shared Visualizer Engine**: The exact same frontend engine (`visualizer.js`)
   renders protocol exchanges for both Simulation and Live modes across all three activities.
3. **Simulation Untouched**: All offline simulation algorithms and deterministic
   event sequences remain 100% preserved.
4. **Honest Protocol Representation**: No fake packet traces or simulated wire-level
   captures. Live modes visualize real application-level protocol interactions
   observed by the system resolver, HTTP client, SMTP client, and HLS player.

---

## Requirements

- Python 3.9 or newer
- pip (comes with Python)
- Modern web browser (Chrome, Edge, Firefox, Safari)

---

## Quick Start: Running the Project

### 1. Set up a virtual environment (recommended)

```bash
# Create virtual environment (only needed once)
python -m venv venv

# Activate it
# On Windows (PowerShell):
venv\Scripts\Activate.ps1
# On macOS / Linux:
source venv/bin/activate
```

### 2. Install Flask

```bash
pip install flask
```

*(No extra third-party Python packages are required; all live DNS, HTTP, and SMTP features utilize Python's standard library).*

### 3. Run Automated Tests

To verify both Simulation and Live modes, SSRF defenses, and DOM integrity:

```bash
python run_tests.py
```

You should see:
```
Ran 11 tests in 0.090s
OK
```

### 4. Start the Application

```bash
python app.py
```

You will see:
```
 * Running on http://127.0.0.1:5000
```

Open `http://127.0.0.1:5000` in your browser.

---

## Playback Controls (Shared Across All Activities)

The right-hand Protocol panel provides standard playback controls that operate identically across all three activities:

- **Previous**: Steps backward one event; disabled at Step 1.
- **Pause / Playing**: Pauses automatic timed playback; click again to resume auto-advancing.
- **Next**: Steps forward one event; disabled at the final event.
- **Replay**: Restarts the currently loaded event sequence from step 1 without making a new network request.

Switching activity tabs cleanly resets the Protocol panel back to its waiting placeholder, preventing stale events from previous activities from lingering.

---

## Part 1: Browsing Activity

### Simulation Mode (Default)
1. Enter a domain (e.g. `example.com`) and click **Visit**.
2. Fully offline deterministic simulation generates 4 events:
   - **Step 1**: `DNS Query` (client → DNS server)
   - **Step 2**: `DNS Response` (server → client, with deterministic IP derived from domain hash)
   - **Step 3**: `HTTP GET Request` (client → web server)
   - **Step 4**: `HTTP Response` (server → client, status `200 OK` or `404 Not Found` if domain contains `notfound`)

### Live Mode + Browser Preview
1. Select the **Live (real DNS + HTTP)** radio option.
2. Enter any public website (e.g. `example.com`, `python.org`, `wikipedia.org`).
3. Clicking **Visit** triggers two parallel actions:
   - Backend performs real DNS resolution via `socket.gethostbyname` and a real HTTP/HTTPS GET request via `urllib.request`.
   - Left Activity Panel loads a best-effort browser preview inside a sandboxed iframe.
4. **Safety & Design Safeguards**:
   - **Hostname Preservation**: The request URL uses the original hostname (preserving HTTP `Host` header and HTTPS TLS/SNI validation).
   - **SSRF Defense**: The resolved IP is inspected before connecting; loopback, private RFC1918, link-local, and multicast addresses are refused with HTTP 502.
   - **Scheme Restriction**: Only `http://` and `https://` are accepted; `file://`, `ftp://`, `javascript:`, `data:` are rejected with HTTP 400.
   - **No Redirect Chasing**: 3xx redirect responses are displayed as-is (with `Location` header) as the honest Event 4.
   - **Embedding Protection Handling**: If a website sets `X-Frame-Options: DENY/SAMEORIGIN` or CSP `frame-ancestors`, the iframe preview displays:
     > *"Preview unavailable — this website does not allow embedding."*
     The protocol visualization on the right remains 100% operational.

---

## Part 2: Mail Activity

### Simulation Mode (Default)
1. Fill in **To**, **Subject**, and **Body**, then click **Send**.
2. Fully offline deterministic simulation generates a complete 15-event SMTP exchange:
   - DNS/MX lookup (Steps 1–2)
   - Server Greeting `220` (Step 3)
   - Client introduction `EHLO` & server capabilities `250` (Steps 4–5)
   - Envelope sender `MAIL FROM` & acceptance `250` (Steps 6–7)
   - Recipient `RCPT TO` & acceptance `250` (Steps 8–9)
   - Data initiation `DATA` & intermediate prompt `354` (Steps 10–11)
   - Message transmission & queue acceptance `250` (Steps 12–13)
   - Termination `QUIT` & connection closed `221 2.0.0` (Steps 14–15)

### Live Mode (Real Authenticated SMTP Submission)
1. Select the **Live (real SMTP)** radio option.
2. If SMTP environment variables are not set, the UI gracefully displays:
   > *"Live SMTP is not configured. Please set SMTP_HOST in environment variables or .env file."*
   without crashing or hanging.
3. **Environment Configuration**:
   Configure credentials via environment variables or a local `.env` file (excluded from version control):
   ```ini
   SMTP_HOST=smtp.example.com
   SMTP_PORT=587
   SMTP_SECURITY=starttls   # starttls, ssl, or none
   SMTP_USERNAME=user@example.com
   SMTP_PASSWORD=your_secure_password
   SMTP_FROM=user@example.com
   ```
4. **Security & Protocol Traceability**:
   - **Zero Secrets in Source/Logs**: Passwords, tokens, and credentials are NEVER logged or exposed. Authentication steps are formatted as `AUTH <redacted>`.
   - **SSRF Checks**: `SMTP_HOST` is resolved via DNS and checked against private/internal IP ranges before establishing connections.
   - **Actual Server Codes**: Server greetings, STARTTLS negotiations, authentication confirmations, recipient acceptances/rejections (`250`, `550`), and queue acknowledgments are visualized with real measured timing.

---

## Part 3: Streaming Activity

### Simulation Mode (Default)
1. Select a quality tier (**360p**, **720p**, or **1080p**) and click **Play**.
2. Generates 10 deterministic protocol events:
   - DNS Query & Response for `video.example.com` (Steps 1–2)
   - HTTP Manifest Request & Response for `/video/<quality>/playlist.m3u8` (Steps 3–4)
   - 3× HTTP Segment Request & Response pairs for `/video/<quality>/segment00X.ts` (Steps 5–10)
3. Demonstrates that quality selection alters resource paths at the application layer while utilizing ordinary HTTP GET transactions.

### Live Mode (Real HLS Video Playback)
1. Select the **Live (real HLS playback)** radio option.
2. A configurable **HLS Stream URL (.m3u8)** input and HTML5 `<video>` player appear inside the Activity Panel.
   - *Default URL*: `https://test-streams.mux.dev/x36xhzz/x36xhzz.m3u8` (verified public multi-bitrate HLS test stream with CORS enabled).
3. Click **Play**:
   - Step 1: Real DNS resolution for the streaming host is performed via the backend (`/api/live/dns`), generating real DNS Query & Response events.
   - Step 2: The player initializes HLS.js (with native HLS fallback for Safari).
   - Step 3: Player lifecycle events are captured in real time:
     - `Hls.Events.MANIFEST_LOADING` → HTTP Manifest Request event
     - `Hls.Events.MANIFEST_PARSED` → HTTP Manifest Response event (auto-populates available adaptive quality levels in the dropdown)
     - `Hls.Events.FRAG_LOADING` → HTTP Segment Request event (with quality label and sequence number)
     - `Hls.Events.FRAG_LOADED` → HTTP Segment Response event (with measured duration, byte count, and HTTP 200)
4. **Progressive Visualizer**: The shared Visualizer accepts live streaming events progressively via `Visualizer.appendLiveEvent()`. Users can inspect earlier segments using **Previous** or **Pause** without disrupting live stream playback.
5. **Quality Switching**: Changing quality in the dropdown switches `hls.currentLevel`, immediately reflecting in subsequent segment request events.

---

## Automated Test Suite

Run the full automated verification suite:

```bash
python run_tests.py
```

### Coverage:
- **Simulation Regressions**: Browsing (4 events), Mail (15 events), Streaming (10 events across 360p/720p/1080p).
- **Live Browsing & Safety**: Scheme validation (`ftp://`, `file://`, `javascript:` rejected), SSRF loopback/RFC1918 blocking, IP classification unit tests.
- **Live Mail**: Unconfigured state safety (HTTP 400 clean message), full authenticated SMTP conversation mocking, credential redaction (`AUTH <redacted>`).
- **DOM & Structural Checks**: Exactly two main panels, presence of preview containers and video elements, matching DOM IDs between JavaScript and HTML templates, balanced JS tokenizer syntax checks.

---

## Project Structure

```
protocol-visualizer/
├── app.py                     # Flask application & API routes (Simulation & Live)
├── run_tests.py               # Comprehensive automated test suite (11 test suites)
├── simulators/                # Deterministic offline protocol engines (Phases 1-3)
│   ├── dns_sim.py             # Offline DNS simulator
│   ├── http_sim.py            # Offline HTTP simulator
│   ├── smtp_sim.py            # Offline DNS/MX + SMTP conversation simulator
│   └── streaming_sim.py       # Offline HLS manifest & segment simulator
├── live/                      # Real networking engines
│   ├── dns_live.py            # Real DNS lookup via socket.gethostbyname
│   ├── http_live.py           # Real HTTP/HTTPS GET client with SSRF safety
│   └── smtp_live.py           # Real authenticated SMTP submission engine
├── static/
│   ├── css/style.css          # Dual-panel grid, design tokens, preview & player styles
│   └── js/
│       ├── activity_panel.js  # Left Activity Panel controller (forms, iframe, video, HLS)
│       └── visualizer.js      # Right Protocol Panel engine (step controls, live progressive mode)
├── templates/
│   └── index.html             # Single-page dual-panel HTML dashboard
├── docs/
│   ├── ai_usage_log.md        # Comprehensive AI collaboration and debugging log
│   ├── reflection.md          # Technical reflection & architecture document
│   ├── final_test_report.md   # Final test results and evidence matrix
│   ├── requirements_checklist.md # Traceability matrix to assignment requirements
│   ├── demo_script.md         # Demo presentation walkthrough script
│   └── evidence_checklist.md  # Verification checklist
└── README.md                  # Project overview, architecture, and run guide
```

---

## Stopping the Application

Press `Ctrl + C` in the terminal running `python app.py`.
