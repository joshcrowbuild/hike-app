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
