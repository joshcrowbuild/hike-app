import { useState } from 'react'

import { OptionButton, OptionGroup, Sheet, Signal, Toggle } from './components'
import * as g from './Gallery.css'

// ---- Signal section -------------------------------------------------------

function SignalSection() {
  return (
    <section className={g.section}>
      <div className={g.sectionHead}>
        <h2 className={g.sectionTitle}>Signal</h2>
        <p className={g.sectionDesc}>
          Verify-before-you-go honesty primitive. Sole carrier of the accent hue.
          Left rule + soft field, never a banner or stoplight.
        </p>
      </div>

      <div className={g.demoBox}>
        <div className={g.demoRow}>
          <span className={g.demoLabel}>Default label</span>
          <Signal>Verify creek crossings — running high after last week's rain.</Signal>
        </div>

        <hr className={g.divider} />

        <div className={g.demoRow}>
          <span className={g.demoLabel}>Custom label</span>
          <Signal label="Permit required">Wilderness permit required Fri–Sun. Quota fills by 7 am.</Signal>
        </div>

        <hr className={g.divider} />

        <div className={g.demoRow}>
          <span className={g.demoLabel}>Tokens</span>
          <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
            <span className={g.tokenChip}>
              <span
                className={g.tokenDot}
                style={{ background: 'var(--signal-caution-fg)' }}
                aria-hidden="true"
              />
              signal.caution.fg
            </span>
            <span className={g.tokenChip}>
              <span
                className={g.tokenDot}
                style={{ background: 'var(--signal-caution-bg)', border: '1px solid var(--border-hairline)' }}
                aria-hidden="true"
              />
              signal.caution.bg
            </span>
            <span className={g.tokenChip}>stroke.path · size.emphasis · weight.medium</span>
          </div>
        </div>
      </div>
    </section>
  )
}

// ---- Toggle section -------------------------------------------------------

type ToggleDemoProps = { label: string; description?: string; initial?: boolean }

function ToggleDemo({ label, description, initial = false }: ToggleDemoProps) {
  const [on, setOn] = useState(initial)
  return (
    <Toggle
      label={label}
      description={description}
      isSelected={on}
      onChange={setOn}
    />
  )
}

function ToggleSection() {
  return (
    <section className={g.section}>
      <div className={g.sectionHead}>
        <h2 className={g.sectionTitle}>Toggle</h2>
        <p className={g.sectionDesc}>
          Explicit on/off control — slide animation on the thumb and track.
          Tap or press Space/Enter to see the transition.
        </p>
      </div>

      <div className={g.demoBox}>
        <div className={g.demoRow}>
          <span className={g.demoLabel}>Off → On (try it)</span>
          <ToggleDemo
            label="Match today's readiness"
            description="Hide what today can't support. Off unless you turn it on."
          />
        </div>

        <hr className={g.divider} />

        <div className={g.demoRow}>
          <span className={g.demoLabel}>Starts on</span>
          <ToggleDemo label="Avoid exposed ridgelines" initial />
        </div>

        <hr className={g.divider} />

        <div className={g.demoRow}>
          <span className={g.demoLabel}>Tokens</span>
          <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
            <span className={g.tokenChip}>duration.fast · easing.standard</span>
            <span className={g.tokenChip}>radius.pill (track + thumb)</span>
            <span className={g.tokenChip}>space.8+2 × space.6 track</span>
          </div>
        </div>
      </div>

      <p className={g.motionNote}>
        Motion: thumb translates <code>space.4 (16px)</code> on the x-axis;
        track transitions <code>background + border-color</code>. Both use{' '}
        <code>duration.fast (120ms)</code> + <code>easing.standard</code>. Drops
        under <code>prefers-reduced-motion</code>.
      </p>
    </section>
  )
}

// ---- OptionGroup section --------------------------------------------------

type EffortKey = 'easy' | 'moderate' | 'bigDay'
const effortOptions: EffortKey[] = ['easy', 'moderate', 'bigDay']
const effortLabels: Record<EffortKey, string> = {
  easy: 'Easy — under 6 mi, < 800 ft',
  moderate: 'Moderate — 6–10 mi, 800–2 k ft',
  bigDay: 'Big day — 10+ mi or 2 k+ ft',
}

type WhenKey = 'tomorrowMorning' | 'weekendMorning' | 'weekendAfternoon' | 'fullDay'
const whenOptions: WhenKey[] = ['tomorrowMorning', 'weekendMorning', 'weekendAfternoon', 'fullDay']
const whenLabels: Record<WhenKey, string> = {
  tomorrowMorning: 'Tomorrow morning',
  weekendMorning: 'This weekend, morning',
  weekendAfternoon: 'This weekend, afternoon',
  fullDay: 'Full day, any day',
}

function OptionGroupSection() {
  const [effort, setEffort] = useState<EffortKey>('moderate')
  const [when, setWhen] = useState<WhenKey>('weekendMorning')

  return (
    <section className={g.section}>
      <div className={g.sectionHead}>
        <h2 className={g.sectionTitle}>OptionGroup</h2>
        <p className={g.sectionDesc}>
          Single-select from a small set. Built on RAC RadioGroup — roving
          arrow-key navigation, structural selection (ink border + weight, no
          accent hue). Press feedback via <code>data-pressed</code>.
        </p>
      </div>

      <div className={g.demoBox}>
        <div className={g.demoRow}>
          <span className={g.demoLabel}>Effort (arrow-key navigate)</span>
          <OptionGroup label="Effort" value={effort} onChange={setEffort}>
            {effortOptions.map((key) => (
              <OptionButton key={key} value={key}>
                {effortLabels[key]}
              </OptionButton>
            ))}
          </OptionGroup>
        </div>

        <hr className={g.divider} />

        <div className={g.demoRow}>
          <span className={g.demoLabel}>Time frame</span>
          <OptionGroup label="Time frame" value={when} onChange={setWhen}>
            {whenOptions.map((key) => (
              <OptionButton key={key} value={key}>
                {whenLabels[key]}
              </OptionButton>
            ))}
          </OptionGroup>
        </div>

        <hr className={g.divider} />

        <div className={g.demoRow}>
          <span className={g.demoLabel}>Tokens</span>
          <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
            <span className={g.tokenChip}>border-color: text.primary (selected)</span>
            <span className={g.tokenChip}>weight.medium (selected)</span>
            <span className={g.tokenChip}>duration.fast · easing.standard</span>
          </div>
        </div>
      </div>
    </section>
  )
}

// ---- Sheet section --------------------------------------------------------

type SheetVariant = 'options' | 'back' | null

function SheetSection() {
  const [open, setOpen] = useState<SheetVariant>(null)
  const [origin, setOrigin] = useState('frontRoyal')

  return (
    <section className={g.section}>
      <div className={g.sectionHead}>
        <h2 className={g.sectionTitle}>Sheet</h2>
        <p className={g.sectionDesc}>
          Bottom-sheet modal with focus trap, Escape + scrim dismiss, focus
          return. Rise + fade on enter; drop + fade on exit. One concern per
          sheet.
        </p>
      </div>

      <div className={g.demoBox}>
        <div className={g.demoRow}>
          <span className={g.demoLabel}>Open + close (see the rise)</span>
          <button
            type="button"
            className={g.sheetTrigger}
            onClick={() => setOpen('options')}
          >
            Starting point
            <span className={g.arrow}>→</span>
          </button>
        </div>

        <hr className={g.divider} />

        <div className={g.demoRow}>
          <span className={g.demoLabel}>With Back affordance</span>
          <button
            type="button"
            className={g.sheetTrigger}
            onClick={() => setOpen('back')}
          >
            Effort (with Back)
            <span className={g.arrow}>→</span>
          </button>
        </div>

        <hr className={g.divider} />

        <div className={g.demoRow}>
          <span className={g.demoLabel}>Tokens</span>
          <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
            <span className={g.tokenChip}>overlay: opacity fast (120ms)</span>
            <span className={g.tokenChip}>panel: translateY base (160ms)</span>
            <span className={g.tokenChip}>elevation.overlay shadow</span>
          </div>
        </div>
      </div>

      <p className={g.motionNote}>
        Motion: overlay fades opacity with <code>duration.fast</code>; panel
        rises from <code>translateY(space.4)</code> with <code>duration.base (160ms)</code>.
        RAC provides <code>[data-entering]</code>/<code>[data-exiting]</code>
        for clean in/out. Drops under <code>prefers-reduced-motion</code>.
      </p>

      <Sheet
        isOpen={open === 'options'}
        onClose={() => setOpen(null)}
        title="Starting point"
      >
        <OptionGroup label="Starting point" value={origin} onChange={setOrigin}>
          {(['frontRoyal', 'luray', 'charlottesville'] as const).map((key) => (
            <OptionButton key={key} value={key}>
              {{ frontRoyal: 'Front Royal', luray: 'Luray', charlottesville: 'Charlottesville' }[key]}
            </OptionButton>
          ))}
        </OptionGroup>
      </Sheet>

      <Sheet
        isOpen={open === 'back'}
        onClose={() => setOpen(null)}
        onBack={() => setOpen(null)}
        title="Effort"
      >
        <OptionGroup label="Effort" value="moderate" onChange={() => {}}>
          <OptionButton value="easy">Easy — under 6 mi, &lt; 800 ft</OptionButton>
          <OptionButton value="moderate">Moderate — 6–10 mi, 800–2 k ft</OptionButton>
          <OptionButton value="bigDay">Big day — 10+ mi or 2 k+ ft</OptionButton>
        </OptionGroup>
      </Sheet>
    </section>
  )
}

// ---- Colour + motion reference --------------------------------------------

function TokenReference() {
  return (
    <section className={g.section}>
      <div className={g.sectionHead}>
        <h2 className={g.sectionTitle}>Live tokens</h2>
        <p className={g.sectionDesc}>
          Every swatch below is a live CSS custom property — change a token in{' '}
          <code>tokens/*.json</code> and it propagates here.
        </p>
      </div>

      <div className={g.demoBox}>
        <div className={g.demoRow}>
          <span className={g.demoLabel}>Surfaces</span>
          <div style={{ display: 'flex', gap: '8px' }}>
            {(['--surface-canvas', '--surface-raised', '--surface-press'] as const).map((v) => (
              <div key={v} style={{ display: 'grid', gap: '4px', flex: 1, minWidth: 0 }}>
                <div
                  style={{
                    height: '32px',
                    borderRadius: '6px',
                    background: `var(${v})`,
                    border: '1px solid var(--border-hairline)',
                  }}
                />
                <span
                  style={{
                    fontFamily: 'var(--font-family-mono)',
                    fontSize: '0.625rem',
                    color: 'var(--text-muted)',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                  }}
                >
                  {v.replace('--', '')}
                </span>
              </div>
            ))}
          </div>
        </div>

        <hr className={g.divider} />

        <div className={g.demoRow}>
          <span className={g.demoLabel}>Text</span>
          <div style={{ display: 'flex', gap: '8px' }}>
            {(['--text-primary', '--text-secondary', '--text-muted'] as const).map((v) => (
              <div key={v} style={{ display: 'grid', gap: '4px', flex: 1, minWidth: 0 }}>
                <div
                  style={{
                    height: '32px',
                    borderRadius: '6px',
                    background: `var(${v})`,
                    border: '1px solid var(--border-hairline)',
                  }}
                />
                <span
                  style={{
                    fontFamily: 'var(--font-family-mono)',
                    fontSize: '0.625rem',
                    color: 'var(--text-muted)',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                  }}
                >
                  {v.replace('--', '')}
                </span>
              </div>
            ))}
          </div>
        </div>

        <hr className={g.divider} />

        <div className={g.demoRow}>
          <span className={g.demoLabel}>Accent (signal only)</span>
          <div style={{ display: 'flex', gap: '8px' }}>
            {(['--signal-caution-fg', '--signal-caution-bg'] as const).map((v) => (
              <div key={v} style={{ display: 'grid', gap: '4px', flex: 1, minWidth: 0 }}>
                <div
                  style={{
                    height: '32px',
                    borderRadius: '6px',
                    background: `var(${v})`,
                    border: '1px solid var(--border-hairline)',
                  }}
                />
                <span
                  style={{
                    fontFamily: 'var(--font-family-mono)',
                    fontSize: '0.625rem',
                    color: 'var(--text-muted)',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                  }}
                >
                  {v.replace('--', '')}
                </span>
              </div>
            ))}
          </div>
        </div>

        <hr className={g.divider} />

        <div className={g.demoRow}>
          <span className={g.demoLabel}>Motion</span>
          <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
            <span className={g.tokenChip}>fast: 120ms</span>
            <span className={g.tokenChip}>base: 160ms</span>
            <span className={g.tokenChip}>easing: cubic-bezier(0.2, 0, 0, 1)</span>
          </div>
        </div>
      </div>
    </section>
  )
}

// ---- Root gallery ---------------------------------------------------------

export function Gallery() {
  return (
    <main className={g.page}>
      <p className={g.pageTitle}>Design system · component gallery</p>

      <SignalSection />
      <ToggleSection />
      <OptionGroupSection />
      <SheetSection />
      <TokenReference />
    </main>
  )
}
