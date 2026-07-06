import { readFileSync } from 'node:fs'

import { describe, expect, it } from 'vitest'

/**
 * Epic 020 (AC-20.2.1): every muted-small text/background pairing app-wide
 * clears WCAG AA (4.5:1) — not just the one card-surface case Epic 019 tested
 * (AC-19.2.3). `--text-muted` renders directly on all three standing surfaces
 * (canvas: the page body; raised: cards/sheets/facet-rows; press: active/hover
 * states) and, via <Staleness>, inside the terracotta-tinted warning field —
 * so all four are asserted here from the primitive tokens, never hand-copied
 * hex values.
 */
const primitive = JSON.parse(readFileSync('tokens/primitive.json', 'utf8'))

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

/** Alpha-composite a foreground rgba over an opaque hex background — needed
 *  for `signal-caution-bg`, which is authored as a terracotta alpha wash, not
 *  a flat hex. */
function composite(fgHex: string, alpha: number, bgHex: string): string {
  const fg = Number.parseInt(fgHex.replace('#', ''), 16)
  const bg = Number.parseInt(bgHex.replace('#', ''), 16)
  const mix = (shift: number) => {
    const f = (fg >> shift) & 0xff
    const b = (bg >> shift) & 0xff
    return Math.round(f * alpha + b * (1 - alpha))
  }
  const r = mix(16)
  const g = mix(8)
  const b = mix(0)
  return `#${((r << 16) | (g << 8) | b).toString(16).padStart(6, '0')}`
}

describe('text-muted clears WCAG AA app-wide, not just on one surface (AC-20.2.1)', () => {
  const muted = primitive.color.neutral['500'].$value
  const surfaces: Record<string, string> = {
    raised: primitive.color.neutral['25'].$value,
    canvas: primitive.color.neutral['50'].$value,
    press: primitive.color.neutral['100'].$value,
  }

  for (const [name, bg] of Object.entries(surfaces)) {
    it(`text-muted on surface-${name} is >= 4.5:1`, () => {
      expect(contrast(muted, bg)).toBeGreaterThanOrEqual(4.5)
    })
  }

  it('text-muted inside the signal (warning-timestamp) field is >= 4.5:1', () => {
    // Mirrors .card-warning-meta's real field: signal-caution-bg (a 10% terracotta
    // wash) composited over surface-raised, the card ground it sits on.
    const terracotta = primitive.color.terracotta['600'].$value
    const raised = primitive.color.neutral['25'].$value
    const signalBg = composite(terracotta, 0.1, raised)
    expect(contrast(muted, signalBg)).toBeGreaterThanOrEqual(4.5)
  })
})
