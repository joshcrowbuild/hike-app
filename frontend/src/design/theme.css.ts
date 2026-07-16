/**
 * Typed theme contract over the Style-Dictionary-generated CSS custom
 * properties in `tokens.css`.
 *
 * The single source of truth stays DTCG -> Style Dictionary: this file defines
 * **no values**. `createGlobalThemeContract` maps each token path onto the exact
 * `--var` name Style Dictionary emits, so `vars.surface.canvas` resolves to
 * `var(--surface-canvas)` at zero runtime cost and with full type-safety. If a
 * token is renamed at the source, TypeScript flags every consumer.
 *
 * Components reference SEMANTIC roles (surface / text / border / overlay /
 * signal / focus) and the primitive SCALES (space / size / lineHeight / radius
 * / stroke / duration / font) — never raw primitive colours. The
 * `color.neutral.*`, `color.terracotta.*` and `color.amber.*` ramps are
 * deliberately ABSENT from this contract so a component cannot bind to a
 * primitive colour — `color.amber.600` reaches components only through the
 * semantic `signal.headsUp.{fg,bg}` role, exactly like terracotta reaches them
 * only through `signal.caution`/`signal.blocked`. This is the one-directional
 * reference rule made structural (design-system-v0.1 §3.1, §11).
 *
 * FROZEN CONTRACT (WP-0, design-system-v0.2.md Part IV.1). Changes go through
 * the merge desk — see `contracts.ts` (Contract B) for the component-facing
 * prop/data-shape contract that sits alongside this one.
 */
import { createGlobalThemeContract } from '@vanilla-extract/css'

export const vars = createGlobalThemeContract(
  {
    // --- semantic colour roles (component -> semantic -> primitive) ---
    surface: {
      canvas: 'surface-canvas',
      raised: 'surface-raised',
      press: 'surface-press',
    },
    text: {
      primary: 'text-primary',
      secondary: 'text-secondary',
      muted: 'text-muted',
    },
    border: {
      hairline: 'border-hairline',
      faint: 'border-faint',
    },
    overlay: {
      scrim: 'overlay-scrim',
    },
    elevation: {
      // The single permitted shadow; only overlays (sheets) may lift (§6.4).
      overlay: 'elevation-overlay',
    },
    signal: {
      // DEPRECATED (design-system-v0.2 D1) — kept for existing call sites
      // (Signal.css.ts, Confidence.css.ts, VisionPrototype.tsx, Gallery.tsx).
      // WP-2/WP-3 re-sort each usage into headsUp | blocked and migrate off it.
      caution: {
        fg: 'signal-caution-fg',
        bg: 'signal-caution-bg',
      },
      // The 4-tier signal system (design-system-v0.2 D1). `clear` has no
      // token — it renders nothing (Law 1).
      unknown: {
        fg: 'signal-unknown-fg',
      },
      headsUp: {
        fg: 'signal-heads-up-fg',
        bg: 'signal-heads-up-bg',
      },
      blocked: {
        fg: 'signal-blocked-fg',
        bg: 'signal-blocked-bg',
      },
    },
    focus: {
      ring: 'focus-ring',
    },

    // --- primitive scales: no semantic layer, used directly per §6 ---
    space: {
      0: 'space-0',
      1: 'space-1',
      2: 'space-2',
      3: 'space-3',
      4: 'space-4',
      5: 'space-5',
      6: 'space-6',
      8: 'space-8',
      10: 'space-10',
      11: 'space-11',
      12: 'space-12',
    },
    size: {
      dataMicro: 'size-data-micro',
      label: 'size-label',
      meta: 'size-meta',
      body: 'size-body',
      emphasis: 'size-emphasis',
      placeLead: 'size-place-lead',
      title: 'size-title',
    },
    // NEW (design-system-v0.2 I.3) — tokenizes what `styles.css` hardcoded.
    lineHeight: {
      tight: 'line-height-tight',
      snug: 'line-height-snug',
      normal: 'line-height-normal',
      relaxed: 'line-height-relaxed',
    },
    radius: {
      sm: 'radius-sm',
      md: 'radius-md',
      pill: 'radius-pill',
    },
    stroke: {
      hairline: 'stroke-hairline',
      line: 'stroke-line',
      path: 'stroke-path',
    },
    duration: {
      fast: 'duration-fast',
      base: 'duration-base',
      // NEW (design-system-v0.2 I.6) — disclosure-only (expand/collapse).
      slow: 'duration-slow',
    },
    easing: {
      standard: 'easing-standard',
    },
    font: {
      family: {
        sans: 'font-family-sans',
        mono: 'font-family-mono',
      },
      weight: {
        regular: 'font-weight-regular',
        medium: 'font-weight-medium',
        semibold: 'font-weight-semibold',
      },
    },
    // The v0.2 role scale (design-system-v0.2.md I.3) — each role carries
    // size + lineHeight + weight (+ family for `metric`, mono). The v0.1
    // Epic-019 roles below (name/verdict/fact-value/fact-label/condition/
    // supporting) stay exposed unchanged for existing components; WP-1/WP-7
    // migrate them onto the roles above and retire this block.
    type: {
      name: { size: 'type-name-size', weight: 'type-name-weight' },
      verdict: { size: 'type-verdict-size', weight: 'type-verdict-weight' },
      factValue: { size: 'type-fact-value-size', weight: 'type-fact-value-weight' },
      factLabel: { size: 'type-fact-label-size', weight: 'type-fact-label-weight' },
      condition: { size: 'type-condition-size', weight: 'type-condition-weight' },
      supporting: { size: 'type-supporting-size', weight: 'type-supporting-weight' },

      display: {
        size: 'type-display-size',
        lineHeight: 'type-display-line-height',
        weight: 'type-display-weight',
      },
      title: {
        size: 'type-title-size',
        lineHeight: 'type-title-line-height',
        weight: 'type-title-weight',
      },
      lead: {
        size: 'type-lead-size',
        lineHeight: 'type-lead-line-height',
        weight: 'type-lead-weight',
      },
      body: {
        size: 'type-body-size',
        lineHeight: 'type-body-line-height',
        weight: 'type-body-weight',
      },
      bodySm: {
        size: 'type-body-sm-size',
        lineHeight: 'type-body-sm-line-height',
        weight: 'type-body-sm-weight',
      },
      metric: {
        size: 'type-metric-size',
        lineHeight: 'type-metric-line-height',
        weight: 'type-metric-weight',
        family: 'type-metric-family',
      },
      metricLabel: {
        size: 'type-metric-label-size',
        lineHeight: 'type-metric-label-line-height',
        weight: 'type-metric-label-weight',
      },
      caption: {
        size: 'type-caption-size',
        lineHeight: 'type-caption-line-height',
        weight: 'type-caption-weight',
      },
      overline: {
        size: 'type-overline-size',
        lineHeight: 'type-overline-line-height',
        weight: 'type-overline-weight',
      },
    },
  },
  // Every leaf above is a non-null var name; map it straight through.
  (value) => value as string,
)
