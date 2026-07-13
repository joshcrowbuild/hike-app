import { readFileSync } from 'node:fs'
import { join } from 'node:path'

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { Sheet } from './Sheet'
import * as styles from './Sheet.css'

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

/**
 * C1 regression suite (craft review 2026-07): the origin sheet rendered
 * 2,110px tall in a fixed overlay with no max-height and no scrollable
 * element — Back/Done sat 1,261px above the viewport, and swiping scrolled
 * the FEED behind the open modal. These tests pin the two mechanisms that
 * make that impossible: the document scroll lock, and the pinned-header /
 * internal-scroll structure.
 */
describe('Sheet height + scroll contract (C1)', () => {
  it('locks the page scroll while open and releases it on unmount', () => {
    const { unmount } = render(
      <Sheet isOpen onClose={() => {}} title="Starting point">
        body
      </Sheet>,
    )
    // React Aria's usePreventScroll: the document must not be scrollable
    // behind the modal (window.scrollBy moving the feed was the measured bug).
    expect(document.documentElement.style.overflow).toBe('hidden')
    unmount()
    expect(document.documentElement.style.overflow).toBe('')
  })

  it('keeps Back and Done OUTSIDE the internal scroll area — pinned and reachable at any content height', () => {
    render(
      <Sheet isOpen onClose={() => {}} onBack={() => {}} title="Starting point">
        <div data-testid="tall-content">35 origins</div>
      </Sheet>,
    )
    const body = document.querySelector(`.${styles.body}`)
    expect(body).not.toBeNull()
    // The content scrolls inside `body`; the header actions must never be in it.
    expect(body).toContainElement(screen.getByTestId('tall-content'))
    expect(body).not.toContainElement(screen.getByRole('button', { name: 'Done' }))
    expect(body).not.toContainElement(screen.getByRole('button', { name: 'Back' }))
  })

  it('declares the height cap and internal scroll in the stylesheet (jsdom computes no vanilla-extract styles — pin the source)', () => {
    // jsdom cannot resolve the compiled vanilla-extract CSS into computed
    // styles, so the cap is pinned at the declaration level: the sheet must
    // carry a maxHeight and the body must scroll + contain overscroll. If this
    // test fails after a refactor, the C1 guarantee moved — re-pin it, don't
    // delete it.
    // vitest's jsdom import.meta.url is not file-scheme; vitest always runs
    // with cwd at the frontend package root, so resolve from there.
    const source = readFileSync(join(process.cwd(), 'src/components/Sheet/Sheet.css.ts'), 'utf8')
    expect(source).toMatch(/maxHeight:\s*\['85vh', '85dvh'\]/)
    expect(source).toMatch(/overflowY:\s*'auto'/)
    expect(source).toMatch(/overscrollBehavior:\s*'contain'/)
  })

  it('traps focus inside the dialog (Tab cycles through Back → content → Done, never the page behind)', async () => {
    render(
      <Sheet isOpen onClose={() => {}} onBack={() => {}} title="Starting point">
        <button type="button">Front Royal</button>
      </Sheet>,
    )
    const dialog = screen.getByRole('dialog', { name: 'Starting point' })
    await waitFor(() => expect(dialog.contains(document.activeElement)).toBe(true))
    // One full cycle plus one: focus must still be inside the dialog.
    for (let i = 0; i < 4; i++) {
      await userEvent.tab()
      expect(dialog.contains(document.activeElement)).toBe(true)
    }
  })
})
