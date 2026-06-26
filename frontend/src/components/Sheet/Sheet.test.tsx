import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { Sheet } from './Sheet'

describe('Sheet', () => {
  it('renders nothing when closed', () => {
    render(
      <Sheet isOpen={false} onClose={() => {}} title="Adjust">
        body
      </Sheet>,
    )
    expect(screen.queryByRole('dialog')).toBeNull()
  })

  it('renders a titled dialog when open', () => {
    render(
      <Sheet isOpen onClose={() => {}} title="Adjust">
        body
      </Sheet>,
    )
    expect(screen.getByRole('dialog', { name: 'Adjust' })).toBeInTheDocument()
  })

  it('dismisses on Escape', async () => {
    const onClose = vi.fn()
    render(
      <Sheet isOpen onClose={onClose} title="Adjust">
        body
      </Sheet>,
    )
    await userEvent.keyboard('{Escape}')
    expect(onClose).toHaveBeenCalled()
  })

  it('shows Back only when onBack is provided', () => {
    const { rerender } = render(
      <Sheet isOpen onClose={() => {}} title="Adjust">
        body
      </Sheet>,
    )
    expect(screen.queryByRole('button', { name: 'Back' })).toBeNull()
    rerender(
      <Sheet isOpen onClose={() => {}} title="Adjust" onBack={() => {}}>
        body
      </Sheet>,
    )
    expect(screen.getByRole('button', { name: 'Back' })).toBeInTheDocument()
  })
})
