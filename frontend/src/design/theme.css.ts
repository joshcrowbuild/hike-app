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
 * signal / focus) and the primitive SCALES (space / size / radius / stroke /
 * duration / font) — never raw primitive colours. The `color.neutral.*` and
 * `color.terracotta.*` ramps are deliberately ABSENT from this contract so a
 * component cannot bind to a primitive colour. This is the one-directional
 * reference rule made structural (design-system-v0.1 §3.1, §11).
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
      caution: {
        fg: 'signal-caution-fg',
        bg: 'signal-caution-bg',
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
  },
  // Every leaf above is a non-null var name; map it straight through.
  (value) => value as string,
)
