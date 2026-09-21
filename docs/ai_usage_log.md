# AI Usage Log

Platform / model used: Claude, via the claude.ai chat interface (this
session used Claude Sonnet 5).

This file is a running record of AI-assisted development, kept as required
by the assignment. Add an entry each time you prompt the AI for a new
piece of work, including corrections you had to make.

---

## Planning -- architecture design (before any code was written)

**Prompt (summary):** Uploaded the professor's assignment PDF and asked
the AI to analyze it and produce, WITHOUT writing implementation code:
a requirements checklist, recommended system architecture, project
folder structure, an explanation of how the left Activity Panel would
communicate with the right Protocol Visualization Panel, a proposed
uniform data structure for protocol events, how synchronization/
animation/playback controls should work, how each of the three
activities would be represented internally, likely AI protocol-accuracy
mistakes to guard against, a phased development plan, and a testing
plan.

**What the AI produced:** A planning document (no code) covering all of
the above. Key decisions made here and followed for the rest of the
project: a single uniform JSON event shape (`protocol`, `direction`,
`summary`, `raw`, `fields`, `highlight`, `timing_ms`, `step`) used by
every activity so one shared frontend "Visualizer Engine" could replay
any of them; a simple Flask route-per-activity backend with one
simulator module per protocol family; and a phased build order
(Browsing first as a full vertical slice, then Mail, then Streaming,
then an integration/polish pass, then final submission prep).

**Verification performed:** None yet -- no code existed at this stage.
This plan was approved by the student before Phase 0 began, and every
later phase followed it without architectural deviation.

---

## Phase 0 -- Project skeleton

**Prompt (summary):** Requested the Flask project skeleton, folder
structure, and a polished two-panel dashboard layout with placeholder
content only (no backend logic yet).

**What the AI produced:** `app.py`, `templates/index.html`,
`static/css/style.css`, empty placeholder JS files, and this docs folder.

**Corrections made:** None -- the skeleton was reviewed, run locally,
and approved as delivered before Phase 1 began.

---

## Phase 1 -- Browsing activity (DNS + HTTP)

**Status:** Completed and verified.

**Prompt (summary):** Requested the first complete end-to-end vertical
slice: the Browsing activity only. Left panel gets a URL input + Visit
button; backend gets a `/api/simulate/browsing` route backed by new
`dns_sim.py` / `http_sim.py` modules producing a deterministic 4-event
sequence (DNS Query, DNS Response, HTTP Request, HTTP Response); right
panel gets a JavaScript playback engine (Previous / Pause / Next /
Replay) that renders one event at a time without re-contacting the
backend. Mail and Streaming explicitly excluded from this phase.

**What the AI produced:** `simulators/dns_sim.py`, `simulators/http_sim.py`,
a new Flask route in `app.py`, updated `templates/index.html` (Browsing
form + protocol-event container), updated `static/css/style.css`
(form/button/protocol-event styling), and full logic in
`static/js/activity_panel.js` and `static/js/visualizer.js`.

**Verification performed:** Ran the Flask app's test client directly
(not just visual inspection) to confirm: the homepage renders the new
form elements; `POST /api/simulate/browsing` returns 4 correctly-ordered
events for a valid URL; the same domain produces the same simulated IP
address on repeated calls (determinism check); a domain containing
"notfound" returns a 404 response instead of 200; an empty URL returns
a 400 with a usable error message; a URL missing `http://` still parses
into the correct domain/path. All checks passed before delivery.

**Issue discovered and corrected:** The first ZIP delivered for Phase 1
did not actually contain the Phase 1 files (student inspected it and
found Phase 0 content). Root cause was traced to zip packaging/delivery
under a reused filename, most likely a stale cached download on the
student's side rather than missing files in the working project (the
working project directory was independently re-verified to contain all
Phase 1 files and logic at every step). Fix: rebuilt the archive under
a new filename (`protocol-visualizer-phase1-v2.zip`) and verified the
route, both simulator files, and both JS files *from inside the
rebuilt archive itself* (via `unzip -p` + grep) rather than only from
the source folder, before redelivering it. Student re-inspected and
confirmed the corrected ZIP was complete.

**Phase 1 cleanup pass:** Reviewed `visualizer.js` for unsafe `innerHTML`
use of user-influenced values (the domain/path typed into the URL box
flows into the rendered `raw` message and field values). Added a small
`escapeHtml()` helper and applied it to all user-influenced text before
inserting it into the DOM, without changing the UI or introducing a
framework. Updated `README.md` to reflect Phase 1 status, document the
`/api/simulate/browsing` endpoint, and add Phase 1 testing steps.

---

## Phase 2 -- Mail activity (DNS/MX + SMTP)

**Status:** Completed and verified.

**Prompt (summary):** Requested the Mail activity as a second complete
end-to-end vertical slice, reusing the same event-based architecture
and visualizer engine already built for Browsing. Left panel gets a
Mail form (To/Subject/Body/Send) alongside the existing Browsing form,
switched via tabs so no third panel is added; backend gets a
`/api/simulate/mail` route backed by a new `smtp_sim.py` module
producing a deterministic 15-event sequence (DNS/MX query+response,
then a full SMTP conversation: greeting, EHLO, MAIL FROM, RCPT TO,
DATA, message data, QUIT, each with its server response); the existing
visualizer engine is reused unchanged apart from adding an SMTP badge
color so DNS/SMTP are visually distinguishable. Streaming and live
networking explicitly excluded from this phase.

**What the AI produced:** `simulators/smtp_sim.py` (new), a new Flask
route + validation in `app.py`, an activity-tab selector and Mail form
added to `templates/index.html`, tab/mail styling added to
`static/css/style.css`, a rewritten `static/js/activity_panel.js`
(tab-switching plus a Mail submit handler alongside the existing
Browsing handler), and one small addition to `static/js/visualizer.js`
(a `badgeClassFor()` helper so SMTP gets its own badge color instead of
falling into the HTTP branch). Updated `README.md` and this log.

**Verification performed:** Ran the Flask test client directly to
confirm: the homepage renders all Phase 1 *and* Phase 2 elements (tabs,
mail form fields, existing browsing form, playback controls); a direct
unit test of `simulate_mail()` (no Flask involved) confirms exactly 15
events in the correct order, the mail server name is derived from the
actual recipient domain (tested with a non-"example.com" domain,
`company.org`, to rule out a hardcoded value), and the raw SMTP text
matches the required commands/codes exactly; `POST /api/simulate/mail`
returns 200 with 15 events for valid input, and 400 with a specific,
field-appropriate error message for empty To, empty Subject, empty
Body, and a malformed (non-email-shaped) To address; `POST
/api/simulate/browsing` was re-tested afterward and still returns the
same 4-event DNS+HTTP sequence as before, confirming Phase 1 was not
broken. Both JS files were also checked with `node --check` to catch
any syntax errors before manual browser testing.

**Corrections/issues discovered:** None required after implementation —
initial design and validation logic matched the required SMTP sequence
and response codes on first test. (See the Phase 1 entry above for the
earlier stale-ZIP delivery issue, which does not recur here since this
phase's ZIP will again be verified from inside the archive before
delivery.)

---

## Phase 3 -- Streaming activity (DNS + HTTP manifest/segments)

**Status:** Completed and verified.

**Prompt (summary):** Requested Streaming as the third activity, reusing
the same event-based architecture and shared visualizer engine already
used for Browsing and Mail. Left panel gets a Streaming form (quality
selector + Play button) added as a third tab, alongside Browsing and
Mail; backend gets a `/api/simulate/streaming` route backed by a new
`streaming_sim.py` module producing a deterministic 10-event sequence
(DNS query+response for a fixed simulated host, one HTTP manifest/
playlist request+response, then 3 HTTP segment request+response pairs);
the quality selector ("360p"/"720p"/"1080p") changes every requested
resource path but nothing else. Explicitly instructed not to invent a
"STREAMING" protocol -- only DNS and HTTP appear, matching how HLS
streaming actually works at the application layer. `visualizer.js` was
explicitly *not* to be rewritten; only a small protocol-badge addition
was needed there back in Phase 2 for SMTP, and Streaming needed no
further changes to it at all. Live networking, real video playback,
and adaptive bitrate streaming were explicitly excluded.

**What the AI produced:** `simulators/streaming_sim.py` (new), a new
Flask route + quality validation in `app.py`, a third activity tab and
Streaming form (quality `<select>` + Play button) added to
`templates/index.html`, a small CSS addition so `<select>` elements
match the existing input/textarea styling, a Streaming submit handler
added to `static/js/activity_panel.js` alongside the untouched
Browsing/Mail handlers. `static/js/visualizer.js` was left completely
unmodified this phase, as instructed. Updated `README.md` and this log.

**Verification performed:** Ran the Flask test client to confirm: the
homepage renders all Phase 1 + 2 + 3 elements simultaneously (tabs,
all three forms, shared playback controls); `POST
/api/simulate/streaming` returns exactly 10 events for each of
`360p`/`720p`/`1080p`, with the manifest and segment-1 request paths
each containing the correct quality string (`/video/360p/...`,
`/video/720p/...`, `/video/1080p/...`) -- confirming quality actually
changes the simulated resource paths, not just a label; an unsupported
quality value (`"4k"`) and a missing `quality` field both return 400
with a clear error listing the supported options, without raising an
exception. Browsing was re-tested and still returns exactly 4 events;
Mail was re-tested and still returns exactly 15 events -- both
confirming Phases 1 and 2 were not broken by this change. Both JS
files were checked with `node --check` for syntax errors.

**Design decision / deviation from the example Activity Log text:** The
prompt's example Activity Log showed several separate lines appearing
progressively ("DNS lookup completed", "Manifest loaded", "Segment 1
loaded", ...). Implementing that literally would require the shared
`visualizer.js` engine to call back into `activity_panel.js` as each
event is *displayed* (not just when it's *fetched*), which would mean
modifying the shared visualizer -- explicitly out of scope for this
phase ("Do NOT rewrite the shared visualizer unnecessarily," and
`visualizer.js` was not listed among the expected files to modify).
Instead, Streaming logs a single concise line after the fetch succeeds
(e.g. "Streamed at 720p (10 protocol steps)"), matching the exact
one-line-per-action convention Browsing and Mail already use. This
keeps the log honest (it doesn't claim segments are "loaded" before
the visualizer has actually shown them) and keeps the architecture
unchanged.

**Corrections/issues discovered:** None required after implementation —
all test cases passed on first run.

---

## Phase 4 -- Integration, polish, UX, and synchronization audit

**Status:** Completed and verified.

**Prompt (summary):** Requested a read-only inspection of every file
first, followed by ONLY genuinely necessary integration/polish fixes
across all three completed activities (no new features, no simulator
rewrites unless a real protocol-accuracy bug was found). Explicit focus
areas: activity-tab clarity, synchronization between activity actions
and the shared visualizer, consistent status wording, playback-control
correctness across all three activities, responsive layout, protocol
accuracy audit, and basic accessibility -- all without rewriting the
architecture, the event schema, or the shared visualizer's core logic.

**Inspection performed first (before any changes):** Read `index.html`,
`style.css`, `activity_panel.js`, `visualizer.js`, `app.py`, and all
four simulator modules (`dns_sim.py`, `http_sim.py`, `smtp_sim.py`,
`streaming_sim.py`) in full. All four simulators were confirmed
protocol-accurate on inspection (correct SMTP reply codes, no
HTTP-as-SMTP or SMTP-as-HTTP mixups, Streaming correctly uses only
DNS+HTTP with no invented "STREAMING" protocol) -- none were modified.
`app.py`'s three routes and validation logic were confirmed correct
and were not modified.

**Genuine issues found and fixed:**
1. Stale comments left over from earlier phases (`index.html` said
   "two .activity-form-panel blocks" after Streaming had made it
   three; `activity_panel.js`'s header comment still described "BOTH
   activities" from Phase 1/2; `style.css` still labeled the tab
   section "Phase 2: choosing Browsing vs Mail") -- corrected to
   reflect all three activities.
2. Dead CSS: `.placeholder-box` (a Phase 0 leftover) was no longer
   referenced anywhere in the HTML after Phase 1 replaced it -- removed.
3. A genuine synchronization gap: if a person submitted an activity
   and then switched tabs *before* the fetch() resolved, the late
   response would still call `Visualizer.loadEvents()` and overwrite
   whatever the person was now looking at. Fixed with the smallest
   possible change: an `activeActivity` variable set on every tab
   switch, checked before the visualizer/status are updated on a
   successful response (the Activity Log entry is still recorded
   either way, since it's a factual record of what happened).
4. Switching tabs without submitting a new activity left the previous
   activity's last event and enabled Previous/Next/Replay buttons
   visible in the Protocol panel -- confusing, since the buttons
   would operate on the wrong activity's data. Fixed by adding one
   small public method to the shared visualizer, `Visualizer.reset()`
   (clears events, stops any timer, restores the placeholder, disables
   all four buttons), called on every tab switch. This is an addition,
   not a rewrite -- `loadEvents()` and all playback logic are untouched.
5. Status message wording was inconsistent in shape across the three
   activities -- unified to "{Activity} simulation complete -- ...
   ({N} protocol steps)." for all three.
6. Disabled playback buttons looked too similar to enabled ones --
   added `opacity: 0.5` or visual toggle so disabled state is clearly
   distinguishable, satisfying the assignment's basic-accessibility
   guidance.
7. Added a minimal ARIA tab pattern (`role="tab"`, `aria-selected`,
   `aria-controls` on the tab buttons; `role="tabpanel"` +
   `aria-labelledby` on each form panel) so screen readers announce
   which activity is currently selected -- no new dependency, no
   framework, plain HTML attributes only.

**Verification performed:** Re-ran the full backend regression suite
(Browsing 4 events incl. 404 case, Mail 15 events incl. all four
invalid-input cases, Streaming 10 events for 360p/720p/1080p incl.
invalid-quality case) -- all passed unchanged. Confirmed exactly two
`<section class="panel...">` elements remain (the two-panel
requirement). Cross-checked every `getElementById()`/`querySelector()`
target used in both JS files against the actual HTML to rule out
"Cannot read property of null" console errors from a missing element --
none found. Syntax-checked both JS files with `node --check`. Manually
traced the tab-switch, playback-control bounds-checking, and
late-response-guard logic against the requested test scenarios line by
line, since a real browser/DOM environment was not available in this
sandbox (network access for installing a headless-DOM test tool was
blocked) -- the student is asked to do a final visual/interactive pass
locally in VS Code to confirm, as with every previous phase.

**Corrections/issues discovered:** The six items listed above were the
only genuine issues found; everything else inspected (the two-panel
grid layout, all four simulators, `app.py`'s routes and validation,
the core playback bounds-checking in `visualizer.js`) was already
correct and was deliberately left unchanged.

---

## Phase 5 -- Final verification and submission readiness

**Status:** Completed.

**Prompt (summary):** Requested a final read-only-first audit against
the professor's PDF as the source of truth, a code-quality pass (dead
code, unused CSS, stale comments, duplicate logic, syntax), a full
regression across all three activities and error cases, and creation
of the remaining submission artifacts: a polished `docs/reflection.md`,
`docs/demo_script.md`, `docs/evidence_checklist.md`,
`docs/requirements_checklist.md`, and `docs/final_test_report.md`. No
new features, no Live Mode, no architecture changes.

**Code-quality audit performed:** Checked every CSS class defined in
`style.css` against actual usage in `index.html`/the JS files (one
apparent false positive, `protocol-message--client-to-server`, was
confirmed genuinely used -- it's built dynamically in `visualizer.js`
via a template literal, `protocol-message--${event.direction}`, so a
plain-text search couldn't see it). Compiled all five Python files with
`py_compile` and checked for unused imports via `ast` -- all clean.
Syntax-checked both JS files with `node --check`. No further stale
comments or dead code were found beyond what Phase 4 had already fixed.
Also found and fixed two small documentation gaps: this log's very
first planning conversation (before Phase 0) had never been recorded,
and `README.md` had no consolidated "Assumptions" section even though
several were mentioned scattered across individual phase writeups.

**Verification performed:** Re-ran the full backend regression as a
single structured suite (26 checks covering all three activities'
happy paths, protocol-composition checks, every documented invalid-
input case, and the two-panel/ARIA structural checks) -- all 26 passed.

**Corrections/issues discovered:** No functional bugs. Two documentation
gaps (noted above) were the only findings, and both were corrected.

**Known limitation carried forward:** As in Phase 4, this sandbox has no
real browser or headless-DOM tool available (installing one requires
network access, which is blocked here), so interactive browser
behavior (tab clicks, playback button clicks) is verified by direct
code tracing and Flask-level testing, not live browser execution. The
student should do a final manual click-through locally as the
definitive check, per the demo script below.

---

## Live Phase 1 -- Real DNS resolution (optional, post-submission add-on)

**Status:** Completed.

**Objective:** With the required Simulation-mode assignment (Phases
0-5) already complete, approved, and backed up separately, add an
*optional* Live mode to the Browsing activity that performs one real
network operation -- an actual DNS resolution -- while leaving every
existing Simulation-mode feature (Browsing, Mail, Streaming) completely
unchanged. Explicitly scoped to DNS only: no Live HTTP/HTTPS, SMTP,
Streaming, WebSockets, authentication, or deployment.

**Prompt/approach:** Requested a small Simulation/Live selector on the
Browsing form, a new `POST /api/live/dns` Flask route, and a real DNS
lookup via Python's standard library only (no new dependencies),
returning events in the exact same schema the shared Visualizer Engine
already renders. Honesty was an explicit requirement: the Live events
must not invent packet-level detail (transaction IDs, TTL, which DNS
server answered) that Python's `socket` module cannot actually observe,
and any timing shown must be genuinely measured, not fabricated.

**Files changed:**
- `live/__init__.py`, `live/dns_live.py` (new) -- `resolve_domain()`
  performs the real lookup via `socket.gethostbyname()` and measures
  actual elapsed time with `time.perf_counter()`; `build_live_dns_events()`
  turns that into the two-event DNS Query/Response pair, reusing the
  established event schema.
- `app.py` -- added `POST /api/live/dns`, reusing the existing
  `_parse_url()` helper for consistent validation with Simulation mode;
  returns 400 for an unusable URL and 502 (upstream lookup failure) if
  the domain doesn't resolve. No existing route was modified.
- `templates/index.html` -- added a Simulation/Live radio selector
  inside the existing Browsing form only; no new panel, no changes to
  Mail or Streaming.
- `static/css/style.css` -- small `.mode-toggle` styling addition.
- `static/js/activity_panel.js` -- the Browsing submit handler now
  branches on the selected mode: Simulation calls the exact same
  endpoint with the exact same success-path code as before; Live calls
  `/api/live/dns` and logs/status-shows the real resolved IP. On a Live
  DNS failure specifically, the visualizer is cleared via the existing
  `Visualizer.reset()` (added in Phase 4) so a stale prior result never
  sits next to a fresh error -- Simulation's existing error behavior
  (leave prior events as-is) was left untouched.
- `static/js/visualizer.js` -- **not modified**. Both modes return the
  same event shape, so the shared engine needed no changes at all.
- `README.md` -- new "Simulation Mode vs. Live Mode" section, a
  `POST /api/live/dns` API reference section, and Live DNS testing
  steps.

**Testing performed:** This sandbox unexpectedly *does* have outbound
DNS resolution available (confirmed by direct test before writing any
code), so testing here used genuine real lookups, not mocks:
- `example.com` and `python.org` each resolved to a different real,
  live IP address in the same test run, confirming the result is not
  hardcoded.
- An intentionally nonexistent domain correctly raised a handled error
  (`socket.gaierror` → `DNSLookupError`) and the Flask route returned a
  clean 502 with a readable message -- no unhandled exception, no
  server crash.
- An empty URL returned the existing 400 validation error, matching
  Simulation mode's behavior for the same input.
- Full Simulation regression re-run after the change: Browsing = 4
  events, Mail = 15 events, Streaming = 10 events for all three
  qualities -- all unchanged and passing.
- Homepage re-checked to confirm the new mode selector renders, all
  three activity tabs are intact, and the page still has exactly two
  main panels.
- Both `live/*.py` files pass `py_compile`; `activity_panel.js` passes
  `node --check`.

**Limitations (stated honestly, not hidden):**
- Live mode covers DNS only -- clicking Visit in Live mode does not
  fetch anything over HTTP, matching the assignment's explicit scope
  for this phase.
- The Live DNS events cannot show which specific DNS server answered,
  a real transaction ID, or a TTL, because Python's `socket` module
  doesn't expose that information -- this is disclosed in the events'
  own field names (e.g. "Resolver: System default (OS-configured)")
  and in `README.md`, rather than fabricated to look more detailed.
- Frontend interaction (clicking the actual radio buttons in a real
  browser) is, as in every previous phase, verified by code tracing
  rather than live browser execution, for the same sandbox reason
  noted in the Phase 4/5 entries above.

**Corrections:** None required -- the DNS module worked correctly on
the first implementation, verified against real, live lookups.

---

## Live Phase 2 -- Real HTTP/HTTPS after real DNS (correction pass)

**Status:** Completed, including a self-caught correction to the first
implementation.

**Objective:** Extend Browsing's Live mode from DNS-only to the full
real sequence -- DNS Query, DNS Response, HTTP(S) Request, HTTP(S)
Response -- performing a genuine HTTP/HTTPS GET against the real
resolved server, while preserving every Simulation-mode and Live
Phase 1 behavior exactly.

**First implementation (initial pass):** Added `live/http_live.py`
(`urllib.request`-based real GET) and a combined
`POST /api/live/browsing` route chaining `build_live_dns_events()` +
a new `build_live_http_events()`. Verified against a genuinely
reachable real host and confirmed events, status codes, and timing
were all real.

**Mistake found and corrected (documented honestly, as required):**
The first version's SSRF safety check called `socket.gethostbyname(domain)`
a *second* time, independently of the DNS step that had already resolved
the domain to build the DNS Query/Response events. This is a real
TOCTOU (time-of-check-to-time-of-use) flaw: two separate lookups for
the same domain can return different addresses (round-robin DNS, or
worst case a DNS-rebinding attack), meaning the safety check could
validate one address while a subsequent connection used another. This
was caught on review before being considered final, and fixed by:
extracting the IP already obtained by the DNS step
(`dns_events[1]["fields"]["IP Address"]"`) in `app.py`, and passing
that single value through to `live/http_live.py`'s safety check
(`_ip_is_blocked(resolved_ip)`) instead of re-resolving. `socket` is no
longer imported in `http_live.py` at all -- there is now exactly one
DNS resolution per Live Browsing request, not two.

Also corrected in this same pass, before considering the phase done:
- **Hostname vs. IP for the actual request:** re-verified (this part
  was actually correct from the first implementation, but is called
  out explicitly here since it was flagged as critical): the real GET
  request is built as `f"{scheme}://{domain}{path}"` using the
  original hostname, never the resolved IP -- confirmed by an
  automated check that the request URL contains the hostname and does
  NOT contain the resolved IP string.
- **Redirects:** changed from "follow automatically, report the final
  URL" to "do not follow -- show the real 3xx response, including its
  Location header, as Event 4." Implemented via a custom
  `urllib.request.HTTPRedirectHandler` subclass whose
  `redirect_request()` returns `None`. Verified against a real local
  HTTP server returning a genuine 301, confirming the 301 (not a
  followed 200) is what comes back.
- **Scheme validation:** the first version silently treated any
  non-"http://" input as https, meaning `ftp://example.com` would have
  quietly become `https://example.com`. Added an explicit scheme check
  that rejects anything other than http/https with a clear 400 error.
- **HTTPS labeling:** the event `protocol` field stays `"HTTP"` for
  both http and https requests (matching this project's established
  DNS/HTTP/SMTP protocol categories -- HTTPS is HTTP-over-TLS at the
  application layer), but the `summary` and a new `Scheme` field now
  say "HTTP" or "HTTPS" explicitly, so the distinction is still
  visible without inventing a new protocol category.

**Files changed:** `live/http_live.py` (rewritten: TOCTOU fix,
no-redirect handler, `Scheme` field, `Location` header added to the
shown-headers list); `app.py` (`_live_scheme_or_error()` replacing the
looser `_live_http_scheme_for()`, resolved-IP extraction and pass-through
in `live_browsing_route()`); `static/js/activity_panel.js`
(`extractLiveSummary()` now reads by event position instead of matching
on summary text, since summary text now varies by scheme; log/status
wording updated to include the resolved IP, scheme, and status, per the
requested format); `templates/index.html` (mode-selector label and
comment updated: "Live (real DNS + HTTP)"); `README.md` (Simulation vs.
Live Mode section substantially expanded, new `/api/live/browsing` API
reference, Live Browsing testing steps replacing the old Live-DNS-only
steps, Assumptions section updated).

**Testing performed:**
- Full pipeline re-verified against a genuinely reachable real host
  (api.anthropic.com, the one host this sandbox's egress proxy
  allows): 4 events, real IP, real HTTPS status, hostname confirmed
  present in the request URL and the IP confirmed absent from it.
- SSRF classification unit-tested directly against 10 addresses
  (loopback, three RFC1918 ranges, link-local, unspecified, multicast,
  two public addresses, and an IPv6 loopback) -- all classified
  correctly.
- No-redirect behavior verified against a real local HTTP server (on
  loopback, which needs no external network) returning an actual 301
  with a Location header -- confirmed the 301 comes back as Event 4
  as-is, not followed.
- Scheme rejection verified for `ftp://` (clear 400) and `file://`
  (also rejected, via the earlier domain-parsing check, since a
  `file://` URL has no domain for this app's purposes -- same safe
  outcome, different code path).
- SSRF safeguard re-verified through the full Flask route with
  `http://localhost` -> 502, clearly worded, not a scheme error.
- Full Simulation regression re-run after every change in this phase:
  Browsing 4 / Mail 15 / Streaming 10x3, all unchanged and passing.
  The Phase-1 `/api/live/dns` endpoint re-tested and still works.

**Limitations (stated honestly, not hidden):**
- This sandbox's own network egress is restricted to a small
  allowlist (confirmed directly: `example.com`, `python.org`,
  `pypi.org`, and `github.com` are all intercepted by an internal
  proxy that returns a synthetic `403 host_not_allowed`, while
  `api.anthropic.com` is genuinely reachable). The module correctly
  reports whatever real HTTP response it receives -- including that
  proxy's 403 -- which incidentally proved the HTTPError-handling code
  path works correctly, but full testing against arbitrary public
  domains could only be done structurally (code review + the one
  reachable host), not against every domain a student might try. This
  will work against any real domain on the student's own unrestricted
  machine.
- Frontend interaction (radio buttons, visual event playback) is
  still verified by code tracing rather than live browser execution,
  for the same sandbox reason noted in every earlier phase's entry.
- No IP-pinning at the TCP-connect level: the safety check uses the
  already-resolved IP (fixing the TOCTOU double-lookup bug above), but
  the actual `urllib` connection still resolves the hostname again
  internally as a normal part of connecting. A fully rebinding-proof
  implementation would need to pin the validated IP at the socket
  level while still presenting the hostname for Host/SNI -- this is a
  meaningfully larger change and was judged out of scope for a Live
  Phase 2 focused on "real HTTP after real DNS," but is worth noting
  as a genuine residual limitation rather than glossing over it.

---

## Final Live Implementation Pass -- Complete Live Extension & Verification

**Platform / model used:** Google Antigravity (powered by Gemini 3.8 Flash), assisting the student directly on their local workstation.

**Prompt (summary):** Complete the entire optional live extension in one final pass without restarting the project or creating further phases:
1. Finish Live Browsing with an in-panel sandboxed iframe browser preview and educational fallback for `X-Frame-Options` / CSP blocking.
2. Implement real Live Streaming using HTML5 `<video>` and HLS.js, capturing real player lifecycle events (DNS, manifest loading/loaded, fragment loading/loaded with adaptive bitrate levels) and streaming them progressively to the Visualizer.
3. Implement real Live Mail performing actual authenticated SMTP submission via Python's standard `smtplib`, using environment variables (`SMTP_HOST`, `SMTP_PORT`, `SMTP_SECURITY`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM`), with strict `AUTH <redacted>` credential protection, SSRF safety, and graceful degradation when unconfigured.
4. Maintain the strictly two-panel layout (`.panel--activity` and `.panel--protocol`).
5. Guarantee 100% regression fidelity for all Phase 0–5 Simulation modes.
6. Create an automated test runner (`run_tests.py`) verifying simulations, live endpoints, SSRF, scheme validation, and DOM integrity.
7. Update all documentation (`README.md`, `ai_usage_log.md`, `reflection.md`, `final_test_report.md`, `requirements_checklist.md`).

**What the AI produced:**
- `live/smtp_live.py`: Real SMTP submission engine using standard `smtplib` and `socket`. Resolves `SMTP_HOST` via DNS, enforces SSRF protection, logs `220` server greeting, `EHLO`, `STARTTLS`, `AUTH <redacted>`, `MAIL FROM`, `RCPT TO`, `DATA` (`354`), message payload transfer (`250`), and `QUIT` (`221`).
- `app.py`: Added `POST /api/live/mail` route, imported `live/smtp_live.py`, enhanced `_live_scheme_or_error()` to detect and reject arbitrary non-HTTP schemes before domain parsing.
- `static/js/visualizer.js`: Extended with `appendLiveEvent()` for progressive real-time event arrival during HLS playback, while preserving standard finite playback controls (`loadEvents`, `Previous`, `Next`, `Pause`, `Replay`) for all Simulation runs.
- `templates/index.html` & `static/css/style.css`: Integrated browser preview container (mockup address bar, iframe, fallback notice) in Browsing panel, mode selectors in Mail and Streaming panels, configurable HLS URL input, and video container. All styling strictly contained within the left Activity Panel.
- `static/js/activity_panel.js`: Integrated live browser preview triggering, live SMTP submission handling, and HLS.js lifecycle event listeners (`MANIFEST_LOADING`, `MANIFEST_PARSED`, `FRAG_LOADING`, `FRAG_LOADED`, `ERROR`).
- `run_tests.py`: Comprehensive test runner covering 11 automated test cases.

**Mistakes found and corrected (documented honestly):**
1. **Scheme validation on pseudo-schemes without `://`:** In `app.py`, `_live_scheme_or_error()` originally checked `if "://" in stripped:`. When testing `javascript:alert(1)`, `_parse_url()` prepended `http://`, resulting in a hostname of `javascript` which proceeded to DNS resolution and failed with 502 rather than 400. Fix: updated `_live_scheme_or_error()` to check for scheme patterns before `:` and reject all non-`http`/`https` schemes with an immediate 400.
2. **Bracket matching test on multiline template strings:** When writing `run_tests.py`, an initial regex-based bracket counter stripped quotes before template strings, causing single quotes inside JS template literals (e.g. `got '${scheme}://'`) to eat code up to the next single quote. Fix: replaced regex stripping with an accurate character-by-character JavaScript tokenizer state machine that tracks line comments, block comments, double quotes, single quotes, and backtick template literals.
3. **SMTP EHLO response false positive in test assertion:** In `run_tests.py`, the test checked `if "AUTH" in e["raw"]: assertIn("<redacted>")`. Because the mock Postfix server advertised `AUTH PLAIN` in its `EHLO` response, this assertion triggered on the server's feature advertisement. Fix: scoped the redaction check specifically to `e.get("summary") == "SMTP Authentication Request (Live)"`.

**Testing performed:**
- `python run_tests.py`: 11 test suites executed and passed in 0.090s:
  - Simulation Browsing: 4 deterministic events.
  - Simulation Browsing 404: `notfound.test` returns 404.
  - Simulation Mail: 15 events with standard reply codes (220, 250, 354, 221).
  - Simulation Streaming: 10 events across 360p, 720p, 1080p with correct quality paths.
  - Live Browsing scheme rejection: `ftp://`, `file://`, `javascript:` rejected with 400.
  - Live Browsing SSRF defense: loopback and RFC1918 addresses rejected with 502.
  - SSRF unit test: 8 address classifications verified.
  - Live Mail unconfigured test: clean 400 error without crashing.
  - Live Mail mock test: full STARTTLS + AUTH flow with verified `<redacted>` password protection.
  - HTML structure check: exactly 2 main panels, all containers and IDs present.
  - DOM ID & JS syntax check: all IDs called by JS exist in HTML, all brackets balanced.
- Live internet tests from workstation:
  - Real DNS query against `example.com`: status 200, resolved IP `104.20.23.154`, lookup time 46.9ms.
  - Real HTTP GET against `http://example.com`: status 200, real headers (`Content-Type`, `Date`, `Server`).

**Limitations (stated honestly):**
- **Iframe Browser Embedding**: Cross-origin web pages with `X-Frame-Options: DENY/SAMEORIGIN` or CSP `frame-ancestors` cannot be displayed inside an iframe due to browser security models. The implementation handles this gracefully by displaying an informative fallback message explaining the security restriction while ensuring the protocol visualization functions normally.
- **HLS Stream CORS Requirement**: In-browser HLS playback requires the streaming server to expose CORS headers (`Access-Control-Allow-Origin`). A verified public test stream (`https://test-streams.mux.dev/x36xhzz/x36xhzz.m3u8`) is configured by default; arbitrary non-CORS streams will display a readable CORS error.
- **SMTP Submission**: Real email sending requires valid SMTP credentials configured via environment variables. If unconfigured, the application gracefully alerts the user without crashing.

