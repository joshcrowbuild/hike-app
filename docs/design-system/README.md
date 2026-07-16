# Design system — `docs/design-system/`

The **look-and-feel layer** of record (UI system + front-end performance). Home for the v0.2 facelift.

| File | What it is |
|------|-----------|
| [`spec-v0.2.md`](./spec-v0.2.md) | **The spec of record.** Foundations (tokens, color, type, spacing, motion, voice) · component library · the performance/reload fix · sequencing + agent map. Supersedes `docs/research/design-system-v0.1.md`. |
| [`mocks/happy-path-before-after.html`](./mocks/happy-path-before-after.html) | Before/after of feed, card, and detail-conditions. The visual North Star for the happy path. |
| [`mocks/states-gallery.html`](./mocks/states-gallery.html) | Every non-happy state: condition tiers, "couldn't verify" fix, degraded personalization, empty/no-match, reload, full outage, mixed detail. |
| [`kickoff/wp2-conditionstatus-trailcard.md`](./kickoff/wp2-conditionstatus-trailcard.md) | Self-contained brief for **Gemini 3.1 Pro (A)** — WP-2. |
| [`kickoff/wp3-detail-evidence.md`](./kickoff/wp3-detail-evidence.md) | Self-contained brief for **Gemini 3.1 Pro (B)** — WP-3. |

**Reading order:** `spec-v0.2.md` → open both mocks → the kickoff briefs. Open mocks in a browser
(`open docs/design-system/mocks/*.html`).

**Status:** DRAFT. WP-0 (tokens + the two frozen contracts) must land before WP-2/WP-3 kick off.
