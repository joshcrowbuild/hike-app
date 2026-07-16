# Adventure Planner Design System — v0.2 "Calm Utility"

**Status:** DRAFT (spec of record) · **Owner:** PO · **Supersedes:** `docs/research/design-system-v0.1.md`
**Scope:** the *look-and-feel layer* = **UI system + front-end performance**. Native iOS is out of scope.

> This is a **reconcile-and-finish** release, not a greenfield build. The v0.1 pipeline (DTCG → Style
> Dictionary v4 → vanilla-extract), the honesty primitives (`Confidence`/`Staleness`/`Signal`), the
> `ConditionStates` renderer, the `Icon`/`glyphs` layer, and Storybook+axe all ship today. v0.2 **reconciles
> drift, finishes the partial Epic-019 type migration, resolves three brand decisions, and extends the
> system to signed-in performance.** Read Appendix A first if you maintained v0.1.

**Visual North Star:** `docs/design-system/mocks/happy-path-before-after.html` and
`docs/design-system/mocks/states-gallery.html`. When prose and mock disagree, the mock's *intent* wins;
the spec's *tokens* win on exact values.

---

## 0. Decisions locked for v0.2

| # | Decision | Choice | Consequence |
|---|----------|--------|-------------|
| D1 | Signal palette | **Full 4-tier severity** | `silent` (clear) · `unknown` (gray) · `heads-up` (amber, NEW hue) · `blocked` (terracotta, firm barrier). Replaces the single-hue `signal.caution`. |
| D2 | Data voice | **Mono for metrics only** | Numeric facts render in the mono family (tabular figures); prose stays sans. Fulfils v0.1 §5.1's never-shipped "cartographic voice." |
| D3 | Typeface | **IBM Plex, self-hosted** | `sans → IBM Plex Sans`, `mono → IBM Plex Mono`, subset + self-host, with system fallback. Replaces `system-ui`. |
| D4 | Perf root cause | **Signed-in cache exclusion** (not cold-start) | Render is a paid Starter ($7/mo, no spin-down). Primary fix = extend SWR cache to signed-in viewers. |

**The governing laws** (every rule below derives from these; they extend the vision *refusals*):

1. **Silence is a state** — a clean result shows nothing.
2. **Conclusion over checklist, but keep the receipt** — show what we concluded; sourced evidence lives one tap away (never delete provenance — that would break source-or-silence / Rule #1).
3. **Every fact declares its altitude** — area facts once at area level; trail facts on the trail.
4. **Speak human** — no builder nouns on screen.
5. **One role-based type scale** — pick a role, never a size.
6. **Degrade calmly** — never alarm-red for a non-event.
7. **Color encodes actionability, not confidence** — unknown is gray, never red (see D1).

---

# Part I — Foundations

## I.1 Token architecture (unchanged, extended)

Three tiers, one-directional reference (v0.1 §3 holds): **primitive → semantic → component**. Components
bind **semantic** roles and **primitive scales** only — never a raw color ramp (the vanilla-extract contract
in `frontend/src/design/theme.css.ts` enforces this by omitting primitive color ramps). Pipeline:
`frontend/tokens/*.json` (DTCG) → `frontend/style-dictionary.config.js` → `frontend/src/design/tokens.css`
→ `theme.css.ts` (`vars`). **Do not hand-edit `tokens.css`.** All v0.2 token deltas are in **Appendix B**.

## I.2 Color & the 4-tier signal system (D1)

**Neutral ink ramp** (unchanged, shipped): `text.primary` `#16191d` · `text.secondary` `#3c424a` ·
`text.muted` `#5e636a`. Surfaces: `canvas` `#f4f3ef` · `raised` `#fbfaf7` · `press` `#ecebe4`. Borders:
`hairline` `rgba(22,25,29,.14)` · `faint` `.08`. **Depth is carried by this ramp + hairlines, never shadow**
(the answer to "feels flat" that keeps the calm-utility refusal — see I.8).

**Signal tiers** (D1 — this is the load-bearing change):

| Tier | Semantic token | Value | Meaning | Rendering |
|------|----------------|-------|---------|-----------|
| `clear` | — (none) | — | Nothing to flag | **Renders nothing** (Law 1) |
| `unknown` | `signal.unknown.fg` | `text.muted` `#5e636a` | A source is down / not fetched | Neutral gray sentence, calm |
| `heads-up` | `signal.headsUp.fg` / `.bg` | `amber.600` (NEW) / `amber.alpha.10` | Actionable but not blocking (heat, permit, high flow) | Amber line + optional soft field |
| `blocked` | `signal.blocked.fg` / `.bg` | `terracotta.600` `#9a4424` / `.alpha.10` | A genuine barrier (closure) | Terracotta line + soft field; the only firm color |

**Rules:**
- **Amber is a NEW primitive** (`amber.600`, candidate `#8a6a16`). It **must** meet WCAG AA (≥4.5:1) on both
  `surface.canvas` and `surface.raised`; verify in WP-0 and darken if short. Dark-theme variant lightens.
- `signal.caution` (v0.1) is **deprecated**: each current usage is re-sorted into `heads-up` or `blocked`
  by *actionability* (see Appendix A). The `Signal` primitive gains a `tier` prop.
- **Never** introduce green ("good"), and **never** red for `unknown`. Reserve `blocked`/terracotta strictly
  for real barriers — a closure, not a missing AQI reading (Law 6 + 7).

## I.3 Typography (finishes Epic-019; D2, D3)

**Families (D3):** `sans → "IBM Plex Sans", system-ui, …` · `mono → "IBM Plex Mono", ui-monospace, …`.
Self-hosted woff2, **Latin subset**, `font-display: swap`; **preload** Sans 400/600 + Mono 500. System stack
is the fallback so first paint never blocks. **Weights:** 400 / 500 / 600 only (Apple HIG: avoid <400).

**The v0.2 role scale** — a closed set of 9. Pick a role, never a size (Law 5). **Line-heights are now
tokenized** (v0.1 debt: they were hardcoded in `styles.css`).

| Role token | size | line-height | weight | family | case | Supersedes | Applied to |
|------------|------|-------------|--------|--------|------|-----------|-----------|
| `type.display` | 1.75rem/28 | `tight` 1.2 | 600 | sans | Sentence | detail-name clamp | Detail hero name |
| `type.title` | 1.25rem/20 | `snug` 1.3 | 600 | sans | Sentence | `type.name` | Card name |
| `type.lead` | 1.125rem/18 | `normal` 1.45 | 400 | sans | Sentence | `size.place-lead`/`type.verdict` | Context sentence, verdict prose |
| `type.body` | 1rem/16 | `relaxed` 1.5 | 400 | sans | Sentence | `size.emphasis`/`body` | Prose (water, character) |
| `type.body-sm` | 0.875rem/14 | `normal` 1.45 | 400 | sans | Sentence | `size.condition`/`meta` | Secondary + degraded copy |
| `type.metric` | 1rem/16 (detail 1.25/20) | `snug` 1.3 | 500 | **mono**, `tabular-nums` | — | `type.fact-value` | Distance · ascent · duration · coords |
| `type.metric-label` | 0.75rem/12 | `snug` 1.3 | 500 | sans | Sentence, muted | `type.fact-label` | "Distance / Ascent / Duration" |
| `type.caption` | 0.75rem/12 | `snug` 1.35 | 400 | sans | Sentence, tertiary | `size.meta`/`supporting` | Provenance · source · timestamp |
| `type.overline` | 0.6875rem/11 | `snug` 1.3 | 500 | sans, +.06em | **UPPERCASE** | `size.label` | The one rare kicker |

**Laws that fall out of the table:**
- **Sentence case everywhere; UPPERCASE only in `type.overline`, used rarely.** This single rule retires
  `CURATION`, `CONDITIONS`, `IN THIS AREA`, `DISTANCE`-as-shouting — the biggest "de-wireframe" move.
- **Measure cap ≤ 66ch** on all prose blocks (NN/g 50–75ch). Prevents the "lines run over / data-dump" feel.
- **Metrics are mono + `tabular-nums`** so numeric columns align.

## I.4 Spacing, layout & grid

Adopt the shipped **4px-base** scale (`space.0…8` = 0/4/8/12/16/20/24/32), extended with `space.10` 40,
`space.11` 48, `space.12` 64 for section rhythm. Component padding follows an **8px rhythm** (inspired by
Carbon's 2px-base × mini-unit; ours is already 4px-native). Card internal padding `space.4` (16); card
gap `space.3` (12); section gap `space.8` (32). Radius: `sm` 8 / `md` 10 / `pill` 999 (unchanged).
Breakpoints (mobile-first, matching the app's single-column feed): `sm` 480 · `md` 768 · `lg` 1024.

## I.5 Iconography

Lucide via the shipped `Icon` wrapper (`frontend/src/components/Icon/Icon.tsx`): glyph is `aria-hidden`,
sizes to `1em`, binds `currentColor`, and **requires** an sr-only `label`. v0.2 **wires the three reserved
glyphs** in `frontend/src/screens/glyphs.ts`: `check`, `triangle-alert` (heads-up/blocked), `layers` (map).
New status glyphs map 1:1 to signal tiers: `unknown → CircleHelp/Info`, `heads-up → TriangleAlert`,
`blocked → CircleSlash/XCircle`. Icons earn their keep only beside a word — never decorative.

## I.6 Motion

Restraint. Two durations, one easing, extended minimally: `duration.fast` 120 · `duration.base` 160 ·
**`duration.slow` 240 (NEW, disclosure only)**; `easing.standard` `cubic-bezier(0.2,0,0,1)` (shipped) ·
**`easing.emphasized` `cubic-bezier(0.2,0,0,1)`** kept identical for now (Material-inspired; we don't need
its two-part curve). Named motions: skeleton→content crossfade (`fast`), cache-first "Updating…" pulse,
disclosure expand/collapse (`slow`). **`prefers-reduced-motion` disables all** (the `SkeletonCard` shimmer
already honors this — extend the pattern).

## I.7 Voice & content

NN/g error rules: explicit, human, polite, constructive, calm; reserve firm color for real barriers.

- **Banned-builder-noun glossary** (Law 4) — enforced by lint in WP-6:
  | Banned | Say instead |
  |--------|-------------|
  | Curation / Curated | (a plain greeting, or nothing) |
  | Adjust | Edit day, place or party |
  | N checks / Checked N sources | "Conditions look clear" (+ evidence on tap) |
  | frame / context / personal context | (name what actually happened) |
  | fetched / not fetched | "not required here" / "unavailable right now" |
  | Couldn't verify: X | "X is unavailable right now — everything else checked out" |
  | options | trails |
- **State-message templates** (one per state; WP-6 owns the copy): clear / heads-up / blocked / unknown /
  empty-search / empty-filters / personalization-degraded / live-outage / stale-paint. Conclusion-first,
  ≤ 1 sentence, name the one thing + the one next step.

## I.8 Elevation & depth

**Flat by default.** No card shadows. The only shadow token is `elevation.overlay` (the `Sheet` scrim).
Depth = ink ramp + hairline borders + spacing rhythm. This is how v0.2 answers "feels like a wireframe / a
bit flat" *without* adding color or shadow — it stays inside the calm-utility refusal.

---

# Part II — Component library

**How we spec a component:** *anatomy · variants · states · tokens consumed · a11y · the law it embodies ·
the file it lives in.* Storybook story = the visual acceptance contract; a11y is axe-clean per story.

### II.A Primitives (WP-1)

| Component | File (new/existing) | v0.2 spec |
|-----------|--------------------|-----------|
| **Text** | NEW `components/Text/` | The missing primitive. `<Text role="title" as="h3">`. Applies a `type.*` role (size+lh+weight+family+case) from one place. Retires raw-rem classes in `styles.css`. Embodies Law 5. |
| **Button** | NEW `components/Button/` (extract from `cardParts.tsx`) | Variants `primary`/`secondary`/`ghost`; sizes `sm`/`md`; states hover/press/focus(`focus.ring`)/disabled; min hit target 44px (Apple HIG). Sentence case. |
| **Icon** | existing `components/Icon/` | Wire `check`/`triangle-alert`/`layers`; add tier→glyph map. No API change. |
| **MetricRow** | existing `cardParts.tsx` `DecisionFacts` | Re-token to `type.metric` (mono, tabular) + `type.metric-label` (sentence, muted). Missing values render **named** ("time unavailable"), never `—`. |
| **Chip / Toggle / OptionGroup / Sheet** | existing `components/` | No structural change; re-token to v0.2. |

### II.B Composites

| Component | File | v0.2 spec | Law | WP |
|-----------|------|-----------|-----|-----|
| **ConditionStatus** engine | existing `screens/ConditionStates.tsx` + `cardParts.tsx#ConditionSilence` | Reconcile the six coverage states (`present/stale-degraded/no-hazard/no-data/unavailable/not-fetched`) → the 4 signal **tiers**: `no-hazard`→`clear`(silent); `present`(actionable)→`heads-up` or `blocked`; `no-data`/`unavailable`/`not-fetched`/`stale-degraded`→`unknown`(gray). Single source of the tier→color mapping. | 1,2,7 | 2 |
| **TrailCard** | existing `screens/RecommendationCard.tsx` | Restyle: **name leads**; status silent when `clear`; **one action zone** (kill separate "OPEN DETAIL" — tap card opens Detail); **no per-card weather** (area fact → area level, Law 3); mono metrics. | 1,3,5 | 2 |
| **EvidencePanel** | existing full table in `screens/Detail.tsx` | Progressive disclosure (NN/g): conclusion line ("Conditions look clear" / "Two things to know") + `<details>` sourced rows, each row colored by tier, provenance as `type.caption`. Keeps every source (Rule #1). | 2 | 3 |
| **ContextSentence** | existing `screens/FeedConditions.tsx` (`ContextRibbon`) | "For tomorrow morning near Cinnamon Bay, solo." + an **edit** affordance (retires "Adjust"/"Curation"). Area conditions collapse to one honest line. | 3,4 | 3 |
| **EmptyState** | NEW (extract from `Home.tsx` inline) | Search-no-match / filters-too-tight; each names the binding constraint + one **reset/loosen CTA** (answers "the search X has no clear reset"). | 4,6 | 4 |
| **SystemBanner** | NEW (extract from `Home.tsx#feed-alert-banner`) | Regional alert / live-outage / personalization-degraded. Calm, one sentence, constructive. Tiered color. | 6 | 4 |
| **Skeleton + UpdateChip** | existing `screens/SkeletonCard.tsx` | Skeleton only on true cold start. Add "Updating conditions…" chip shown during background revalidate. | 1 | 4 |
| **MapControls** | existing `screens/map/MapControls.tsx` | Re-token base-layer chips to Button/Chip; sentence case; `layers` glyph. | 5 | 3 |

### II.C Reconciling the honesty primitives

`Confidence` (freshness·authority·corroboration → stated/hedged/flagged) and `Staleness` (demote, never
reorder) are **kept as-is** and remain the mechanism for Rule #1 / Rule #2 — v0.2 does **not** delete them.
The subtraction (Law 1) removes *repetition and shouting*, not the trust machinery. Where the mock appears
to "delete" a check, the fact moves into `EvidencePanel` (still sourced + timestamped). **A builder must not
over-subtract** provenance to hit the aesthetic.

---

# Part III — The performance layer (the reload fix)

## III.1 Corrected root cause (D4)

The scan showed the reload skeleton you felt is **not** server cold-start (Render is now a paid **$7 Starter**
that does not spin down). It is:

1. **Signed-in viewers are excluded from the SWR cache.** `frontend/src/data/PlannerProvider.tsx#useFeed`
   seeds synchronously from `frontend/src/data/feedCache.ts`, but `hydrateStale()` returns `null` unless
   `viewerId === 'anonymous'`. So signed-in reloads refetch cold and show `SkeletonCard`.
2. The `/plan` (+ `/plan/conditions`) round-trip itself, with nothing painted meanwhile.

## III.2 Fix 1 — extend stale-while-revalidate to signed-in viewers (primary)

- **Namespace the cache slot by viewer:** `adventure-planner:feed-cache:<viewerId>` (today it's a single
  anon slot). Hydrate for *any* viewer; write on signed-in, non-empty, phase-2-complete feeds.
- **Privacy (Rule #5, private-by-default):** the signed-in feed is personal. Keep it in a viewer-namespaced
  local slot, **evict on sign-out**, and **never** persist granted/shared substrate — only the viewer's own
  derived feed. Honor `SCHEMA_VERSION`.
- **Honest stale-paint (Rule #1) is unchanged:** `toStalePaint` already strips every live/ephemeral fact and
  injects `stale-degraded` silence, so a repaint never shows a frozen hazard. Reuse verbatim.
- **Result:** signed-in reload paints the last feed in <300ms, no skeleton; conditions revalidate behind the
  "Updating…" chip.

## III.3 Fix 2 — HTTP caching (cheap revalidation)

Add `ETag` + `Cache-Control` to `GET /regions` and the `/plan` **shell** phase so the background revalidate
is a conditional `304`, not a full recompute. Consider `stale-while-revalidate` in `Cache-Control`. The
ephemeral `/plan/conditions` overlay stays uncached (Rule #3 — fetched JIT).

## III.4 Fix 3 — cold-start (downgraded to belt-and-suspenders)

Paid Starter keeps the service warm, so the `loadingStages.ts` ladder ("Reading…"→"Still checking…"→"Waking
the server…") should rarely reach "Waking." **Re-tune the ladder thresholds down** (warm responses are fast)
and **verify no accidental scale-to-zero** on the Render plan. A keep-warm ping is optional and only guards
post-deploy/idle edges — not required for the reload symptom.

## III.5 Rendering strategy & budget

Cache-first instant paint for **all** viewers; two-phase overlay unchanged (Epic 040); skeleton only on the
true first-ever visit. **Budget:** reload-to-first-paint **< 300ms** (from cache); INP **< 200ms**; LCP
**< 1.5s** warm. Add a perf-guard test alongside `codeSplit.test.ts`. Keep the map lazy-load (already a
separate ~1MB chunk) — do not regress it.

---

# Part IV — Governance & delivery

## IV.1 The two frozen contracts (the key to safe parallelism)

WP-0 produces and **freezes** two interface files before any component work forks:
- **Contract A — tokens:** the semantic token names (Appendix B). No agent edits tokens after freeze.
- **Contract B — component APIs:** TS prop types + data shapes, incl. `type ConditionTier = 'clear' |
  'unknown' | 'headsUp' | 'blocked'`, `TrailCardModel`, `EvidenceItem`, `SystemBannerModel`. Agents code
  against these types in isolated worktrees → zero merge conflict.

## IV.2 Acceptance (per component)

Storybook story covering every variant × state (incl. dark theme) · axe-clean · unit test · **tests before
callers** (dev-process rule) · visual match to the referenced mock section · WCAG AA verified for any new
color. Targeted self-review per epic (not `/code-review ultra`); fix every CRITICAL before commit.

## IV.3 Work packages, sequencing & agent map

| WP | Scope | Owner · model | Depends |
|----|-------|---------------|---------|
| **0** | Tokens v0.2 (IBM Plex self-host, 4-tier signal, tokenized line-heights, mono metric role, drift reconcile) + freeze Contracts A & B + this spec | **Claude Sonnet**, PO-supervised | — |
| **1** | Primitives: Text, Button, Icon glyphs, MetricRow | Claude **Haiku** | 0 |
| **2** | ConditionStatus 4-tier engine + TrailCard restyle | **Gemini 3.1 Pro — A** | 0,1 |
| **3** | Detail restyle + EvidencePanel + ContextSentence + MapControls | **Gemini 3.1 Pro — B** | 0,1 |
| **4** | EmptyState + SystemBanner + Skeleton/UpdateChip | Claude Haiku/Sonnet | 0,1 |
| **5** | Perf: signed-in feed cache + HTTP caching + ladder re-tune | Claude **Sonnet** | 0 (else independent) |
| **6** | Voice: glossary lint + state-message templates + microcopy | Claude **Haiku** | 0 |
| **7** | Assembly (Feed+Detail) + WCAG/contrast audit + QA vs mocks + review | Claude Sonnet + PO (**merge desk**) | all |

| Wave | Parallel |
|------|----------|
| **0** | WP-0 alone (blocking) |
| **1** | WP-1 ‖ WP-5 ‖ WP-6 |
| **2** | WP-2 (Gemini-A) ‖ WP-3 (Gemini-B) ‖ WP-4 |
| **3** | WP-7 (single merge desk) |

**Merge discipline:** one worktree per WP (`.claude/worktrees/`), **single merge desk** (one integrator
branch), frozen Contracts A+B, Storybook story as the visual gate. Mirrors the overnight-run learnings.

## IV.4 Epic map (created BACKLOG→DEFINED at kickoff)

047 DS-v0.2 foundations (WP-0) · 048 Primitives (WP-1) · 049 ConditionStatus+Card (WP-2) · 050
Detail+Evidence (WP-3) · 051 System states (WP-4) · 052 Signed-in cache + HTTP caching (WP-5) · 053 Voice
(WP-6) · 054 Assembly+audit (WP-7). Chunks: 047–051/053/054 = **Look & feel**; 052 = **Guardrails & groundwork**.

---

## Appendix A — v0.1 → v0.2 drift reconciliation

| Drift found in scan | Resolution in v0.2 |
|---------------------|--------------------|
| v0.1 §5.2 type scale (`dataMicro…display`) ≠ shipped Epic-019 roles (`name/verdict/fact-value/…`) | I.3 defines the **single** canonical role scale; both prior sets are superseded. |
| §4.1 lists `neutral.500 = #6b7178`; shipped token is `#5e636a` (AA-darkened) | `#5e636a` is canonical (asserted in `typeScale.test.ts`). Fix the doc value. |
| §5.1 mandates mono "cartographic" data voice; shipped is all-sans | D2 **ships it** — mono for metrics only. |
| Font is `system-ui`, not a brand face | D3 adopts **IBM Plex** (self-hosted). |
| Single `signal.caution` (terracotta), no severity scale | D1 introduces the **4-tier** system; `signal.caution` deprecated and re-sorted. |
| Line-heights hardcoded in `styles.css` | I.3 **tokenizes** them (`lineHeight.tight/snug/normal/relaxed`). |
| Epic-019 migration partial (raw rems linger) | WP-1 `Text` primitive + WP-7 retire the stragglers. |
| Doc predates two-phase render / feed cache / `ConditionStates` / `Icon`/`glyphs` / water fact | Parts II & III cover them as first-class. |

## Appendix B — token deltas (DTCG, for WP-0)

```jsonc
// primitive.json — additions
"color": {
  "amber":      { "600": { "$value": "#8a6a16" },   // NEW — VERIFY AA ≥4.5:1 on canvas + raised
                  "alpha": { "10": { "$value": "rgba(138,106,22,0.10)" } } }
  // terracotta.600 (#9a4424) retained — now the `blocked` hue
},
"lineHeight": {                                        // NEW — tokenize what styles.css hardcoded
  "tight":   { "$value": "1.2" },  "snug":    { "$value": "1.3" },
  "normal":  { "$value": "1.45" }, "relaxed": { "$value": "1.5" }
},
"font": { "family": {
  "sans": { "$value": "'IBM Plex Sans', system-ui, -apple-system, 'Helvetica Neue', Arial, sans-serif" },
  "mono": { "$value": "'IBM Plex Mono', ui-monospace, SFMono-Regular, Menlo, monospace" }
}},
"space": { "10": { "$value": "40px" }, "11": { "$value": "48px" }, "12": { "$value": "64px" } },
"duration": { "slow": { "$value": "240ms" } }

// semantic.json — 4-tier signal + tokenized type line-heights
"signal": {
  "unknown":  { "fg": { "$value": "{text.muted}" } },
  "headsUp":  { "fg": { "$value": "{color.amber.600}" },      "bg": { "$value": "{color.amber.alpha.10}" } },
  "blocked":  { "fg": { "$value": "{color.terracotta.600}" }, "bg": { "$value": "{color.terracotta.alpha.10}" } }
  // signal.caution: DEPRECATED — migrate call sites to headsUp | blocked
},
"type": {
  // each role now carries size + lineHeight + weight (+ family/case documented in I.3)
  "display":      { "size": {"$value":"1.75rem"},   "lineHeight": {"$value":"{lineHeight.tight}"},  "weight": {"$value":"{font.weight.semibold}"} },
  "title":        { "size": {"$value":"1.25rem"},   "lineHeight": {"$value":"{lineHeight.snug}"},   "weight": {"$value":"{font.weight.semibold}"} },
  "lead":         { "size": {"$value":"1.125rem"},  "lineHeight": {"$value":"{lineHeight.normal}"}, "weight": {"$value":"{font.weight.regular}"} },
  "body":         { "size": {"$value":"1rem"},      "lineHeight": {"$value":"{lineHeight.relaxed}"},"weight": {"$value":"{font.weight.regular}"} },
  "body-sm":      { "size": {"$value":"0.875rem"},  "lineHeight": {"$value":"{lineHeight.normal}"}, "weight": {"$value":"{font.weight.regular}"} },
  "metric":       { "size": {"$value":"1rem"},      "lineHeight": {"$value":"{lineHeight.snug}"},   "weight": {"$value":"{font.weight.medium}"},   "family": {"$value":"{font.family.mono}"} },
  "metric-label": { "size": {"$value":"0.75rem"},   "lineHeight": {"$value":"{lineHeight.snug}"},   "weight": {"$value":"{font.weight.medium}"} },
  "caption":      { "size": {"$value":"0.75rem"},   "lineHeight": {"$value":"{lineHeight.snug}"},   "weight": {"$value":"{font.weight.regular}"} },
  "overline":     { "size": {"$value":"0.6875rem"}, "lineHeight": {"$value":"{lineHeight.snug}"},   "weight": {"$value":"{font.weight.medium}"} }
}
```
> Dark-theme variants (`amber` lighter, signal bg alphas) authored in WP-0 alongside the light set.
