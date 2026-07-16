import { readFileSync } from 'node:fs'

import { describe, expect, it } from 'vitest'

/**
 * design-system-v0.2 I.3 replaces the Epic-019 role scale (name/verdict/
 * fact-value/fact-label/condition/supporting) with the v0.2 canonical set
 * (display/title/lead/body/body-sm/metric/metric-label/caption/overline),
 * each carrying size + lineHeight + weight (+ family for `metric`, mono —
 * D2's "mono for metrics only"). The v0.1 roles stay defined in
 * `semantic.json` for existing components (WP-1/WP-7 migrate them off), so
 * these tests assert the NEW v0.2 scale is what's now authored as tokens —
 * never hand-edited into `tokens.css`, and never a hardcoded rem in a
 * component.
 */
const primitive = JSON.parse(readFileSync('tokens/primitive.json', 'utf8'))
const semantic = JSON.parse(readFileSync('tokens/semantic.json', 'utf8'))

const V02_ROLES = [
  'display',
  'title',
  'lead',
  'body',
  'body-sm',
  'metric',
  'metric-label',
  'caption',
  'overline',
] as const

const remValue = (t: { $value: string }): number => Number.parseFloat(t.$value)

describe('the v0.2 type role scale is authored as tokens (design-system-v0.2 I.3)', () => {
  it('every v0.2 role carries size + lineHeight (referencing a primitive) + weight', () => {
    for (const role of V02_ROLES) {
      const t = semantic.type[role]
      expect(t, role).toBeTruthy()

      // size is a literal rem dimension (Appendix B hardcodes it directly —
      // unlike the v0.1 roles, which reference a `size.*` primitive step).
      expect(t.size.$value, `${role}.size`).toMatch(/^\d*\.?\d+rem$/)

      // lineHeight REFERENCES the new lineHeight primitive scale.
      expect(t.lineHeight.$value, `${role}.lineHeight`).toMatch(/^\{lineHeight\.[a-z]+\}$/)
      const lhName = t.lineHeight.$value.slice('{lineHeight.'.length, -1)
      expect(primitive.lineHeight[lhName], `${role} -> lineHeight.${lhName}`).toBeTruthy()

      // weight REFERENCES the shared font.weight scale.
      expect(t.weight.$value, `${role}.weight`).toMatch(/^\{font\.weight\.[a-z]+\}$/)
      const weightName = t.weight.$value.slice('{font.weight.'.length, -1)
      expect(primitive.font.weight[weightName], `${role} -> font.weight.${weightName}`).toBeTruthy()
    }
  })

  it('mono for metrics only (D2): metric carries family -> font.family.mono; no other v0.2 role does', () => {
    expect(semantic.type.metric.family?.$value).toBe('{font.family.mono}')
    expect(primitive.font.family.mono).toBeTruthy()

    for (const role of V02_ROLES) {
      if (role === 'metric') continue
      expect(semantic.type[role].family, `${role} should have no family override`).toBeUndefined()
    }
  })

  it('the generated tokens.css carries the v0.2 roles (proof the pipeline ran, not a manual edit)', () => {
    const css = readFileSync('src/design/tokens.css', 'utf8')
    expect(css).toContain('Do not edit directly, this file was auto-generated.')
    expect(css).toContain('--type-display-size: 1.75rem;')
    expect(css).toContain('--type-metric-family: var(--font-family-mono);')
    expect(css).toContain('--signal-heads-up-fg: var(--color-amber-600);')
    expect(css).toContain('--signal-blocked-fg: var(--color-terracotta-600);')
  })
})

describe('display is the dominant v0.2 role (Law 5 — one role-based type scale, never a size)', () => {
  it('type.display is strictly larger than every other v0.2 role', () => {
    const display = remValue(semantic.type.display.size)
    for (const role of V02_ROLES) {
      if (role === 'display') continue
      expect(display, `display vs ${role}`).toBeGreaterThan(remValue(semantic.type[role].size))
    }
  })

  it('the heading roles step down in the table order (display > title > lead > body)', () => {
    const [display, title, lead, body] = ['display', 'title', 'lead', 'body'].map((role) =>
      remValue(semantic.type[role].size),
    )
    expect(display).toBeGreaterThan(title)
    expect(title).toBeGreaterThan(lead)
    expect(lead).toBeGreaterThan(body)
  })
})

describe('muted-small text clears WCAG AA on the card (AC-19.2.3)', () => {
  // Relative luminance + contrast ratio per WCAG 2.x.
  const channel = (c: number): number => {
    const s = c / 255
    return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4
  }
  const luminance = (hex: string): number => {
    const n = Number.parseInt(hex.replace('#', ''), 16)
    const r = channel((n >> 16) & 0xff)
    const g = channel((n >> 8) & 0xff)
    const b = channel(n & 0xff)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b
  }
  const contrast = (a: string, b: string): number => {
    const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x)
    return (hi + 0.05) / (lo + 0.05)
  }

  it('text-muted on surface-raised (the card ground) is >= 4.5:1', () => {
    // Resolve the semantic refs down to primitive hex.
    const muted = primitive.color.neutral['500'].$value // text.muted
    const raised = primitive.color.neutral['25'].$value // surface.raised
    expect(muted).toBe('#5e636a')
    expect(contrast(muted, raised)).toBeGreaterThanOrEqual(4.5)
  })
})

describe('the amber heads-up hue clears WCAG AA with headroom (design-system-v0.2 D1/WP-0)', () => {
  const channel = (c: number): number => {
    const s = c / 255
    return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4
  }
  const luminance = (hex: string): number => {
    const n = Number.parseInt(hex.replace('#', ''), 16)
    const r = channel((n >> 16) & 0xff)
    const g = channel((n >> 8) & 0xff)
    const b = channel(n & 0xff)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b
  }
  const contrast = (a: string, b: string): number => {
    const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x)
    return (hi + 0.05) / (lo + 0.05)
  }

  it('amber.600 is >= 4.6:1 on both surface.canvas and surface.raised', () => {
    const amber = primitive.color.amber['600'].$value
    const canvas = primitive.color.neutral['50'].$value // surface.canvas
    const raised = primitive.color.neutral['25'].$value // surface.raised
    expect(contrast(amber, canvas)).toBeGreaterThanOrEqual(4.6)
    expect(contrast(amber, raised)).toBeGreaterThanOrEqual(4.6)
  })
})
