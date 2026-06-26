import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { summarizeProfile } from '../../data/geo'
import { ElevationProfile } from './ElevationProfile'

const profile = summarizeProfile(
  [
    { distanceMeters: 0, elevationMeters: 1000 },
    { distanceMeters: 800, elevationMeters: 1200 },
    { distanceMeters: 1600, elevationMeters: 1100 },
  ],
  'USGS 3DEP (sample)',
  10,
)

describe('ElevationProfile (S5b)', () => {
  it('labels total gain, loss, and max grade as a text equivalent (E / a11y)', () => {
    render(<ElevationProfile profile={profile} cursorFraction={null} onScrub={vi.fn()} />)
    // 200 m gain ≈ 656 ft, 100 m loss ≈ 328 ft.
    expect(screen.getByText('↑ 656 ft')).toBeInTheDocument()
    expect(screen.getByText('↓ 328 ft')).toBeInTheDocument()
    expect(screen.getByText(/max 25%/)).toBeInTheDocument()
    // The sr-only summary restates the chart for assistive tech.
    expect(screen.getByText(/Climbs 656 ft, descends 328 ft, steepest grade 25%/)).toBeInTheDocument()
  })

  it('is an accessible slider whose value text starts at the summary', () => {
    render(<ElevationProfile profile={profile} cursorFraction={null} onScrub={vi.fn()} />)
    const slider = screen.getByRole('slider', { name: /elevation/i })
    expect(slider).toHaveAttribute('aria-valuemin', '0')
    expect(slider).toHaveAttribute('aria-valuemax', '100')
    expect(slider).toHaveAttribute('aria-valuenow', '0')
    expect(slider.getAttribute('aria-valuetext')).toMatch(/Climbs/)
  })

  it('scrubs with the keyboard and emits a fraction', async () => {
    const onScrub = vi.fn()
    const user = userEvent.setup()
    render(<ElevationProfile profile={profile} cursorFraction={0.5} onScrub={onScrub} />)
    const slider = screen.getByRole('slider', { name: /elevation/i })
    slider.focus()
    await user.keyboard('{ArrowRight}')
    expect(onScrub).toHaveBeenLastCalledWith(expect.closeTo(0.52, 5))
    await user.keyboard('{Home}')
    expect(onScrub).toHaveBeenLastCalledWith(0)
    await user.keyboard('{End}')
    expect(onScrub).toHaveBeenLastCalledWith(1)
  })

  it('reports the cursor distance + elevation in the value text when set', () => {
    render(<ElevationProfile profile={profile} cursorFraction={0.5} onScrub={vi.fn()} />)
    const slider = screen.getByRole('slider', { name: /elevation/i })
    expect(slider).toHaveAttribute('aria-valuenow', '50')
    // Midpoint ≈ 0.5 mi, elevation interpolated to the peak (~1200 m ≈ 3,937 ft).
    expect(slider.getAttribute('aria-valuetext')).toMatch(/0\.5 mi/)
    expect(slider.getAttribute('aria-valuetext')).toMatch(/ft/)
  })
})
