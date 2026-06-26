import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { Toggle } from './Toggle'

describe('Toggle', () => {
  it('exposes a switch with its label', () => {
    render(<Toggle label="Match today's readiness" isSelected={false} onChange={() => {}} />)
    expect(
      screen.getByRole('switch', { name: /match today's readiness/i }),
    ).toBeInTheDocument()
  })

  it('keeps the description out of the accessible name', () => {
    // Regression guard: the name must be exactly the label (not label+description
    // run together), and the description must be a separate accessible description.
    render(
      <Toggle
        label="Match readiness"
        description="Hides hard climbs today."
        isSelected={false}
        onChange={() => {}}
      />,
    )
    const sw = screen.getByRole('switch', { name: 'Match readiness' })
    expect(sw).toHaveAccessibleDescription('Hides hard climbs today.')
  })

  it('reflects the on state', () => {
    render(<Toggle label="Readiness" isSelected onChange={() => {}} />)
    expect(screen.getByRole('switch')).toBeChecked()
  })

  it('calls onChange when toggled', async () => {
    const onChange = vi.fn()
    render(<Toggle label="Readiness" isSelected={false} onChange={onChange} />)
    await userEvent.click(screen.getByRole('switch'))
    expect(onChange).toHaveBeenCalledWith(true)
  })
})
