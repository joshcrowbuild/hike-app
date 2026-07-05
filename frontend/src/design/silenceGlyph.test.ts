import { readFileSync } from 'node:fs'

import { describe, expect, it } from 'vitest'

/**
 * Epic 020 (AC-20.3.1, DD2): the caution/terracotta signal hue is reserved for
 * a LIVE hazard (`triangle-alert`/`!`, carried by the owned <Signal> primitive)
 * — a merely-stale timestamp must never borrow it. Asserted directly against
 * the stylesheet text so a future edit can't silently re-attach the hue to
 * `stale-degraded` without this test catching it.
 */
describe('stale-degraded silence is off the caution hue (AC-20.3.1)', () => {
  const css = readFileSync('src/styles.css', 'utf8')

  const rule = (selector: string): string => {
    const start = css.indexOf(selector)
    expect(start, `${selector} should exist in styles.css`).toBeGreaterThanOrEqual(0)
    const close = css.indexOf('}', start)
    return css.slice(start, close)
  }

  it('.condition-silence--stale-degraded carries no signal-caution reference', () => {
    expect(rule('.condition-silence--stale-degraded {')).not.toMatch(/signal-caution/)
  })

  it('.condition-silence--stale-degraded .condition-silence-glyph carries no signal-caution reference', () => {
    expect(rule('.condition-silence--stale-degraded .condition-silence-glyph {')).not.toMatch(/signal-caution/)
  })

  it('the caution hue stays reserved for the Signal primitive (still wired)', () => {
    expect(css).toMatch(/signal-caution-fg/)
  })
})
