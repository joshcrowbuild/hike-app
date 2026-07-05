import { render } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { SkeletonCard } from './SkeletonCard'

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('SkeletonCard', () => {
  it('renders a decorative card silhouette', () => {
    const { container } = render(<SkeletonCard />)
    const card = container.querySelector('.skeleton-card')
    expect(card).toBeInTheDocument()
    expect(card).toHaveAttribute('aria-hidden', 'true')
    expect(container.querySelectorAll('.skeleton-line').length).toBeGreaterThan(0)
  })

  it('mirrors the new lean silhouette — a verdict line at top, no deleted place line (AC-19.3.1)', () => {
    const { container } = render(<SkeletonCard />)
    // The restructured card leads with the verdict, not the old placeCue; the
    // skeleton must match so the real card never reflows on swap.
    expect(container.querySelector('.skeleton-line--verdict')).toBeInTheDocument()
    expect(container.querySelector('.skeleton-line--place')).not.toBeInTheDocument()
    // The element set the card actually renders: verdict, name, area, decision, condition, foot.
    for (const part of ['verdict', 'name', 'area', 'decision', 'condition', 'foot']) {
      expect(container.querySelector(`.skeleton-line--${part}`), part).toBeInTheDocument()
    }
    expect(container.querySelector('.skeleton-glyph')).toBeInTheDocument()
  })

  it('shimmers by default (no reduced-motion preference)', () => {
    vi.stubGlobal('matchMedia', vi.fn().mockReturnValue({ matches: false }))
    const { container } = render(<SkeletonCard />)
    expect(container.querySelector('.skeleton-shimmer')).toBeInTheDocument()
  })

  it('drops the shimmer entirely under prefers-reduced-motion', () => {
    vi.stubGlobal('matchMedia', vi.fn().mockReturnValue({ matches: true }))
    const { container } = render(<SkeletonCard />)
    expect(container.querySelector('.skeleton-shimmer')).not.toBeInTheDocument()
    // Still renders the static placeholder shape, just without the animation.
    expect(container.querySelectorAll('.skeleton-line').length).toBeGreaterThan(0)
  })

  it('does not error when matchMedia is unavailable (defensive default)', () => {
    vi.stubGlobal('matchMedia', undefined)
    const { container } = render(<SkeletonCard />)
    expect(container.querySelector('.skeleton-card')).toBeInTheDocument()
  })
})
