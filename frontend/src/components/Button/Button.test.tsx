import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { Button } from './Button'
import * as styles from './Button.css'

describe('Button', () => {
  it('renders as an accessible button carrying its label', () => {
    render(<Button>Save trail</Button>)
    expect(screen.getByRole('button', { name: 'Save trail' })).toBeInTheDocument()
  })

  it('calls onPress when activated by click', async () => {
    const onPress = vi.fn()
    render(<Button onPress={onPress}>Directions</Button>)
    await userEvent.click(screen.getByRole('button', { name: 'Directions' }))
    expect(onPress).toHaveBeenCalledTimes(1)
  })

  it('is keyboard-activatable (Enter)', async () => {
    const onPress = vi.fn()
    render(<Button onPress={onPress}>Retry</Button>)
    const btn = screen.getByRole('button', { name: 'Retry' })
    btn.focus();
    await userEvent.keyboard('{Enter}')
    expect(onPress).toHaveBeenCalledTimes(1)
  })

  it('disables the button and refuses press when isDisabled', async () => {
    const onPress = vi.fn()
    render(
      <Button onPress={onPress} isDisabled>
        Save trail
      </Button>,
    )
    const btn = screen.getByRole('button', { name: 'Save trail' })
    expect(btn).toBeDisabled()
    await userEvent.click(btn)
    expect(onPress).not.toHaveBeenCalled()
  })

  it('defaults to the primary variant and md size', () => {
    render(<Button>Save trail</Button>)
    const btn = screen.getByRole('button')
    expect(btn.className).toContain(styles.variant.primary)
    expect(btn.className).toContain(styles.size.md)
  })

  it.each(['primary', 'secondary', 'ghost'] as const)('applies the %s variant class', (variant) => {
    render(<Button variant={variant}>Label</Button>)
    expect(screen.getByRole('button').className).toContain(styles.variant[variant])
  })

  it.each(['sm', 'md'] as const)('applies the %s size class', (size) => {
    render(<Button size={size}>Label</Button>)
    expect(screen.getByRole('button').className).toContain(styles.size[size])
  })

  it('forwards a className alongside the base/variant/size classes', () => {
    render(<Button className="placed">Label</Button>)
    expect(screen.getByRole('button').className).toContain('placed')
  })

  it('carries the shared base class that owns the 44px hit-target and focus-ring selectors', () => {
    render(<Button>Label</Button>)
    expect(screen.getByRole('button').className).toContain(styles.base)
  })
})
