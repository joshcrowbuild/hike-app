# UX Vision Brief — a deep, divergent redesign spike

> **How to run this:** open this repo in Antigravity and tell the agent:
> *"Read and execute the brief in `docs/research/ux-vision-brief.md`. Think long and hard, diverge before you converge, and deliver it as a PR."*
> This file is the instruction set. Everything below is addressed to the executing design agent.

---

You are a world-class product designer and design-systems thinker — the taste of Jony Ive, the interaction instinct behind Things / old-Google-Now, the rigor of a great design-systems lead, and the intellectual honesty of a critic who'd kill a beloved idea rather than ship a dishonest one. You have this entire repository and a runnable app at your disposal. Your job is **not** to polish this product's UI — it's to **reconceive its experience from first principles** and leave behind a design vision the team can build toward.

**Think long and hard before you converge. This is a deep design spike, not a quick critique — budget real reasoning time.**

## 0 — How to think

- **Diverge before you converge.** Generate *many* genuinely different directions — including ones that throw away the current interaction model, that feel almost wrong, that would scare the team. Do not self-censor early. Put the brave options on the table next to the safe ones, and **record your divergent exploration in the deliverable** — don't hide it.
- **Interrogate every inherited assumption.** Is a scrolling feed of cards even the right container? Is a *list* the right answer, or is it *one* confident recommendation? Should the map/terrain be the surface, not a sub-page? Conversational? Ambient? Assume nothing about the current shape is sacred *except the soul and the refusals in §2*.
- **Design for a feeling, not just a function.** Say what the person should feel in the first two seconds, and how type, space, color, motion, and *silence* produce it.
- **Hold the contradictions in §3.** Sit in them; don't paper over them.

## 1 — Orient yourself (do this first, for real)

Ground yourself in the actual product before you critique anything:

- **Read the soul & the rules:** `docs/vision.md` (north star), `CLAUDE.md` (non-negotiable product rules — especially source-or-silence, honest confidence, anti-engagement, private-by-default), `AGENTS.md` (repo operating rules + PR hygiene).
- **Read the current design language:** `docs/research/design-system-v0.1.md`, plus the live tokens/theme in `frontend/src/design/` (`tokens.css`, `theme.css.ts`, `typeScale.test.ts`, `a11y.css.ts`) and `frontend/src/styles.css`. This is a token-first system (Style Dictionary / W3C DTCG) built with **React + React-Aria + vanilla-extract**, mobile-first.
- **Build on the prior UX thinking — don't repeat it:** `docs/research/gemini-ia-flow-review-2026-07.md` (an earlier IA/flow review — the "Omnibox" idea came from there), `ux-review-craft-2026-07.md`, `ux-review-conditions-2026-07.md`, `outcome-card-ux.md`, `ux-assembly-plan-v1.md`, `glm-craft-lane-c-prep-2026-07.md`. Note what's already been proposed so you go *beyond* it.
- **Read the actual screens:** `frontend/src/screens/` — `Home.tsx`, `Detail.tsx`, `Outcome.tsx`, `cardParts.tsx`, `ConditionStates.tsx`, `FeedConditions.tsx`, `BootShell.tsx`.
- **RUN IT AND LOOK AT IT.** `cd frontend && npm run dev` (Vite) — open it in a browser and *experience* the real rendered UI at a phone width **and** a desktop width. Use `npm run storybook` (port 6006) to see the honesty components in isolation. There's a mock data mode so it renders without the backend. **Your critique must be grounded in what you actually see on screen, not just the code.** Note what's cramped, redundant, beautiful, and tiring.

## 2 — The soul & the sacred refusals (protect these; do NOT redesign them away)

It's a **private, single-user, self-verifying hiking/backpacking trip planner** — a calm utility, like *a trusted expert friend who's already done all the homework and will only ever tell you the truth*. Load-bearing and non-negotiable:

1. **Source-or-silence** — every fact carries a named source + timestamp; unverifiable data is *disclosed as unverified*, never faked or quietly hidden; absence must never read as "all clear."
2. **Honest, calibrated confidence** — an authoritative source can be stated; a single unverified/aggregated source is *hedged*; stale data is *flagged*.
3. **Anti-engagement** — no infinite scroll, notifications-as-hooks, streaks, gamification, ads, or manufactured urgency. Success = a trustworthy answer and the user *closing the app*. Calm is the product.
4. **Private by default** — learns preferences locally (pace, taste, who they hike with, incl. a dog named Ruby); never monetizes attention.

You may **reframe how honesty and confidence are *expressed*. You may not weaken *whether* they are.**

## 3 — Why it falls flat (react to this, but verify it against what you see)

It's *correct and honest* but doesn't feel *cared-for or effortless*: **it reads like a spreadsheet with feelings** — every card a dense mini-dashboard (a verdict + six sourced/timestamped checks + monospace facts). **Honesty is rendered as anxiety** (a caveat-storm rather than a calm exhale). **There's no single confident answer** — just ten near-equal verdicts. There's **redundancy** (conditions shown twice on Detail; two look-alike text inputs), an **overflow-prone facts row**, a **desktop layout that's essentially a phone column stranded in white space**, and **no voice, warmth, or craft moment** — trustworthy but not *lovely*.

## 4 — The tensions you must actually resolve (don't dodge)

1. **Calm vs. informative** — honor source-or-silence *without* the density that kills calm. Where does information rest until asked for?
2. **Hedging vs. reassurance** — make "I'm 60% sure on air quality" feel like *trust*, not *worry*. What is the visual/verbal grammar of calibrated confidence that *soothes*?
3. **A list vs. an answer** — should the primary surface be a ranked feed at all, or one confident recommendation with the rest a gesture away?
4. **Utility vs. delight** — in an anti-engagement product, where does legitimate *joy* come from? (Craft, type, a perfect moment of relief, a beautiful terrain drawing, the quiet itself.)
5. **The card-as-dashboard** — is "verdict + six checks + facts" the right atom, or is it doing too much? What's the minimal unit that still tells the whole truth?

## 5 — Deliverable: ship it as a PR

Work on a branch off `main`; open a PR into `main` following `docs/process/development-process.md` + the PR template in `AGENTS.md`. Produce **two things**:

### A) The design-vision document (primary)

A new `docs/research/ux-vision-2026-07.md`, added to the `docs/research/README.md` index (keep `make docs-lint` green). It must contain, in order:

1. **First principles** — what this app is *for*, the one job it must nail, and what the person should *feel*.
2. **A design philosophy** — 5–8 opinionated principles specific to *this* product.
3. **3–5 genuinely divergent directions** (worldviews, not variations). For each: the core bet, an **ASCII wireframe of the primary screen (mobile)**, the interaction model, what it's brilliant at, what it sacrifices, and how it renders the honesty layer. Range required: include at least one that abandons the feed, one that's map/terrain-first, one that's single-answer or conversational, and one that's radically minimal. Be brave; keep the exploration visible.
4. **A recommended synthesis** — pick/fuse the strongest and defend it against the §4 tensions.
5. **Concrete redesigns** of **Home, the trail unit, Detail, and the intent/search entry** — clean ASCII wireframes for **both mobile and desktop** (the desktop today is embarrassing — give it a real answer), with the information hierarchy specified for each.
6. **Design language** — type scale/pairing, how confidence/hedging/warning are encoded *calmly* (never color alone), spacing/rhythm, the elevation/terrain drawing as a signature element, motion (what moves, how slowly, what stays perfectly still), and the *sound of silence* (how a checked-and-clear state reassures). Tie every choice back to the existing tokens where possible; name any new tokens needed.
7. **Voice & microcopy** — the app's verbal personality with samples (a verdict, a hedge, an unverifiable fact, an empty search).
8. **Kill list** — what to delete outright.
9. **"If you only did three things"** — the three highest-leverage moves from *correct* to *quietly extraordinary*, each mapped to the real files/components that would change.

### B) A buildable prototype of the recommended direction (stretch — do it if you can without destabilizing the app)

A **vertical slice** — the redesigned Home + trail-unit (and ideally the desktop layout) — as a *spike*: behind a route/flag or as Storybook stories, so the direction is **tangible and clickable**, WITHOUT ripping out the working production screens. Reuse the design tokens and the existing honesty components (`ConditionStates`, etc.). Keep `make check` and the a11y gate green. If a full slice is too much, at least turn your top wireframe into one real, styled Storybook story.

## 6 — Hard constraints (violating any fails the brief)

- **Never** add engagement mechanics, social features, notifications-as-hooks, ads, streaks, gamification, or urgency. Calm/anti-engagement is load-bearing.
- **Never** weaken source-or-silence: no fabricated data, no hidden uncertainty, no making absence look like "all clear."
- Keep it **private, single-user in feel.**
- Everything must be **buildable in the existing stack** (token-driven React web/PWA, React-Aria, vanilla-extract, mobile-first) and **fully accessible** (keyboard + screen reader; never rely on color alone for confidence/warnings — there's a blocking axe a11y gate, don't red it).
- Follow repo hygiene: small reviewable commits, the PR template, `make check` / `make docs-lint` green, and mark the PR **"DO NOT MERGE — design vision for review"** so a human decides what to adopt.

Now: read, run it, *look* at it, then think hard and wander before you bring it home. The bar: reading your doc should feel like you saw something the rest of us missed — and the prototype should make it real enough to click.
