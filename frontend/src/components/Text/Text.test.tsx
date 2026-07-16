import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { Text } from './Text'
import * as styles from './Text.css'
import type { TextRole } from './Text'

const ALL_ROLES: TextRole[] = [
  'display',
  'title',
  'lead',
  'body',
  'bodySm',
  'metric',
  'metricLabel',
  'caption',
  'overline',
]

describe('Text', () => {
  it.each(ALL_ROLES)('renders the %s role with its own class and no others', (role) => {
    render(<Text role={role}>content-{role}</Text>)
    const node = screen.getByText(`content-${role}`)
    expect(node.className).toContain(styles.role[role])
    for (const other of ALL_ROLES) {
      if (other === role) continue
      expect(node.className).not.toContain(styles.role[other])
    }
  })

  it('defaults to a sensible element per role', () => {
    render(<Text role="display">Hero name</Text>)
    expect(screen.getByRole('heading', { level: 1, name: 'Hero name' })).toBeInTheDocument()
  })

  it('defaults title to an h3', () => {
    render(<Text role="title">Card name</Text>)
    expect(screen.getByRole('heading', { level: 3, name: 'Card name' })).toBeInTheDocument()
  })

  it('lets a caller override the rendered element via `as`', () => {
    render(<Text role="title" as="h2">Section name</Text>)
    expect(screen.getByRole('heading', { level: 2, name: 'Section name' })).toBeInTheDocument()
  })

  it('renders body/caption/metric roles as non-heading elements by default', () => {
    render(<Text role="body">Prose</Text>)
    expect(screen.getByText('Prose').tagName).toBe('P')
  })

  it('forwards a className alongside the role class', () => {
    render(<Text role="caption" className="placed">Source</Text>)
    const node = screen.getByText('Source')
    expect(node.className).toContain(styles.role.caption)
    expect(node.className).toContain('placed')
  })

  it('forwards arbitrary element props (e.g. aria-hidden) to the rendered tag', () => {
    render(
      <div>
        <Text role="metricLabel" aria-hidden="true">
          Distance
        </Text>
      </div>,
    )
    expect(screen.getByText('Distance')).toHaveAttribute('aria-hidden', 'true')
  })
})
