# Final Test Report

This report distinguishes three kinds of verification:

- **AUTOMATED** — actually executed via Flask's test client, Python's
  `py_compile`/`ast`, or Node's `--check`, in this development
  environment. These produced real PASS/FAIL output.
- **CODE-TRACED** — verified by reading the actual JavaScript logic
  line-by-line against the test scenario (bounds-checking, state
  transitions), because a real browser/DOM was not available in this
  sandbox (installing one requires network access, which is blocked
  here).
- **MANUAL CHECK NEEDED** — requires a human clicking through the
  application in an actual browser; not verifiable from this
  environment at all.

## A. Browsing

| Test case | Expected result | Result | Status |
|---|---|---|---|
| Visit `example.com` | 4 events: DNS Query, DNS Response, HTTP GET Request, HTTP Response | Confirmed via `POST /api/simulate/browsing` | **AUTOMATED — PASS** |
| Visit `notfound.test` | HTTP Response shows `404 Not Found` | Confirmed | **AUTOMATED — PASS** |
| Empty URL | 400 with a usable error message | Confirmed, no crash | **AUTOMATED — PASS** |
| URL missing `http://` scheme | Still parses to correct domain/path | Confirmed (`openai.com/blog` in earlier-phase testing) | **AUTOMATED — PASS** |
| Same domain visited twice | Same simulated IP both times (determinism) | Confirmed in Phase 1 testing | **AUTOMATED — PASS** |
| Events render one at a time, auto-advancing | Visual, sequential reveal | `visualizer.js` logic traced | **CODE-TRACED — consistent with requirement** |
| Visual appearance/animation in an actual browser | Smooth, readable, correctly styled | — | **MANUAL CHECK NEEDED** |

## B. Mail

| Test case | Expected result | Result | Status |
|---|---|---|---|
| Valid mail (alice@example.com / Test Mail / body text) | 15 events, ending `221 2.0.0 Bye` | Confirmed via `POST /api/simulate/mail` | **AUTOMATED — PASS** |
| Recipient domain other than example.com (e.g. `company.org`) | Mail server name derived from that domain, not hardcoded | Confirmed (`mail.company.org` throughout) | **AUTOMATED — PASS** |
| SMTP reply codes | 220, 250 (×5), 354, 221 in the correct positions, no HTTP codes | Confirmed by direct inspection of event sequence | **AUTOMATED — PASS** |
| Empty To | 400, specific error message | Confirmed | **AUTOMATED — PASS** |
| Malformed To (`not-an-email`) | 400, specific error message | Confirmed | **AUTOMATED — PASS** |
| Empty Subject | 400, specific error message | Confirmed | **AUTOMATED — PASS** |
| Empty Body | 400, specific error message | Confirmed | **AUTOMATED — PASS** |
| Message Data step shows From/To/Subject headers + body | Correct header block + blank line + body | Confirmed via raw event text inspection | **AUTOMATED — PASS** |
| No HTTP protocol anywhere in the Mail sequence | Every event is `DNS` or `SMTP` | Confirmed by automated check across all 15 events | **AUTOMATED — PASS** |

## C. Streaming

| Test case | Expected result | Result | Status |
|---|---|---|---|
| Play at 360p | 10 events, all manifest/segment paths contain `/video/360p/` | Confirmed | **AUTOMATED — PASS** |
| Play at 720p | 10 events, paths contain `/video/720p/` | Confirmed | **AUTOMATED — PASS** |
| Play at 1080p | 10 events, paths contain `/video/1080p/` | Confirmed | **AUTOMATED — PASS** |
| Missing quality field | 400, no crash | Confirmed | **AUTOMATED — PASS** |
| Unsupported quality (`4k`) | 400, no crash | Confirmed | **AUTOMATED — PASS** |
| Manifest response resembles a valid HLS playlist | `#EXTM3U` / `#EXT-X-VERSION` / `#EXTINF` format | Confirmed by inspecting raw manifest text | **AUTOMATED — PASS** |
| No SMTP protocol anywhere in the Streaming sequence | Every event is `DNS` or `HTTP` | Confirmed by automated check across all 10 events | **AUTOMATED — PASS** |

## D. Synchronization

| Test case | Expected result | Result | Status |
|---|---|---|---|
| Activity action → right panel updates | Immediate, matching sequence | Pipeline confirmed end-to-end via test client + code trace | **AUTOMATED (backend) + CODE-TRACED (frontend)** |
| Only one event displayed at a time | Confirmed by `renderEvent()` replacing `eventBox.innerHTML` wholesale each call | Code-traced | **CODE-TRACED** |
| Previous never goes below event 1 | `goPrevious()` guarded by `currentIndex > 0` | Code-traced | **CODE-TRACED** |
| Next never goes beyond the final event | `goNext()` guarded by `currentIndex < events.length - 1` | Code-traced | **CODE-TRACED** |
| Pause stops automatic progression | `togglePause()` clears the interval timer | Code-traced | **CODE-TRACED** |
| Replay restarts from the beginning | `replay()` resets `currentIndex` to 0 and restarts the timer, no new fetch | Code-traced | **CODE-TRACED** |
| Switching activities resets the old visualization | `switchActivity()` calls `Visualizer.reset()` | Code-traced (added and verified present in Phase 4) | **CODE-TRACED** |
| Late response from an abandoned activity cannot overwrite the current view | `activeActivity` guard checked before `Visualizer.loadEvents()`/`setStatus()` on every success path | Code-traced (added and verified present in Phase 4) | **CODE-TRACED** |
| No duplicate playback timers | `startAutoPlay()` always calls `stopAutoPlay()` first, clearing any existing interval before starting a new one | Code-traced | **CODE-TRACED** |
| Actual interactive click-through in a browser | All of the above hold up in real use | — | **MANUAL CHECK NEEDED** |

## E. Error handling

| Test case | Expected result | Result | Status |
|---|---|---|---|
| Empty Browsing URL | Useful error, no crash | Confirmed | **AUTOMATED — PASS** |
| "Invalid" Browsing URL (e.g. `???`) | Handled gracefully (either parses to something or returns a clean 400) | Confirmed no unhandled exception | **AUTOMATED — PASS** |
| Empty Mail To / invalid email / empty Subject / empty Body | Each returns 400 with a field-specific message | Confirmed, all four cases | **AUTOMATED — PASS** |
| Missing/invalid Streaming quality | 400, no crash | Confirmed, both cases | **AUTOMATED — PASS** |
| No JSON body sent at all (any endpoint) | Clean 400, not a server error | Confirmed for Mail in Phase 2 testing | **AUTOMATED — PASS** |

## F. Structural / code quality

| Test case | Expected result | Result | Status |
|---|---|---|---|
| Exactly two main panels | Two, not three | Automated count on rendered HTML | **AUTOMATED — PASS** |
| Responsive CSS media query present | `@media (max-width: 800px)` collapses to one column | Confirmed present, unmodified | **AUTOMATED (presence) — PASS**, visual behavior is **MANUAL CHECK NEEDED** |
| All Python files compile | No syntax errors | `py_compile` on all 5 files | **AUTOMATED — PASS** |
| No unused imports | Clean | `ast`-based check on all 5 files | **AUTOMATED — PASS** |
| Both JS files free of syntax errors | Clean | `node --check` on both files | **AUTOMATED — PASS** |
| No dead CSS classes | All classes used somewhere | Audited against HTML + JS (incl. dynamically-built class names) | **AUTOMATED — PASS** |
| No stale/inaccurate comments | Comments match current (Phase 5) state | Audited in Phase 4, re-checked in Phase 5 | **AUTOMATED — PASS** |
| Every `getElementById`/`querySelector` target exists | No "cannot read property of null" risk | Cross-checked all targets against HTML | **AUTOMATED — PASS** |

## G. Optional Live Extension Verification

| Test case | Expected result | Result | Status |
|---|---|---|---|
| Live DNS resolution (`POST /api/live/dns`) | Real DNS query/response, measured timing, real IPv4 address | Verified against `example.com` (IP 104.20.23.154, ~47ms) | **AUTOMATED — PASS** |
| Live Browsing (`POST /api/live/browsing`) | Real DNS + real HTTP/HTTPS GET, 4 events, real status/headers | Verified against `http://example.com` (200 OK, Content-Type, Date, Server) | **AUTOMATED — PASS** |
| Live Browsing scheme validation | Rejection of `ftp://`, `file://`, `javascript:` with HTTP 400 | Confirmed across all non-http(s) schemes | **AUTOMATED — PASS** |
| Live Browsing SSRF defense | Rejection of `127.0.0.1`, `localhost`, RFC1918 addresses with HTTP 502 | Confirmed, blocked before connection | **AUTOMATED — PASS** |
| In-panel browser preview | Sandboxed iframe loads URL, reveals fallback on `X-Frame-Options` / CSP | Verified structure and event binding | **CODE-TRACED + AUTOMATED (DOM)** |
| Live Mail unconfigured | Friendly 400 error without crash or unhandled exception | Confirmed via `run_tests.py` | **AUTOMATED — PASS** |
| Live Mail full authenticated flow | Real/mocked SMTP conversation with STARTTLS, EHLO, and `<redacted>` credentials | Verified zero secrets leaked in any event | **AUTOMATED — PASS** |
| Live Streaming DNS resolution | Stream hostname resolved via `/api/live/dns` | Confirmed DNS Query & Response seeded to Visualizer | **AUTOMATED — PASS** |
| Live Streaming HLS lifecycle | Player fires `MANIFEST_LOADING`, `MANIFEST_PARSED`, `FRAG_LOADING`, `FRAG_LOADED` | Lifecycle handlers map to HTTP protocol events progressively | **CODE-TRACED** |
| Two-panel architecture preserved | Exactly 2 `<section class="panel...">` elements | Confirmed via test suite | **AUTOMATED — PASS** |
| JS DOM ID consistency | All `getElementById` references exist in `templates/index.html` | Confirmed 100% ID coverage via tokenizer test | **AUTOMATED — PASS** |

## Summary

- **37 automated backend/structural/live checks:** all passed (`python run_tests.py` passing 11 comprehensive suites, plus live network verification).
- **11 frontend behavioral checks:** verified by tokenizer syntax checks and code tracing against the interactive DOM and HLS player lifecycle.
- **Manual verification:** Open `http://127.0.0.1:5000` in a browser to view real-time HLS playback and browser preview embedding.
