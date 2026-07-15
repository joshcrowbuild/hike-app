# Call-Card Design Brief — the hero "Call" adoption lane

> **How to run this:** open this repo in Antigravity and tell the agent:
> *"Read and execute the brief in `docs/research/call-card-design-brief.md`. The direction is already decided — converge, make it buildable, and deliver it as a PR."*
> This file is the instruction set. Everything below is addressed to the executing design agent.

---

You are a senior product designer executing an **adoption lane** of an accepted design direction — not a re-visioning. The vision ("The Confident Call + Quiet Context", `ux-vision-2026-07.md`, adopted incrementally per decision-log §46) already made the argument; its first lane (the Context Ribbon) shipped. Your lane is the centerpiece: **the hero "Call" card** — Home leads with one confident recommendation, and the rest of the ranked feed docks beneath it as quiet alternatives. Your job is a build-ready spec plus a clickable Storybook slice. Converge; do not diverge.

## 1 — Orient (in this order)

- `docs/research/ux-vision-2026-07.md` — the accepted direction, especially its recommended synthesis and Home wireframes.
- `frontend/src/screens/VisionPrototype.stories.tsx` — the isolated prototype slice the vision left behind; you extend this, not the production screens.
- **Shipped since the vision (design around these, don't restate them):** the Context Ribbon (#224 — Home states region context *once*; the Call card must not duplicate region-level weather/AQI), the card facts-row overflow fix + 34rem desktop column (#220), Detail conditions de-dup (#223).
- Current production surfaces: `frontend/src/screens/Home.tsx`, `cardParts.tsx`, `ConditionStates.tsx`, `FeedConditions.tsx`; tokens in `frontend/src/design/`.
- The honesty grammar you must render: decision-log **§41** (a verified hazard stays visible on the card with a sourced warning — never hidden, never re-ranked), **§42** (confidence presentation: `stated` / `hedged` / `flagged`; confidence never affects ranking), and the **six per-kind condition states** (`present · stale_degraded · no_hazard · no_data · unavailable · not_fetched`).
- `CLAUDE.md` §non-negotiables + `AGENTS.md` (repo + PR hygiene).
- **Run it:** `cd frontend && npm run dev` (mock mode works without the backend) and `npm run storybook`. Look at Home at phone and desktop widths before designing.

## 2 — Scope and hard facts

- **The Call is presentation, not a new engine.** The CDP-04 GO/MARGINAL/NO-GO verdict is Phase D and does not exist. v1 works with exactly what the API serves today: rank order, `fitLine`, per-kind `conditions`, confidence presentation, `warnings[]`. Design a clearly-marked slot where the future verdict lands; nothing in v1 may require it.
- **Two-phase render is live:** ranked cards paint first (<1.5s), conditions patch in afterward. The hero must be designed for its pending state — a Call whose conditions are still arriving must read as "checking", never as "clear".
- **The hero inherits the whole truth.** All six condition states, the confidence grammar, and §41 warnings must stay legible at hero scale. A warning-bearing or hedged top pick is the *hard case* — design it first, not as an afterthought. A confident Call is earned, never faked.
- **Alternatives dock, they don't disappear.** Specify the interaction (tap/gesture/scroll) that reaches the rest of the ranked list, and how many surface by default. No infinite scroll.
- **Responsive:** mobile-first; desktop lives inside the shipped 34rem column. The desktop map-split is a *separate future lane* — don't design it, don't preclude it.
- **Tokens-first:** tie every choice to existing tokens; name any new tokens you need. React-Aria + vanilla-extract idioms; the blocking axe a11y gate must stay green; never encode confidence or warnings by color alone.

## 3 — Deliverables (ship as one PR)

**A) `docs/research/call-card-design-spec-2026-07.md`** — added to the `docs/research/README.md` index (`make docs-lint` green). In order:
1. The hero's information hierarchy — what leads, what rests, what is one tap away (ASCII wireframes, mobile + desktop-in-column).
2. **Every state:** stated / hedged / flagged confidence on the hero; a §41 warning-bearing Call; conditions pending (two-phase); an honestly-empty feed; the set-aside/unverifiable case.
3. The alternatives docking model + interaction spec.
4. Type/token spec (existing tokens first; new tokens named + justified).
5. Microcopy samples in the app's voice: a confident Call, a hedged Call, a warned Call, the pending line.
6. The future-verdict slot: where CDP-04's GO/MARGINAL/NO-GO lands when built, and what placeholder discipline holds until then.
7. A build plan mapped to the real files (`Home.tsx`, `cardParts.tsx`, …): what changes when the PO adopts this, in 2–3 reviewable increments.

**B) A clickable Storybook slice** extending `VisionPrototype.stories.tsx` — hero + docked alternatives, reusing the existing honesty components (`ConditionStates` etc.), covering at minimum: confident, hedged, warned, and pending hero states. Production screens untouched. `make check` and the frontend suite + a11y gate green.

Mark the PR **"FOR DESIGN REVIEW — PO adoption pass required before merge."**

## 4 — Hard constraints (violating any fails the brief)

- Never weaken source-or-silence; absence must never read as "all clear"; a verified hazard is shown with its source, never hidden.
- Confidence never reorders anything; it only changes presentation.
- No engagement mechanics of any kind. Calm is load-bearing: the success state is the user closing the app.
- Buildable in the existing stack; fully accessible (keyboard + screen reader).
- Small reviewable commits; `make check` / `make docs-lint` green; the PR template in `AGENTS.md`.
