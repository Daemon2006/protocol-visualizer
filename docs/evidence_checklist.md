# Evidence Checklist

Use this as a checklist while capturing screenshots/recording for
submission. Check items off as you capture them.

## Application screenshots

- [ ] **Screenshot 1 — Overall dashboard.** The empty two-panel layout:
  Activity Panel (left, with the three tabs visible) and Protocol
  Visualization Panel (right, showing the "waiting for an activity"
  placeholder and disabled playback controls).

- [ ] **Screenshot 2 — Browsing DNS/HTTP visualization.** The
  Browsing tab active, a URL entered, and the right panel showing one
  of the four events (ideally the HTTP Response step, since it shows
  a status code + headers + the raw HTTP text in the monospace box).

- [ ] **Screenshot 3 — Mail SMTP visualization.** The Mail tab active
  with To/Subject/Body filled in, and the right panel showing an SMTP
  step (the "Message Data" step is a good choice — it visibly shows
  the From/To/Subject headers and body text pulled from the form).

- [ ] **Screenshot 4 — Streaming manifest/segment visualization.**
  The Streaming tab active with a quality selected, and the right
  panel showing either the HTTP Manifest Response (to show the HLS
  playlist body) or a Segment Request (to show the quality-specific
  path, e.g. `/video/720p/segment002.ts`).

- [ ] **Screenshot 5 — Playback controls / activity switching.**
  Either: (a) the Previous/Pause/Next/Replay controls in their
  enabled state mid-sequence, with the "Step X of Y" indicator
  visible, or (b) a before/after pair showing the right panel clearing
  when switching from one activity tab to another.

## AI usage evidence

- [ ] **AI platform/model evidence screenshot.** A screenshot of the
  claude.ai conversation showing the model name/platform (visible in
  the interface), to accompany the statement in `docs/ai_usage_log.md`.

- [ ] **AI prompt/history evidence.** Either export/screenshot the
  conversation history directly from claude.ai, or rely on
  `docs/ai_usage_log.md` in this project, which records every phase's
  prompt summary, what was produced, how it was verified, and any
  corrections made — this file is itself usable as the required
  prompt-history evidence if a raw chat export isn't available.

## Where to find supporting detail

- Full prompt-by-prompt history and corrections: `docs/ai_usage_log.md`
- Written reflection: `docs/reflection.md`
- Requirement-by-requirement coverage: `docs/requirements_checklist.md`
- Test results: `docs/final_test_report.md`


## Optional Live Browsing extra-credit evidence

For the optional live-networking extension, capture one screenshot showing
the Browsing tab set to **Live (real DNS + HTTP)** with a completed four-event
sequence: DNS Query, DNS Response, HTTPS/HTTP Request, HTTPS/HTTP Response.
The screenshot should also show the real response status in the status/activity
area. This is supplementary to the required Simulation evidence.
