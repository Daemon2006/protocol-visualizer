# Requirements Checklist (Traceability to the Assignment PDF)

This maps every major requirement from the professor's assignment
specification to where it is implemented and how it was verified.
No grade or score is claimed here — only factual coverage.

| # | Requirement (from assignment PDF) | Where implemented | Verification status | Notes |
|---|---|---|---|---|
| 1 | Dual-panel layout, exactly two main panels | `templates/index.html` (`.panel--activity`, `.panel--protocol`), `static/css/style.css` (`.dashboard` grid) | **Verified** — automated check confirms exactly two `<section class="panel...">` elements | No third panel added for Streaming; activity switching uses tabs inside the left panel |
| 2 | Left = Activity Panel | `templates/index.html` left `<section>` | **Verified** | Contains the tab selector + all three forms |
| 3 | Right = Protocol Visualization Panel | `templates/index.html` right `<section>` | **Verified** | Contains step indicator, event display, playback controls |
| 4 | Side-by-side on desktop, stacked on small screens | `static/css/style.css` `.dashboard` grid + `@media (max-width: 800px)` | **Verified (code-level)** — media query confirmed present and unmodified | Actual responsive rendering needs a manual browser resize check |
| 5 | Browsing: URL input + Visit | `templates/index.html` `#browsing-form`, `static/js/activity_panel.js` | **Verified** | |
| 6 | Browsing: simulate DNS query/response | `simulators/dns_sim.py` | **Verified** — deterministic query/response pair confirmed by direct test | Not a real DNS lookup, as permitted |
| 7 | Browsing: simulate HTTP request/response | `simulators/http_sim.py` | **Verified** — GET request + 200/404 response confirmed by direct test | |
| 8 | Mail: To/Subject/Body + Send | `templates/index.html` `#mail-form`, `static/js/activity_panel.js` | **Verified** | |
| 9 | Mail: SMTP conversation (EHLO, MAIL FROM, RCPT TO, DATA, QUIT + responses) | `simulators/smtp_sim.py` | **Verified** — all 15 events confirmed in correct order with correct reply codes (220/250/354/221) | DNS/MX lookup included (optional per spec, implemented) |
| 10 | Mail: no HTTP messages in the SMTP exchange | `simulators/smtp_sim.py` | **Verified** — automated check confirms every Mail event's protocol is `DNS` or `SMTP`, never `HTTP` | |
| 11 | Streaming: Play control + quality selector (360p/720p/1080p) | `templates/index.html` `#streaming-form`, `static/js/activity_panel.js` | **Verified** | |
| 12 | Streaming: DNS query/response | `simulators/streaming_sim.py` | **Verified** | |
| 13 | Streaming: HTTP manifest/playlist request + response | `simulators/streaming_sim.py` | **Verified** — response body is a real `#EXTM3U` HLS playlist format | |
| 14 | Streaming: multiple HTTP segment request/response pairs | `simulators/streaming_sim.py` | **Verified** — 3 segment pairs confirmed | |
| 15 | Streaming: quality affects simulated resource paths | `simulators/streaming_sim.py` (`/video/{quality}/...`) | **Verified** — automated check confirms manifest/segment paths change for 360p/720p/1080p | |
| 16 | Streaming: segments represented as HTTP, not a separate protocol | `simulators/streaming_sim.py` | **Verified** — automated check confirms every Streaming event's protocol is `DNS` or `HTTP`, never a custom "STREAMING" value | |
| 17 | For each protocol: exact messages, direction, sequence/timing, key fields highlighted | Shared event schema (`protocol`, `direction`, `raw`, `fields`, `highlight`, `timing_ms`, `step`), rendered by `static/js/visualizer.js` | **Verified** | Same schema used by all three activities |
| 18 | Progressive/animated reveal, one event at a time | `static/js/visualizer.js` (`showCurrentEvent`, auto-advance timer) | **Verified (code-level)** | Visual confirmation needs a manual browser check |
| 19 | Pause / step forward / step backward / replay controls | `static/js/visualizer.js` (`togglePause`, `goNext`, `goPrevious`, `replay`) | **Verified (code-level)** — bounds-checking traced and confirmed correct | Interactive confirmation needs a manual browser check |
| 20 | Left-panel action drives right-panel visualization in real time | Shared fetch → Flask → simulator → `Visualizer.loadEvents()` pipeline | **Verified** | |
| 21 | Simulation is acceptable; real sockets optional extra credit | All four simulator modules + `live/` package (`dns_live.py`, `http_live.py`, `smtp_live.py`) | **Verified & Extended** | Simulation mode 100% complete and verified; Optional Live Extension fully implemented for Browsing (real DNS + HTTP + preview), Mail (real authenticated SMTP), and Streaming (real HLS playback + lifecycle events) |
| 22 | Preferred stack: Python + Flask + HTML/JS | `app.py`, `templates/`, `static/` | **Verified** | Vanilla JS only, no frontend framework |
| 23 | Working dashboard + source code + run instructions | Whole project + `README.md` | **Verified** | |
| 24 | AI usage log/artifacts (platform, model, prompts, iteration) | `docs/ai_usage_log.md` | **Verified** | Covers planning phase through Phase 5 |
| 25 | 2–4 minute demo video or screenshots, all three activities + right-panel updates | `docs/demo_script.md`, `docs/evidence_checklist.md` | **Prepared, not yet recorded** | Recording/capturing is a manual step for the student |
| 26 | Reflection: AI platform/model chosen and why | `docs/reflection.md` §1 | **Verified** | |
| 27 | Reflection: how the two panels stay synchronized | `docs/reflection.md` §2 | **Verified** | |
| 28 | Reflection: what AI got wrong and how corrected | `docs/reflection.md` §3 | **Verified** | References the stale-ZIP issue, the escaping fix, and the two synchronization fixes |
| 29 | Reflection: differences between DNS+HTTP, SMTP, and streaming HTTP flows | `docs/reflection.md` §4 | **Verified** | |

## Grading-criteria cross-reference (informational only, no score claimed)

The PDF's evaluation section weights four areas. This project's
coverage against each, factually:

- **Dual-panel layout + live synchronization (35%):** implemented and
  verified as rows 1–4 and 17–20 above.
- **DNS/HTTP/SMTP message accuracy (25%):** implemented and verified
  as rows 5–16 above; all four simulators passed a dedicated
  protocol-accuracy audit with no corrections needed.
- **Effective use of AI platform (25%):** documented in
  `docs/ai_usage_log.md` (prompt history, iteration, corrections) and
  `docs/reflection.md` §1 and §3.
- **Code quality, UI polish, reflection document (15%):** a dedicated
  code-quality pass (dead code, unused CSS, stale comments, syntax)
  was performed in Phase 4 and re-checked in Phase 5 with no further
  issues found; `docs/reflection.md` addresses all four required
  points.
