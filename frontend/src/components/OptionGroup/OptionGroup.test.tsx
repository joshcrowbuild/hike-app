import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { OptionButton, OptionGroup } from './OptionGroup'

function Fixture({
  value = 'a',
  onChange = () => {},
}: {
  value?: string
  onChange?: (value: string) => void
}) {
  return (
    <OptionGroup label="Pick one" value={value} onChange={onChange}>
      <OptionButton value="a">Alpha</OptionButton>
      <OptionButton value="b">Beta</OptionButton>
    </OptionGroup>
  )
}

describe('OptionGroup', () => {
  it('renders a labelled radiogroup of options', () => {
    render(<Fixture />)
    expect(screen.getByRole('radiogroup', { name: 'Pick one' })).toBeInTheDocument()
    expect(screen.getAllByRole('radio')).toHaveLength(2)
  })

  it('marks the selected value', () => {
    render(<Fixture value="b" />)
    expect(screen.getByRole('radio', { name: 'Beta' })).toBeChecked()
  })

  it('calls onChange with the chosen value', async () => {
    const onChange = vi.fn()
    render(<Fixture value="a" onChange={onChange} />)
    await userEvent.click(screen.getByRole('radio', { name: 'Beta' }))
    expect(onChange).toHaveBeenCalledWith('b')
  })
})
