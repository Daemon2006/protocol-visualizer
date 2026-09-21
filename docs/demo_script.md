# Demo Script (target: 2–4 minutes)

A suggested walkthrough for the required demo video/screenshots, with a
short optional Live Browsing segment that demonstrates the extra-credit
real-networking extension. Keep the live segment brief so the full demo
stays within the assignment's 2–4 minute target.

## 1. Introduction (~20 seconds)

> "This is a Dual-Panel Activity & Protocol Visualizer for the
> Application Layer. The required Simulation Mode covers Browsing, Mail,
> and Streaming, while the optional Live Browsing extension can perform
> a real DNS lookup and HTTP/HTTPS request. The right panel shows the
> corresponding application-layer messages step by step."

Show the empty dashboard: point out the two panels, the activity tabs,
and the disabled playback controls before anything has run.

## 2. Browsing demonstration (~35 seconds)

1. Click the **Browsing** tab (already selected by default).
2. Type `example.com` into the URL field, click **Visit**.
3. Narrate as the sequence plays: "DNS Query, then DNS Response with a
   simulated IP, then an HTTP GET request, then the HTTP response."
4. Optionally type `notfound.test` and re-run to show the HTTP response
   switching to 404 — proving the status code isn't hardcoded.

## 3. Mail demonstration (~40 seconds)

1. Click the **Mail** tab.
2. Fill in To: `alice@example.com`, Subject: `Test Mail`, Body:
   `Hello from the protocol visualizer.`, click **Send**.
3. Narrate: "This is a full fifteen-step SMTP conversation — DNS MX
   lookup, greeting, EHLO, MAIL FROM, RCPT TO, DATA, the message
   itself, then QUIT — each with its real SMTP reply code."
4. Use **Next** a couple of times to pause on the "Message Data" step
   and point out the From/To/Subject headers and body text.

## 4. Streaming demonstration (~40 seconds)

1. Click the **Streaming** tab.
2. Leave quality at `720p` (or pick one), click **Play**.
3. Narrate: "DNS lookup for the video host, then an HTTP request for
   the manifest — a real HLS playlist format — then three separate
   HTTP requests, one per video segment."
4. Change the quality to `1080p` and click Play again; pause on the
   manifest or a segment request to show the path now says
   `/video/1080p/...` instead of `/video/720p/...`.

## 5. Playback controls demonstration (~25 seconds)

With any sequence loaded (Streaming works well here since it has 10
steps):
1. Click **Pause** mid-playback — point out it stops advancing.
2. Click **Next** / **Previous** a couple of times — point out the
   step counter ("Step X of Y") updates and the buttons disable at
   the first/last step.
3. Click **Replay** — point out it restarts from step 1 *without* a
   new network request (open DevTools → Network tab beforehand if you
   want to show this directly).

## 6. Activity switching / synchronization demonstration (~20 seconds)

1. Mid-playback on one activity, click a different activity tab.
2. Point out the right panel immediately clears back to its "waiting"
   placeholder — it never shows a leftover event from the activity you
   just left.
3. Run a quick second activity to show the right panel updates
   correctly for the newly selected tab.

## 7. Optional Live Browsing extra-credit segment (~30 seconds)

1. Click **Browsing** and switch the mode to **Live (real DNS + HTTP)**.
2. Visit a simple HTTPS site such as `https://example.com`.
3. Pause the visualizer and point out the four real events:
   DNS Query → DNS Response → HTTPS Request → HTTPS Response.
4. Point out that the response status is the actual server response, and
   explain that Live mode preserves the original hostname rather than
   replacing it with the resolved IP. Mention that the application-level
   view does not claim to expose raw TLS packets.

## 8. Closing explanation (~15 seconds)

> "The required assignment is fully implemented in Simulation Mode, with
> all three activities using the same synchronized protocol visualizer.
> Browsing also includes an optional Live extension that demonstrates real
> DNS and HTTP/HTTPS networking with basic SSRF safeguards."

## Notes for recording

- Have the Flask server already running (`python app.py`) before you
  start recording, so the demo doesn't include setup time.
- If recording screenshots instead of video, capture: the empty
  dashboard, one full Browsing sequence, one full Mail sequence
  (ideally paused on the SMTP "Message Data" step), one Streaming
  sequence at a visible quality path, and one shot showing the
  Previous/Pause/Next/Replay controls in an enabled state.
