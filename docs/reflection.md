# Reflection

**Project:** Dual-Panel Activity & Protocol Visualizer
**Course:** Computer Networks — Application Layer
**Development approach:** AI-agent assisted (Claude)

## 1. Which AI platform and model I used, and why

I built this project using Claude, through the claude.ai chat
interface (this session ran on Claude Sonnet 5). I chose Claude
because it could act as a genuine development partner rather than a
one-shot code generator: I could hand it the assignment PDF directly,
have it produce a written architecture plan *before* any code existed,
and then work through the project in small, reviewable phases —
Browsing first, then Mail, then Streaming, then an integration/polish
pass, then this final verification pass. At every phase boundary I
asked it to stop and wait for my approval before continuing, and it
did. It was also able to run the actual Flask application inside its
own environment (using a real Python interpreter, not just guessing),
so most of the testing described in this document — event counts,
status codes, SMTP reply codes, quality-specific URL paths — was
verified by actually executing the code, not just by reading it.

## 2. How the two panels stay synchronized

The whole project follows one pipeline, used identically by all three
activities:

```
User action (left panel form)
  -> fetch() sends the input to Flask, no page reload
  -> Flask route validates input, calls a simulator module
  -> simulator returns an ordered list of protocol "events"
     (same shape for every activity: protocol, direction, summary,
     raw message, key fields, timing, step number)
  -> Flask returns that list as JSON
  -> the shared JavaScript "Visualizer Engine" stores the list and
     displays one event at a time in the right panel, auto-advancing
     on a timer
  -> Previous / Pause / Next / Replay all just move a pointer through
     that same in-memory array -- no new request to the server
```

Because every activity produces the *same* event shape, there is only
one visualizer, reused unchanged across Browsing, Mail, and Streaming
— it has no idea whether it's replaying DNS+HTTP, DNS/MX+SMTP, or
DNS+HTTP-manifest-and-segments.

During the integration pass I found and fixed two real synchronization
gaps: first, switching activity tabs without submitting anything left
the *previous* activity's last event and enabled playback buttons
visible, which was misleading; the fix clears the panel back to its
placeholder state on every tab switch. Second, if a request was still
in flight when the user switched tabs, its late response could
silently overwrite whatever the user was now looking at; the fix
tracks which activity tab is currently selected and only lets a
response update the shared visualizer if that tab is still active.

## 3. What the AI got wrong, and how it was corrected

- **A broken ZIP delivery.** After the first Browsing phase, the ZIP I
  downloaded still contained the old Phase 0 code, not the new
  Browsing implementation. The actual project files on Claude's side
  were correct the whole time — the packaging/delivery step was the
  problem, most likely compounded by my browser reusing a cached
  download under the same filename. The fix was to rebuild the archive
  under a new filename and verify the contents *from inside the ZIP
  itself* (not just the source folder) before handing it to me again.
  Every ZIP after that point was verified the same way, and the
  problem never recurred.
- **An unescaped-HTML risk in the visualizer.** The right panel builds
  its HTML using JavaScript template strings, and some of that text
  (the domain typed into the URL box, for example) originates from
  user input. The first version inserted that text directly, which
  meant a deliberately crafted domain could have injected HTML/script
  content into the page. This was caught in a dedicated review pass
  and fixed by escaping every user-influenced value before it's
  inserted into the DOM.
- **The two synchronization gaps** described in section 2 above.

To Claude's credit, all four protocol simulators (DNS, HTTP, SMTP,
streaming) were correct on the first implementation and never needed a
protocol-accuracy correction — SMTP reply codes, command order, and
the DNS/HTTP-only composition of Streaming were all right from the
start and confirmed by direct testing at every later phase.

## 4. Differences between the three protocol flows

**Browsing (DNS + HTTP):** the shortest flow — one DNS query/response
to resolve the domain to an IP, then one HTTP GET request/response.
Stateless: each of the two exchanges is self-contained, and the HTTP
response can vary (200 vs. 404) based on the requested resource.

**Mail (DNS/MX + SMTP):** SMTP is a *stateful, multi-step conversation*
rather than a single request/response pair. The client and server
exchange fifteen messages in a fixed order — greeting, EHLO, MAIL FROM,
RCPT TO, DATA, the message itself, then QUIT — and each step has its
own three-digit reply code (220, 250, 354, 221) that means something
specific in the SMTP specification, unlike HTTP's single status line
per exchange. The DNS lookup here is also different in kind from
Browsing's: it's an MX (mail exchanger) query, asking "which server
handles mail for this domain," not an A record asking "what is this
domain's IP."

**Streaming (DNS + HTTP manifest/segments):** this one surprised me —
it turns out video streaming isn't a special protocol at all. After
one DNS lookup, *everything* is ordinary HTTP: first a GET for a
playlist/manifest file (a real `.m3u8` HLS playlist format, listing
each segment), then a separate GET for every individual video segment.
Changing the quality selector doesn't change the protocol behavior at
all — it only changes the *paths* being requested
(`/video/720p/...` vs. `/video/1080p/...`), which is exactly how real
adaptive streaming picks a quality tier: the client requests a
different file, not a different kind of connection.

## A note on scope and optional Live extension

The required assignment remains fully implemented as an **offline
Simulation Mode**, which is explicitly permitted by the assignment. The
three required activities continue to use deterministic local protocol
events so the submission remains completely repeatable, testable, and safe
to demo without requiring internet access or third-party credentials.

As an optional extra-credit extension, the **Live Mode** was expanded to
encompass all three activities within the single two-panel architecture:

1. **Live Browsing**: Performs real DNS resolution via Python's `socket`
   and a real HTTP/HTTPS GET request via `urllib.request`, accompanied by
   a sandboxed browser preview iframe inside the left Activity Panel. It
   preserves the original hostname for HTTP Host headers and HTTPS
   TLS/SNI validation, applies SSRF filtering against loopback and
   private addresses, and honestly displays an educational explanation if a
   target website blocks embedding via `X-Frame-Options` or CSP.
2. **Live Streaming**: Plays real HTTP Live Streaming (HLS) video via
   HTML5 `<video>` and HLS.js inside the Activity Panel, capturing genuine
   player lifecycle events (real DNS lookup, manifest loading and parsed
   responses, and media segment request/response pairs across adaptive
   bitrate tiers). The shared Visualizer progressively updates as segments
   arrive without disrupting manual stepping controls.
3. **Live Mail**: Performs real authenticated SMTP submission via
   Python's standard `smtplib`. It loads server credentials strictly from
   environment variables or a local `.env` file, enforces SSRF defenses on
   `SMTP_HOST`, and never exposes secrets in logs or event streams (redacting
   credentials as `AUTH <redacted>`). If SMTP is unconfigured, it surfaces a
   friendly, non-crashing notice.

Keeping the core Simulation Mode independent guarantees that the primary
course deliverables remain robust, while the Live extension demonstrates
real-world networking, defensive security, and modern web application
integration.
