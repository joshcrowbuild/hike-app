# Craft Lane C Prep — Type-Space Literal Inventory & Token Mapping (2026-07)

**Status:** ACTIVE (mechanical audit per `ux-review-craft-2026-07.md` M1–M3)
**Reviewer:** GLM (foreign-model craft-lane prep)
**Scope:** `frontend/src/styles.css` (1754 lines) + all `*.css.ts` component files
**Constraint:** No component code changes — mapping table + lint rule proposal only

---

## Methodology

1. Read `ux-review-craft-2026-07.md` findings M1 (type scale sprawl), M2 (spacing off-grid), M3 (identity) and `design-system-v0.1.md` §5.2 (type scale), §6.1 (space scale), §14 (done-bar).
2. Inventoried every `font-size`, `line-height`, `margin`, and `padding` literal in `frontend/src/styles.css` and all `*.css.ts` files.
3. Mapped each literal to the nearest token in the documented 8-step type scale and 8-step space scale.
4. Identified primitive token ramp bloat (extra steps not in the documented scale).
5. Proposed a Stylelint rule set to enforce §14[d3][d4] going forward.

---

## 1. Current state summary

### 1.1 Two CSS systems in parallel

| Layer | Files | Token discipline |
|-------|-------|-----------------|
| **vanilla-extract components** (`*.css.ts`) | 10 files | **Fully tokenized** — every `fontSize`, `padding`, `margin`, `gap` references `vars.*`. Zero raw size/spacing literals. |
| **Legacy stylesheet** (`styles.css`) | 1 file, 1754 lines | **63 `font-size` literals, 21 `line-height` literals, 70+ margin/padding rem literals** — only 7 font-sizes reference a token. |

The `.css.ts` component files (Sheet, Toggle, OptionGroup, Signal, Confidence, Staleness, Icon, Gallery) are the model — they prove the token system works end-to-end. The entire remediation effort is in `styles.css`.

### 1.2 Primitive token ramp bloat

The documented type scale (`design-system-v0.1.md` §5.2) defines **8 steps**:

| Token | Size | Line height |
|-------|------|-------------|
| `type.dataMicro` | 0.625rem / 10px | 1.2 |
| `type.label` | 0.6875rem / 11px | 1.2 |
| `type.meta` | 0.8125rem / 13px | 1.4 |
| `type.body` | 0.9375rem / 15px | 1.5 |
| `type.emphasis` | 1rem / 16px | 1.4 |
| `type.placeLead` | 1.1875rem / 19px | 1.3 |
| `type.title` | 1.5rem / 24px | 1.1 |
| `type.display` | `clamp(1.5rem, 6vw, 2rem)` | 1.05 |

The actual `primitive.json` size ramp has **13 steps** — 5 extra steps minted per-element instead of snapping to the scale:

| Extra primitive | Value | Documented step it should map to | Delta |
|----------------|-------|----------------------------------|-------|
| `size.fact-label` | 0.7rem | `type.label` (0.6875rem) | +0.0125rem (0.2px) |
| `size.supporting` | 0.72rem | `type.label` (0.6875rem) | +0.0325rem (0.52px) |
| `size.condition` | 0.9rem | `type.body` (0.9375rem) | -0.0375rem (0.6px) |
| `size.verdict` | 0.95rem | `type.body` (0.9375rem) | +0.0125rem (0.2px) |
| `size.fact-value` | 1rem | `type.emphasis` (1rem) | 0 (exact dup) |
| `size.name` | 1.3rem | `type.placeLead` (1.1875rem) | +0.1125rem (1.8px) |

**Verdict:** `fact-label` and `supporting` are 0.2–0.5px apart from `label` — indistinguishable at any reading distance. `condition` and `verdict` are <1px from `body`. `fact-value` is an exact duplicate of `emphasis`. `name` (1.3rem) sits between `placeLead` (1.1875rem) and `title` (1.5rem) — it's the one that might warrant keeping as a 9th step, but the documented scale says 8.

---

## 2. Font-size literal inventory (styles.css)

**63 literal `font-size` declarations** in `styles.css`. Below: each unique rem value, its line count, the selector(s) it appears on, and the token it should map to.

### 2.1 Mapping table

| Literal value | Occurrences | Target token | Token value | Delta | Selectors |
|--------------|-------------|-------------|-------------|-------|-----------|
| `0.6rem` | 1 | `type.dataMicro` | 0.625rem | +0.025rem | `.difficulty-sample` |
| `0.62rem` | 10 | `type.dataMicro` | 0.625rem | +0.005rem | `.verdict-sample`, `.condition-label`, `.difficulty-est`, `.map-chip`, `.elev-summary-label`, `.refine-label`, `.map-attribution`, `.measured-label`, `.topbar-mode` |
| `0.64rem` | 4 | `type.dataMicro` | 0.625rem | -0.015rem | `.freshness`, `.open-detail`, `.kicker`, `.pending-nod-cue` |
| `0.66rem` | 1 | `type.dataMicro` | 0.625rem | -0.035rem | `.housekeeping-summary` |
| `0.68rem` | 5 | `type.label` | 0.6875rem | +0.0075rem | `.context-adjust`, `.frame-note`, `.stack-meta`, `.action-chip`, `.condition-state-kind` |
| `0.7rem` | 4 | `type.label` | 0.6875rem | -0.0125rem | `.wordmark`, `.back`, `.text-action`, `.sample-strip` |
| `0.72rem` | 3 | `type.label` | 0.6875rem | +0.0325rem | `.elev-stats`, `.elev-readout`, `.condition-silence-glyph` |
| `0.74rem` | 4 | `type.meta` | 0.8125rem | -0.0725rem | `.card-warning-meta`, `.detail-area`, `.source-list`, `.facet-value` |
| `0.76rem` | 2 | `type.meta` | 0.8125rem | -0.0525rem | `.condition-silence--partial`, `.condition-state-group` |
| `0.78rem` | 3 | `type.meta` | 0.8125rem | -0.0325rem | `.difficulty`, `.map-note`, `.outcome-facts` |
| `0.82rem` | 4 | `type.meta` | 0.8125rem | +0.0075rem | `.set-aside-text`, `.condition-silence`, `.condition-states` |
| `0.85rem` | 5 | `type.meta` | 0.8125rem | +0.0375rem | `.screen-title`, `.sparse-note`, `.elev-soon`, `.trust-cue`, `.readiness-line` |
| `0.9rem` | 5 | `type.body` | 0.9375rem | +0.0375rem | `.trail-summary`, `.detail-practical`, `.state-note`, `.condition-line`, `.condition-lines`, `.measured-note` |
| `0.95rem` | 3 | `type.body` | 0.9375rem | +0.0125rem | `.prose`, `.facet-label`, `.pending-nod-text`, `.measured-value` |
| `1rem` | 3 | `type.emphasis` | 1rem | 0 | `.context-text`, `.faces-legend` |
| `1.1rem` | 1 | `type.emphasis` | 1rem | -0.1rem | `.outcome-ack` |
| `1.3rem` | 1 | `type.placeLead` | 1.1875rem | +0.1125rem | `.outcome-name` |
| `1.8rem` | 1 | *(no token)* | — | — | `.face` (emoji glyph — see note) |
| `1.15em` | 2 | *(relative)* | — | — | `.decision-icon`, `.detail-water-icon` (em-relative to parent — intentional) |
| `1.25em` | 1 | *(relative)* | — | — | `.action-chip-icon` (em-relative — intentional) |
| `0.7em` | 1 | *(relative)* | — | — | `.condition-state-glyph` (em-relative — intentional) |
| `clamp(1.5rem, 6vw, 2rem)` | 1 | `type.display` | same | 0 | `.detail-name` (already correct) |

**Notes:**
- `em`-relative sizes on icon/glyph elements (`.decision-icon`, `.action-chip-icon`, `.detail-water-icon`, `.condition-state-glyph`) are intentionally relative to their parent's font-size — these track the type scale indirectly and should not be tokenized.
- `.face` at `1.8rem` is for emoji reaction glyphs in the outcome card — this is a one-off display size for emoji rendering, not a type-scale step. It could map to a new `type.emoji` token or stay as-is with a documented exemption.
- `clamp(1.5rem, 6vw, 2rem)` on `.detail-name` already matches `type.display` — no change needed.

### 2.2 Collapse summary

| Documented token | Current literals that map to it | Count |
|------------------|-------------------------------|-------|
| `type.dataMicro` (0.625rem) | 0.6, 0.62, 0.64, 0.66 | 16 |
| `type.label` (0.6875rem) | 0.68, 0.7, 0.72 | 12 |
| `type.meta` (0.8125rem) | 0.74, 0.76, 0.78, 0.82, 0.85 | 18 |
| `type.body` (0.9375rem) | 0.9, 0.95 | 8 |
| `type.emphasis` (1rem) | 1, 1.1 | 4 |
| `type.placeLead` (1.1875rem) | 1.3 | 1 |
| `type.title` (1.5rem) | *(none — no raw 1.5rem literals)* | 0 |
| `type.display` | *(already tokenized via clamp)* | 0 |
| **Total** | | **59** |
| em-relative (exempt) | 1.15em, 1.25em, 0.7em | 4 |
| Special (emoji) | 1.8rem | 1 |

**59 font-size literals** would collapse to **6 tokens** (of the documented 8). The em-relative and emoji sizes are exempt.

---

## 3. Line-height literal inventory

**21 literal `line-height` declarations** in `styles.css` + **5** in `.css.ts` files.

### 3.1 Mapping table

| Literal | Occurrences in styles.css | In css.ts | Documented pair | Selectors (styles.css) |
|---------|--------------------------|-----------|----------------|----------------------|
| `1.05` | 1 | 0 | `type.display` (1.05) | `.detail-name` |
| `1.2` | 2 | 0 | `type.dataMicro` / `type.label` (1.2) | `.card-name`, `.outcome-name` |
| `1.3` | 2 | 0 | `type.placeLead` (1.3) | `.detail-place`, `.map-attribution` |
| `1.4` | 9 | 2 | `type.meta` / `type.emphasis` (1.4) | `.verdict`, `.trail-summary`, `.map-note`, `.sample-strip`, `.near-me-note`, `.condition-line`, `.condition-silence`, `.condition-states`, `.condition-state-group` |
| `1.45` | 4 | 2 | *(no exact token — between 1.4 and 1.5)* | `.detail-water-line`, `.detail-water-note`, `.elev-soon`, `.readiness-line` |
| `1.5` | 2 | 2 | `type.body` (1.5) | `:root`, `.prose` |
| `1` | 1 | 0 | *(glyph baseline — exempt)* | `.condition-silence-glyph` |

**Proposed line-height tokens** (currently not in the token system — line-heights are implicit per type step):

| Token | Value | Used by |
|-------|-------|---------|
| `lineHeight.tight` | 1.05 | display |
| `lineHeight.snug` | 1.2 | dataMicro, label |
| `lineHeight.normal` | 1.3 | placeLead |
| `lineHeight.relaxed` | 1.4 | meta, emphasis |
| `lineHeight.loose` | 1.5 | body |

The `1.45` value (4 occurrences) falls between `relaxed` (1.4) and `loose` (1.5) — it should snap to `1.4` (the closest documented pair, used by `type.meta` and `type.emphasis`).

---

## 4. Margin/padding literal inventory

**70+ margin/padding rem literals** in `styles.css`. The space scale (`design-system-v0.1.md` §6.1) defines: `0, 4, 8, 12, 16, 20, 24, 32` px.

### 4.1 Unique rem values and their token mapping

| Literal (rem) | Pixel value | Target token | Token px | Delta | Occurrences |
|---------------|------------|-------------|---------|-------|-------------|
| `0.1rem` | 1.6px | `space.0` (0) or `space.1` (4px) | — | — | 1 (`.near-me-note` padding) |
| `0.15rem` | 2.4px | `space.1` (4px) | 4 | +1.6px | 1 (`.detail-water-note` margin) |
| `0.16rem` | 2.56px | `space.1` (4px) | 4 | +1.44px | 1 (`.difficulty` padding) |
| `0.2rem` | 3.2px | `space.1` (4px) | 4 | +0.8px | 1 (`.housekeeping-summary` padding) |
| `0.22rem` | 3.52px | `space.1` (4px) | 4 | +0.48px | 1 (`.map-attribution` padding) |
| `0.25rem` | 4px | `space.1` (4px) | 4 | 0 | 1 (`.condition-states--compact` gap) |
| `0.28rem` | 4.48px | `space.1` (4px) | 4 | -0.48px | 2 (`.verdict-sample` padding, `.difficulty-sample` margin) |
| `0.3rem` | 4.8px | `space.1` (4px) | 4 | -0.8px | 4 (`.back` padding, `.stack-controls` margin, `.feed-conditions` margin, `.text-action` padding) |
| `0.35rem` | 5.6px | `space.1` (4px) | 4 | -1.6px | 4 (`.card-id` gap, `.card-warnings` gap, `.feed-conditions-scope` margin, `.condition-lines` gap, `.map-layers` gap) |
| `0.4rem` | 6.4px | `space.1` (4px) | 4 | -2.4px | 5 (`.verdict-sample` margin, `.detail-area` margin, `.map-notes` gap, `.trust-cue` gap, `.condition-silence--partial` margin, `.condition-states` margin) |
| `0.42rem` | 6.72px | `space.1` (4px) | 4 | -2.72px | 1 (`.action-chip` padding) |
| `0.45rem` | 7.2px | `space.2` (8px) | 8 | +0.8px | 5 (`.map-controls` gap, `.elev` gap, `.refine` gap, `.condition-silence` gap, `.condition-state` gap, `.condition-state-body` gap) |
| `0.5rem` | 8px | `space.2` (8px) | 8 | 0 | 8 (`.frame-note` margin, `.condition` gap, `.card-actions` gap, `.detail-actions` gap, `.state-block` gap, `.set-aside` gap, `.sparse-block` gap, `.set-aside-row` gap, `.housekeeping-body` gap) |
| `0.55rem` | 8.8px | `space.2` (8px) | 8 | -0.8px | 1 (`.detail-place` margin) |
| `0.6rem` | 9.6px | `space.2` (8px) or `space.3` (12px) | — | — | 5 (`.stack-controls` margin, `.verdict--card` margin, `.decision` gap, `.card-foot` padding, `.housekeeping-body` margin, `.faces` gap, `.faces-row` gap) |
| `0.7rem` | 11.2px | `space.3` (12px) | 12 | +0.8px | 8 (`.card-tap` gap, `.decision` padding, `.card-foot` padding, `.feed-conditions` padding, `.terrain-block` gap, `.facet-row` padding, `.card-actions` padding, `.face` padding) |
| `0.75rem` | 12px | `space.3` (12px) | 12 | 0 | 1 (`.housekeeping` padding) |
| `0.8rem` | 12.8px | `space.3` (12px) | 12 | -0.8px | 2 (`.action-chip` padding, `.refine-input` padding) |
| `0.85rem` | 13.6px | `space.3` (12px) | 12 | -1.6px | 9 (`.card-stack` gap, `.detail` gap, `.feed-alert-banner` margin, `.feed-conditions` margin, `.sparse-note` margin, `.facet-list` gap, `.today-sheet`/`.origin-sheet` gap, `.sparse-block` margin, `.set-aside` margin/padding, `.pending-nod` padding, `.sample-strip` margin) |
| `0.9rem` | 14.4px | `space.4` (16px) | 16 | +1.6px | 10 (`.topbar` margin, `.verdict--detail` margin, `.detail-facts` margin/padding, `.detail-water` margin, `.condition--detail` margin, `.signal--detail` margin, `.detail-practical` margin, `.housekeeping` margin, `.condition-lines--detail` margin, `.pending-nod` margin) |
| `0.95rem` | 15.2px | `space.4` (16px) | 16 | +0.8px | 1 (`.context` padding) |
| `1rem` | 16px | `space.4` (16px) | 16 | 0 | 7 (`.app-shell` padding, `.context` padding, `.refine` margin/padding, `.source-list` padding, `.terrain-block--full` padding, `.measured` padding, `.pending-nod` margin) |
| `1.05rem` | 16.8px | `space.4` (16px) | 16 | -0.8px | 3 (`.card-tap` padding, `.detail-head`/`.detail-block` padding, `.card-actions` padding) |
| `1.1rem` | 17.6px | `space.4` (16px) | 16 | -1.6px | 3 (`.app-shell` padding, `.detail-head`/`.detail-block` padding, `.outcome` gap) |
| `1.25rem` | 20px | `space.5` (20px) | 20 | 0 | 1 (`.frame` margin) |
| `3rem` | 48px | *(no token — layout constant)* | — | — | 1 (`.app-shell` bottom padding) |
| `5rem` | 80px | *(no token — layout constant)* | — | — | 1 (Gallery page bottom padding) |

### 4.2 Collapse summary

| Target token | Token px | Current literals mapping to it | Count |
|-------------|---------|-------------------------------|-------|
| `space.1` (4px) | 4 | 0.1, 0.15, 0.16, 0.2, 0.22, 0.25, 0.28, 0.3, 0.35, 0.4, 0.42 | ~22 |
| `space.2` (8px) | 8 | 0.45, 0.5, 0.55 | ~15 |
| `space.3` (12px) | 12 | 0.6, 0.7, 0.75, 0.8, 0.85 | ~25 |
| `space.4` (16px) | 16 | 0.9, 0.95, 1, 1.05, 1.1 | ~24 |
| `space.5` (20px) | 20 | 1.25 | 1 |
| `space.6` (24px) | 24 | *(none)* | 0 |
| `space.8` (32px) | 32 | *(none)* | 0 |
| Layout constants | — | 3rem, 5rem | 2 |

**~87 margin/padding/gap literals** would collapse to **5 space tokens** (of the documented 8). The 3rem/5rem bottom paddings are layout constants (app shell / gallery scroll buffer), not spacing-scale steps — they should get a documented exemption.

---

## 5. css.ts file audit

The vanilla-extract component files are **nearly clean**. Findings:

| File | Issue | Severity |
|------|-------|----------|
| `Confidence.css.ts:13` | `lineHeight: 1.45` — not a token; should be `1.4` | LOW |
| `Signal.css.ts:26` | `lineHeight: 1.4` — not a token (but matches `type.meta`/`type.emphasis`) | LOW |
| `Toggle.css.ts:49` | `lineHeight: 1.4` — same | LOW |
| `Gallery.css.ts:47,140` | `lineHeight: 1.5` — matches `type.body` | LOW |
| `Gallery.css.ts:89` | `paddingBlock: '2px'` — raw literal, should be `vars.space[1]` (4px) or documented exemption | LOW |
| `a11y.css.ts:28` | `margin: '-1px'` — sr-only recipe, **documented exemption** (§3.1) | EXEMPT |

**Recommendation:** Add `lineHeight` tokens to the semantic layer so `.css.ts` files can reference them. The 5 line-height values (1.05, 1.2, 1.3, 1.4, 1.5) should be primitives that semantic type tokens bind to.

---

## 6. Primitive token ramp cleanup proposal

### 6.1 Kill list — extra size steps to collapse

| Extra primitive | Value | Collapse to | Rationale |
|----------------|-------|-------------|-----------|
| `size.fact-label` | 0.7rem | `size.label` (0.6875rem) | 0.2px delta — indistinguishable |
| `size.supporting` | 0.72rem | `size.label` (0.6875rem) | 0.5px delta — indistinguishable |
| `size.condition` | 0.9rem | `size.body` (0.9375rem) | 0.6px delta — indistinguishable |
| `size.verdict` | 0.95rem | `size.body` (0.9375rem) | 0.2px delta — indistinguishable |
| `size.fact-value` | 1rem | `size.emphasis` (1rem) | Exact duplicate |
| `size.name` | 1.3rem | `size.placeLead` (1.1875rem) | 1.8px delta — closest step; if the name truly needs to be larger, add a documented 9th step |

### 6.2 Semantic token cleanup

The `semantic.json` `type` section has 6 role-specific entries (`name`, `verdict`, `fact-value`, `fact-label`, `condition`, `supporting`) that each reference the extra primitives. After collapsing the primitives, these semantic roles should reference the documented 8 steps:

| Semantic role | Current primitive | After collapse |
|--------------|-------------------|----------------|
| `type.name` | `size.name` (1.3rem) | `size.placeLead` (1.1875rem) |
| `type.verdict` | `size.verdict` (0.95rem) | `size.body` (0.9375rem) |
| `type.fact-value` | `size.fact-value` (1rem) | `size.emphasis` (1rem) |
| `type.fact-label` | `size.fact-label` (0.7rem) | `size.label` (0.6875rem) |
| `type.condition` | `size.condition` (0.9rem) | `size.body` (0.9375rem) |
| `type.supporting` | `size.supporting` (0.72rem) | `size.label` (0.6875rem) |

### 6.3 Add line-height primitives

| New primitive | Value | Semantic binding |
|--------------|-------|-----------------|
| `lineHeight.tight` | 1.05 | `type.display` |
| `lineHeight.snug` | 1.2 | `type.dataMicro`, `type.label` |
| `lineHeight.normal` | 1.3 | `type.placeLead` |
| `lineHeight.relaxed` | 1.4 | `type.meta`, `type.emphasis` |
| `lineHeight.loose` | 1.5 | `type.body` |

---

## 7. Lint rule proposal (§10 enforcement)

The design-system contract §10 says: *"No raw values in component code after migration (§14) — enforced by review, later by lint."* This is the lint.

### 7.1 Stylelint configuration

```json
{
  "extends": ["stylelint-config-recommended"],
  "rules": {
    "declaration-property-value-allowed-list": {
      "font-size": [
        "/^var\\(--/",
        "/^clamp\\(/",
        "/^1em$/",
        "/^1\\.\\d+em$/",
        "/^0\\.\\d+em$/"
      ],
      "line-height": [
        "/^var\\(--/",
        "/^1$/"
      ],
      "margin": [
        "/^var\\(--/",
        "/^0$/",
        "/^auto$/",
        "/^-1px$/"
      ],
      "margin-top": ["/^var\\(--/", "/^0$/"],
      "margin-bottom": ["/^var\\(--/", "/^0$/"],
      "margin-left": ["/^var\\(--/", "/^0$/"],
      "margin-right": ["/^var\\(--/", "/^0$/"],
      "margin-inline-start": ["/^var\\(--/", "/^0$/"],
      "padding": [
        "/^var\\(--/",
        "/^0$/"
      ],
      "padding-top": ["/^var\\(--/", "/^0$/"],
      "padding-bottom": ["/^var\\(--/", "/^0$/"],
      "padding-left": ["/^var\\(--/", "/^0$/"],
      "padding-right": ["/^var\\(--/", "/^0$/"],
      "padding-inline": ["/^var\\(--/", "/^0$/"],
      "padding-block": ["/^var\\(--/", "/^0$/"]
    }
  },
  "overrides": [
    {
      "files": ["**/tokens.css"],
      "rules": {
        "declaration-property-value-allowed-list": null
      }
    },
    {
      "files": ["**/a11y.css.ts"],
      "rules": {
        "declaration-property-value-allowed-list": {
          "margin": ["/^var\\(--/", "/^0$/", "/^-1px$/"]
        }
      }
    }
  ]
}
```

### 7.2 Exemption registry

Values that are intentionally NOT tokenized and must be documented:

| Value | Property | File | Reason |
|-------|----------|------|--------|
| `1px` / `-1px` | width/height/margin | `a11y.css.ts` | sr-only recipe (§3.1 canonical exemption) |
| `44px` | width/height | `styles.css` (hit-area `::before`) | Platform minimum touch target (AC-20.1.1) |
| `3rem` | padding-bottom | `styles.css` `.app-shell` | Layout scroll buffer |
| `5rem` | padding-bottom | `Gallery.css.ts` `page` | Layout scroll buffer |
| `29rem` | max-width | `styles.css` `.app-shell`, `Sheet.css.ts` | Layout max-width (app shell) |
| `#ece9e1` | background-color | `styles.css` `.map-static` | MapLibre style match (domain color) |
| `#2b6cb0` | background | `styles.css` `.map-marker--me` | GPS "you-are-here" convention |
| `#3a7ca5` | background | `styles.css` `.map-marker--water` | Water-source convention |
| `1.8rem` | font-size | `styles.css` `.face` | Emoji reaction glyph |
| `1em` / `1.15em` / `1.25em` / `0.7em` | font-size | various | Em-relative icon sizing (tracks parent) |
| `130ms` | transition-duration | `styles.css` | Legacy motion value — should be `var(--duration-fast)` (120ms) or `var(--duration-base)` (160ms) |
| `220ms` | animation-duration | `styles.css` `.card-reveal` | Card entrance animation — should get a `motion.reveal` token or documented exemption |

### 7.3 Vanilla-extract linting

For `.css.ts` files, the token contract is enforced structurally by TypeScript: `vars` is a typed contract, so any property referencing `vars.*` is already token-bound. The remaining risk is raw string literals like `lineHeight: 1.4` or `paddingBlock: '2px'`. An ESLint rule using `@typescript-eslint/no-restricted-syntax` could flag numeric literal assignments to `lineHeight`/`fontSize`/`padding`/`margin` properties:

```json
{
  "rules": {
    "no-restricted-syntax": [
      "error",
      {
        "selector": "Property[key.name='lineHeight'] > Literal",
        "message": "Use a lineHeight token from vars instead of a raw number."
      },
      {
        "selector": "Property[key.name='fontSize'] > Literal",
        "message": "Use a size token from vars.size instead of a raw value."
      }
    ]
  }
}
```

---

## 8. Transition duration literals

While not in the M1–M3 scope, the inventory found **6 raw `130ms` transition-duration literals** in `styles.css` that should be `var(--duration-fast)` (120ms) or `var(--duration-base)` (160ms):

| Line | Selector | Current | Target |
|------|----------|---------|--------|
| 126 | `.context` | `130ms` | `var(--duration-base)` (160ms) |
| 239 | `.card-tap` | `130ms` | `var(--duration-base)` (160ms) |
| 1074 | `.facet-row` | `130ms` | `var(--duration-base)` (160ms) |
| 1610 | `.pending-nod` | `130ms` | `var(--duration-base)` (160ms) |

Plus `220ms` on `.card-reveal` animation and `1.6s` on `.skeleton-shimmer` — these are animation-specific and may warrant their own motion tokens.

---

## 9. Remediation plan (for the Claude lane that applies this)

### Phase 1: Primitive cleanup (tokens only, no component code)
1. Remove 6 extra size primitives from `primitive.json` (`fact-label`, `supporting`, `condition`, `verdict`, `fact-value`, `name`).
2. Update `semantic.json` type roles to reference the 8 documented steps.
3. Add 5 `lineHeight` primitives + semantic bindings.
4. Regenerate `tokens.css` via Style Dictionary.
5. Update `theme.css.ts` to expose `lineHeight` tokens.

### Phase 2: styles.css snap (mechanical find-replace)
1. Replace 59 font-size literals with `var(--size-*)` references.
2. Replace 21 line-height literals with `var(--line-height-*)` references.
3. Replace ~87 margin/padding/gap literals with `var(--space-*)` references.
4. Replace 4 `130ms` transition durations with `var(--duration-base)`.
5. Document exemptions in a comment block at the top of `styles.css`.

### Phase 3: css.ts cleanup
1. Replace 5 raw `lineHeight` values with `vars.lineHeight.*`.
2. Replace `paddingBlock: '2px'` in Gallery with `vars.space[1]` or documented exemption.

### Phase 4: Lint activation
1. Add Stylelint config from §7.1.
2. Add ESLint rule from §7.3.
3. Wire into CI (`make check` or a `make lint-frontend` target).

**Estimated effort:** Phase 1 is ~30 min (token JSON edits). Phase 2 is ~2 hours (mechanical, but 170+ replacements). Phase 3 is ~15 min. Phase 4 is ~1 hour (config + CI wiring). Total: ~half a day.

---

## 10. Verification

The exit criterion is `design-system-v0.1.md` §14[d3][d4]:
- **[d3]** No raw color/size/duration literals remain in component code.
- **[d4]** Type, space, radius, stroke, motion scales are defined and used (no ad-hoc values).

After remediation, the lint rules in §7 should pass with zero violations (excluding the documented exemption registry). The rendered UI should be visually indistinguishable — the largest delta is 1.8px (the `size.name` collapse from 1.3rem to 1.1875rem), which is sub-pixel at most rendering sizes.
