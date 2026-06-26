# Design System Contract — v0.1

**Status:** Draft contract. **Stack ratified (2026-06): Adobe-grade** — DTCG + Style Dictionary token spine, React Aria behavior, vanilla-extract styling, owned components, Storybook. **Phases 1–4 of §9.2 are now built** (token spine · typed theme + `Signal` · React Aria `Sheet`/`Toggle`/`OptionButton` · Storybook); §9 defines the build sequence and §9.2 the per-phase status.
**Scope:** Operationalizes `decision-log.md §20` (token-first; one source → Tailwind/web + SwiftUI/native; shadcn/ui + Radix on web; confidence/staleness/verify as first-class UI states).
**Provenance:** Extracted from the validated `Home / Curation` v0.3 prototype, not invented ahead of it. Where this doc cites a value, it is the value the prototype already shipped in `frontend/src/styles.css`.

This is the artifact we previously skipped. Until it exists and is satisfied, "the design system" is not a deliverable — it's ad-hoc CSS variables. §14 defines the checkable bar for "the system exists."

---

## 1. Why this exists (the gap it closes)

The prototype's `:root` block is a **flat bag of raw variables** — `--paper`, `--ink`, `--signal`, `--r` — used directly as text, border, and stroke with no semantic layer, no scales, no honesty-primitive model, and no path to native. That is tokens-shaped, not a system.

This contract fixes four specific failures:

1. **No layering** — primitives, semantic roles, and component values were collapsed into one tier.
2. **No scales** — type/space/motion were hand-typed per rule.
3. **No honesty primitives as a system** — the product's signature (confidence/staleness/verify) existed only as one hardcoded caution class.
4. **No single cross-platform source of truth** — values lived in CSS only; no SwiftUI path.

---

## 2. Principles

- **Token-first, single source of truth.** Tokens are authored once and emitted to every platform. No platform hand-edits values.
- **Three layers, one-directional references.** Components reference *semantic* tokens; semantic tokens reference *primitives*; primitives reference nothing. Components **never** reference primitives directly.
- **Semantic over raw.** A component asks for `text.primary`, never `ink.900`.
- **Honesty primitives are first-class.** Confidence, staleness, and verify-before-you-go are token-backed states, not per-screen improvisation (`decision-log §20`).
- **Accent is signal, not chrome.** The single non-neutral hue is reserved for the verify/caution signal. Buttons, links, and decoration stay neutral.
- **Calm, cartographic, matte.** Flat surfaces, hairline rules, ink-on-paper, monospaced data labels. No glassmorphism, no gradient-as-decoration, no glow.
- **Quiet motion.** Tight, press-first, sub-160ms. Motion confirms touch; it does not perform.

---

## 3. Token architecture

### 3.1 Layers and naming

| Layer | Purpose | Naming | Example |
|---|---|---|---|
| **Primitive (reference)** | Raw values, no meaning | `category.scaleStep` | `color.neutral.900`, `space.4`, `size.lg` |
| **Semantic (system)** | Roles that carry meaning | `role.variant` | `text.primary`, `surface.raised`, `signal.caution.fg` |
| **Component** | Per-component bindings | `component.part[.state]` | `card.surface`, `signal.border`, `toggle.switch.on.bg` |

Rules:
- A component token resolves to a semantic token. A semantic token resolves to a primitive. Never skip or reverse.
- No literal colors, sizes, or durations in component CSS/JSX once migrated (§14).
- Token names are platform-neutral (no `px`, no `rem` in the name).

### 3.2 The three layers at a glance

```
primitive            semantic                     component
─────────────        ────────────────────         ──────────────────────
color.neutral.50  →  surface.canvas            →  app.background
color.neutral.0   →  surface.raised            →  card.surface, sheet.surface
color.neutral.900 →  text.primary              →  card.name, context.text
color.terracotta.600 → signal.caution.fg       →  signal.fg, frame.note.fg
space.4           →  space.inset.card          →  card.padding
size.lg           →  type.cardPlace.size       →  (card place line)
```

---

## 4. Color

### 4.1 Primitives (extracted from the prototype)

Neutral ramp (warm paper → ink):

| Token | Value | Source |
|---|---|---|
| `color.neutral.50` | `#f4f3ef` | `--paper` |
| `color.neutral.25` | `#fbfaf7` | `--paper-raised` |
| `color.neutral.100` | `#ecebe4` | `--paper-press` |
| `color.neutral.500` | `#6b7178` | `--ink-3` |
| `color.neutral.700` | `#3c424a` | `--ink-2` |
| `color.neutral.900` | `#16191d` | `--ink` |
| `color.neutral.alpha.14` | `rgba(22,25,29,0.14)` | `--line` |
| `color.neutral.alpha.08` | `rgba(22,25,29,0.08)` | `--line-soft` |

Signal ramp (terracotta — the only hue):

| Token | Value | Source |
|---|---|---|
| `color.terracotta.600` | `#ad4f2a` | `--signal` |
| `color.terracotta.alpha.10` | `rgba(173,79,42,0.10)` | `--signal-soft` |

> v0.1 is intentionally a near-monochrome + one signal hue. Adding a second accent requires a contract amendment, not a one-off.

### 4.2 Semantic mapping

| Semantic token | → primitive | Meaning |
|---|---|---|
| `surface.canvas` | `color.neutral.50` | app background |
| `surface.raised` | `color.neutral.25` | cards, sheets, fields |
| `surface.press` | `color.neutral.100` | active/pressed surface |
| `text.primary` | `color.neutral.900` | primary reading + data values |
| `text.secondary` | `color.neutral.700` | supporting prose (fit line, prose) |
| `text.muted` | `color.neutral.500` | labels, freshness, meta |
| `border.hairline` | `color.neutral.alpha.14` | default 1px edges |
| `border.faint` | `color.neutral.alpha.08` | internal dividers |
| `signal.caution.fg` | `color.terracotta.600` | verify/caution foreground |
| `signal.caution.bg` | `color.terracotta.alpha.10` | verify/caution field |
| `focus.ring` | `color.neutral.900` | keyboard focus (ink, not signal) |

### 4.3 Accessibility rules

- **Deterministic contrast.** Because surfaces are flat (no variable backdrop), every text/surface pairing has one contrast value. All `text.*` on `surface.canvas`/`surface.raised` must meet **WCAG AA (4.5:1 body, 3:1 ≥19px/bold)**. `text.muted` on `surface.raised` must be re-validated whenever the ramp changes.
- **Signal is never the only cue.** Caution conveys meaning through copy + structural placement, not color alone (color-blind safe). The signal hue reinforces; it never carries the message by itself.
- **Focus is visible and neutral.** `focus.ring` uses ink, so it reads on both surfaces and never competes with the signal.

---

## 5. Typography

### 5.1 Families

| Token | Stack | Use |
|---|---|---|
| `font.sans` | `system-ui, -apple-system, "Helvetica Neue", Helvetica, Arial, sans-serif` | headings, names, prose |
| `font.mono` | `ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace` | **all data + labels** (cartographic voice) |

**Rule:** Any value the user *reads as data* — drive time, distance, condition, freshness, kicker labels, the wordmark — is `font.mono`, uppercase, tracked `+0.08em`. Any value the user *reads as language* — place line, name, prose, fit — is `font.sans`.

> Open decision (§13): whether `font.sans` becomes a licensed cartographic display face. v0.1 uses the system grotesque to stay runnable offline; the contract treats the family as a token so swapping it is a one-line change.

### 5.2 Type scale

| Token | Size | Line height | Typical use (current → token) |
|---|---|---|---|
| `type.dataMicro` | 0.625rem / 10px | 1.2 | decision/condition/kicker labels |
| `type.label` | 0.6875rem / 11px | 1.2 | mono labels, wordmark, freshness |
| `type.meta` | 0.8125rem / 13px | 1.4 | area, source list, sparse note |
| `type.body` | 0.9375rem / 15px | 1.5 | fit line, prose, decision values |
| `type.emphasis` | 1rem / 16px | 1.4 | context sentence, facet labels |
| `type.placeLead` | 1.1875rem / 19px | 1.3 | card place line |
| `type.title` | 1.5rem / 24px | 1.1 | detail / section titles |
| `type.display` | `clamp(1.5rem, 6vw, 2rem)` | 1.05 | detail name |

Weights: `weight.regular 400`, `weight.medium 500`, `weight.semibold 600`. No light, no heavy.

> The prototype currently uses ~14 ad-hoc sizes (`0.62`–`1.16rem`). Migration (§14) snaps each to the nearest scale step.

---

## 6. Space, radius, stroke, elevation, motion

### 6.1 Space (4px base)

`space.0` 0 · `space.1` 4 · `space.2` 8 · `space.3` 12 · `space.4` 16 · `space.5` 20 · `space.6` 24 · `space.8` 32.

Semantic insets: `space.inset.card` = `space.4`, `space.inset.sheet` = `space.4`, `space.stack.gap` = `space.3`.

### 6.2 Radius

| Token | Value | Use |
|---|---|---|
| `radius.sm` | 8px (`--r-sm`) | fields, option/facet rows, terrain frame |
| `radius.md` | 10px (`--r`) | cards, sheets, context |
| `radius.pill` | 999px | the toggle switch only |

### 6.3 Stroke

| Token | Value | Use |
|---|---|---|
| `stroke.hairline` | 1px | borders, contour, glyph baseline |
| `stroke.line` | 1.5px | terrain glyph elevation line |
| `stroke.path` | 2px | detail elevation/route path |

### 6.4 Elevation

- `elevation.flat` — none. **Cards, fields, and rows use borders, never shadow.**
- `elevation.overlay` — `0 -2px 24px rgba(22,25,29,0.16)`. **Only overlays (sheets) may lift.** This is the single permitted shadow.

### 6.5 Motion

| Token | Value |
|---|---|
| `motion.fast` | 120ms |
| `motion.base` | 160ms |
| `motion.ease` | `cubic-bezier(0.2, 0, 0, 1)` |

Rules: interactions animate `background`/`border`/`opacity` only; **press/`:active` states are mandatory** (mobile-first); no transform-lift as the primary feedback; honor `prefers-reduced-motion` by dropping non-essential transitions.

---

## 7. Honesty primitives as first-class states (the crux)

These are the product's signature and the reason "token-first" was required (`decision-log §7, §20`; `outcome-card-ux.md`). Each is a **state model**, not a one-off style. The discipline is to render them **without clutter** — "the hedge is the honesty."

### 7.1 Confidence

- **Encodes:** freshness · authority · corroboration, rolled into one.
- **States:** `confidence.high | confidence.medium | confidence.low`.
- **Rendering contract:**
  - `high` → `text.primary`, plain statement, no chrome, no hedge.
  - `medium` → `text.secondary`, statement **+ hedge phrase** ("seems to", "usually").
  - `low` → `text.muted`, hedge phrase **+ its reason inline**, and on deeper surfaces an `marker.inferred` glyph (ⓘ).
- **Forbidden:** a **number** on any primary surface; badges/chrome by default; dressing an inference as a fact.
- **Token hooks:** `confidence.<tier>.text` (→ a `text.*` role) + a `hedge` content slot + `marker.inferred`.

### 7.2 Staleness

- **Encodes:** age relative to the fact's rate-of-change.
- **States:** `staleness.fresh | staleness.aging | staleness.stale`.
- **Rendering contract:** always a **relative-time string** ("48m old", "from a hike last fall"). Past the staleness threshold, presentation is **demoted** (`text.muted`, lighter weight) — it is **never reordered or buried**. Staleness demotes presentation, never rank.
- **Forbidden:** raw datetimes; any rank/visibility penalty driven by age.
- **Token hooks:** `staleness.format` (relative-time rule) + `staleness.stale.text` (demotion treatment).

### 7.3 Verify-before-you-go

- **Encodes:** a low-confidence, safety-relevant condition.
- **Rendering contract:** the inline **Signal** component — `signal.caution.fg` on `signal.caution.bg`, 2px `signal.caution.fg` left rule, one tier above body, placed **beside the decision facts** (not at the card bottom). Primary surface = one inline line; detail = fuller context + sources.
- **Forbidden:** banner, modal, toast, stoplight/severity palette, color-scream. This is the **only** place the signal hue appears.
- **Token hooks:** `signal.fg`, `signal.bg`, `signal.border`, `signal.inset`.

### 7.4 Cross-surface rule

| Surface | Confidence | Staleness | Verify |
|---|---|---|---|
| **Home / Curation** | implicit via wording tier; never numeric | one quiet relative line | one inline signal line |
| **Detail** | same tiers, more room for the reason | relative line + source basis | fuller context + sources |
| **Belief store (later)** | non-numeric dots allowed here only | relative + receipts | — |

---

## 8. Component contracts (token bindings)

Each prototype primitive declared in terms of tokens + states. Behavior (focus trap, roles, dismiss) comes from Radix/shadcn when adopted (§9); visuals always come from tokens.

| Component | Surface | Text | Border | States |
|---|---|---|---|---|
| `Card` | `surface.raised` | place=`type.placeLead`/`text.primary`; name=`text.primary`; fit=`text.secondary` | `border.hairline` | rest, `:active`→`surface.press` |
| `ContextSentence` | `surface.raised` | `text.primary` + `text.muted` adjust | `border.hairline` | rest, `:active` |
| `DecisionRow` | — | label=`text.muted`/mono; value=`text.primary`/mono | top `border.faint` | static |
| `ConditionValue` | — | label=`text.muted`; value=`text.primary`/mono | — | static |
| `Signal` | `signal.caution.bg` | `signal.caution.fg` | left `signal.caution.fg` | static (presence = verify state) |
| `Sheet` | `surface.canvas` | `text.primary` | `border.hairline` + `elevation.overlay` | open/closed |
| `FacetRow` / `OptionButton` | `surface.raised` | `text.primary`/`text.secondary` | `border.hairline`; selected→ink | rest, `:active`, selected |
| `Toggle` | `surface.raised` | `text.primary` | `border.hairline`; on→ink fill | off/on |
| `TerrainGlyph` / `TerrainPreview` | `surface.canvas` grid | path=`stroke.path`/`text.primary` | contour=`stroke.hairline`/`border.hairline` | static |

---

## 9. Source of truth, stack & rollout (ratified)

**Decision:** own the system end-to-end — **not** Tailwind, **not** copy-paste component kits. Adopted stack ("Adobe-grade"):

| Concern | Choice | Why |
|---|---|---|
| **Token format** | **W3C DTCG** JSON (`frontend/tokens/`) | Vendor-neutral standard; the only format that cleanly targets web *and* SwiftUI from one source. |
| **Transform** | **Style Dictionary v4** | Enterprise-standard token transformer; DTCG-native; multi-platform emit. |
| **Web emit** | CSS custom properties **+ a typed vanilla-extract theme contract** | Zero-runtime, type-safe theming; deterministic; no utility-class framework. |
| **Native emit (later)** | `DesignTokens.swift` from the same DTCG source | Additive; token names are platform-neutral. |
| **Accessibility / behavior** | **React Aria** (Adobe) | WAI-ARIA APG compliance, focus management, i18n; structurally prevents the nested-control class of bug. |
| **Components** | **Owned**, named, token-bound (`Card`, `Sheet`, `Signal`, …) | Our IP, versioned — not skinned defaults. |
| **Workbench / quality** | **Storybook** + axe/Playwright a11y + visual regression | The system is a product, with tests and docs. |
| **Governance** | semver + deprecation policy + this contract | Changes are reviewable and reversible. |

Tailwind is explicitly **not** the system. If it ever appears, it consumes generated tokens; it never defines them. This honors `decision-log §20` (one source → web + native) and the web-first sequencing in `CLAUDE.md`.

### 9.1 Pipeline

```
frontend/tokens/*.json            (DTCG source of truth)
        │  Style Dictionary v4
        ├─► src/design/tokens.css        (:root custom properties — web now)
        ├─► src/design/theme.css.ts      (vanilla-extract themeContract — typed)
        └─► (later) DesignTokens.swift   (SwiftUI / native)
```

### 9.2 Phased rollout (do not boil the ocean on a surface still in flux)

- **Phase 1 — Token spine.** ✅ **Shipped.** DTCG tokens (primitive→semantic) + Style Dictionary → `tokens.css`; the hand-written `:root` is replaced and the prototype renders identically but token-driven.
- **Phase 2 — Typed theme + reference component.** ✅ **Shipped.** `src/design/theme.css.ts` is the typed vanilla-extract contract (`createGlobalThemeContract` over the generated vars — Style Dictionary still owns values). `Signal` is the first owned, token-bound component and the sole carrier of the accent hue. *(Confidence and Staleness remain to be built as components; only the verify primitive is done.)*
- **Phase 3 — React Aria primitives.** ✅ **Shipped.** `Sheet` / `Toggle` / `OptionButton` rebuilt on React Aria (real focus trap, Escape/scrim dismiss, focus return, roving single-select, role=switch); bespoke focus/dismiss handling retired.
- **Phase 4 — Workbench.** ✅ **Shipped (local).** Storybook 10 (react-vite) with the axe a11y addon and stories for every owned component; static build verified. *(CI integration + visual-regression remain.)*

Each phase is one logical change (`AGENTS.md`).

---

## 10. Governance

- **Versioning:** this doc is the contract; bump `vX.Y` on token additions/renames. Renames require a migration note.
- **Change rule:** new component → new *component tokens* referencing existing semantics; only add a *primitive* when no semantic can express the need; only add a *semantic* when a genuinely new role appears.
- **No raw values** in component code after migration (§14) — enforced by review, later by lint.
- **One logical change per PR** (`AGENTS.md`): tokens source, then each component refactor, separately.

---

## 11. Anti-patterns (explicitly out)

- Glassmorphism, backdrop blur, gradient-as-decoration, glow shadows.
- Accent/signal hue on buttons, links, or chrome.
- Numeric confidence on primary surfaces.
- Raw datetimes; age-driven rank changes.
- Caution as banner/modal/stoplight.
- Components referencing primitive tokens directly.
- A second accent hue without a contract amendment.

---

## 12. Migration map (current `:root` → layered tokens)

No code changes in this doc; this is the exact bridge for the follow-up refactor.

| Current var (`styles.css`) | Primitive | Semantic |
|---|---|---|
| `--paper` | `color.neutral.50` | `surface.canvas` |
| `--paper-raised` | `color.neutral.25` | `surface.raised` |
| `--paper-press` | `color.neutral.100` | `surface.press` |
| `--ink` | `color.neutral.900` | `text.primary` |
| `--ink-2` | `color.neutral.700` | `text.secondary` |
| `--ink-3` | `color.neutral.500` | `text.muted` |
| `--line` | `color.neutral.alpha.14` | `border.hairline` |
| `--line-soft` | `color.neutral.alpha.08` | `border.faint` |
| `--signal` | `color.terracotta.600` | `signal.caution.fg` |
| `--signal-soft` | `color.terracotta.alpha.10` | `signal.caution.bg` |
| `--r` / `--r-sm` | `radius.md` / `radius.sm` | — |
| `--sans` / `--mono` | `font.sans` / `font.mono` | — |
| ad-hoc font sizes | `type.*` scale | per component |
| ad-hoc paddings/gaps | `space.*` scale | `space.inset.*`, `space.stack.gap` |
| `130ms` literals | `motion.fast` | — |

**Refactor steps (separate change):** (1) add the DTCG token source + Style Dictionary config + npm script; (2) replace `:root` with generated vars; (3) snap component font-sizes/spacing to scale tokens; (4) extract `Signal`, `DecisionRow`, `ConditionValue`, `Sheet` as token-bound components; (5) add the confidence/staleness state hooks where data exists.

---

## 13. Decisions

**Resolved (2026-06):**
- **Stack** — Adobe-grade: DTCG + Style Dictionary, React Aria, vanilla-extract, owned components, Storybook (§9). Tailwind rejected as the system layer; shadcn/copy-paste kits rejected.
- **Generator** — Style Dictionary v4 (not hand-rolled); DTCG-native, enterprise emit.

**Still open (defaults stand until decided):**
- **Heading family** — licensed cartographic display face vs. system grotesque for v1. *Default:* tokenized system grotesque; swapping it is a one-token change.
- **Color scheme** — light-only v1 vs. dark in parallel. *Default:* light-only v1; dark becomes a second vanilla-extract theme (cheap once the contract exists).
- **Density** — single density v1 vs. a density theme dimension now. *Default:* single density; architect the token contract so density can be added later without renames.

---

## 14. Definition of done for "the design system exists"

The requirement is satisfied when:

- **[d1]** Tokens are authored in **one DTCG source** and emitted via Style Dictionary to web (CSS vars + typed vanilla-extract theme) now, with the SwiftUI emitter path defined.
- **[d2]** **Three layers** exist with one-directional references; components bind to semantic/component tokens only.
- **[d3]** **No raw color/size/duration literals** remain in component code.
- **[d4]** **Type, space, radius, stroke, motion scales** are defined and used (no ad-hoc values).
- **[d5]** **Confidence, staleness, verify** each have token-backed states with the rendering + forbidden rules in §7.
- **[d6]** **Contrast AA** holds for every text/surface pairing; signal is never color-only.
- **[d7]** This contract is versioned and cross-referenced from `decision-log §20` and the prototype spec.

Until d1–d7 hold, we treat the design system as **not done** — which is the requirement we were missing.
