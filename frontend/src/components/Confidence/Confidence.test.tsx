import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { Confidence } from './Confidence'

describe('Confidence', () => {
  it('gives assistive tech a tier lead-in without showing a number', () => {
    render(
      <Confidence level="hedged" provenance="live">
        Likely sunny, 54°F
      </Confidence>,
    )
    // sr-only lead-in present; no numeric confidence anywhere.
    expect(screen.getByText(/Likely:/)).toBeInTheDocument()
    expect(screen.queryByText(/0\.\d|%/)).not.toBeInTheDocument()
  })

  it('marks non-live data as sample so it cannot pass as verified (R1)', () => {
    render(
      <Confidence level="stated" provenance="mock">
        54°F · breezy · clear
      </Confidence>,
    )
    expect(screen.getByText('sample')).toBeInTheDocument()
  })

  it('never announces mock data as "Verified" to assistive tech (R1)', () => {
    render(
      <Confidence level="stated" provenance="mock">
        54°F · breezy · clear
      </Confidence>,
    )
    // The visual tag is aria-hidden, so the sr-only lead-in carries the
    // disclosure: AT must hear "Sample", never "Verified".
    expect(screen.queryByText(/Verified/)).not.toBeInTheDocument()
    expect(screen.getByText(/Sample, not verified/)).toBeInTheDocument()
  })

  it('does not tag live data as sample', () => {
    render(
      <Confidence level="stated" provenance="live">
        54°F · breezy · clear
      </Confidence>,
    )
    expect(screen.queryByText('sample')).not.toBeInTheDocument()
  })
})
