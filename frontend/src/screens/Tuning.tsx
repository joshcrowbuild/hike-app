import { OptionButton, OptionGroup, Sheet, Toggle } from '../components'
import { effortLabels, originLabels, partyLabels, todayLabels, whenLabels } from '../data/labels'
import type { EffortKey, OriginKey, PartyKey, TodayKey, TuningState, WhenKey } from '../types'

export type PanelKey = 'origin' | 'when' | 'effort' | 'party' | 'today'

const originOptions: OriginKey[] = [
  'frontRoyal',
  'luray',
  'charlottesville',
  'richmond',
  'duck',
  'nagsHead',
  'hatteras',
  'ocracoke',
]
const whenOptions: WhenKey[] = ['tomorrowMorning', 'weekendMorning', 'weekendAfternoon', 'fullDay']
const effortOptions: EffortKey[] = ['easy', 'moderate', 'bigDay']
const partyOptions: PartyKey[] = ['solo', 'ruby', 'friends']
const todayOptions: TodayKey[] = ['standard', 'seekShade', 'bigViews', 'quieter']

const facetMeta: Array<{ key: PanelKey; label: string }> = [
  { key: 'when', label: 'When' },
  { key: 'origin', label: 'From' },
  { key: 'party', label: 'Party' },
  { key: 'effort', label: 'Effort' },
  { key: 'today', label: 'Today' },
]

export function panelTitle(panel: PanelKey): string {
  switch (panel) {
    case 'origin':
      return 'Starting point'
    case 'when':
      return 'Time frame'
    case 'effort':
      return 'Effort'
    case 'party':
      return 'Who is coming'
    case 'today':
      return 'Today'
  }
}

function chipValue(panel: PanelKey, state: TuningState): string {
  switch (panel) {
    case 'origin':
      return originLabels[state.origin]
    case 'when':
      return whenLabels[state.when]
    case 'effort':
      return effortLabels[state.effort]
    case 'party':
      return partyLabels[state.party]
    case 'today':
      return state.readinessOn ? `${todayLabels[state.today]} · tuned` : todayLabels[state.today]
  }
}

type SetState = React.Dispatch<React.SetStateAction<TuningState>>

export interface AdjustSheetProps {
  open: boolean
  state: TuningState
  setState: SetState
  onClose: () => void
  onOpenFacet: (key: PanelKey) => void
  /** Anonymous viewers see only the world facets; party/today are "you" (R7). */
  anonymous?: boolean
}

export function AdjustSheet({ open, state, setState, onClose, onOpenFacet, anonymous }: AdjustSheetProps) {
  if (!open) return null
  const facets = anonymous ? facetMeta.filter((f) => f.key !== 'party' && f.key !== 'today') : facetMeta
  return (
    <Sheet isOpen onClose={onClose} title="Adjust">
      <div className="facet-list">
        {facets.map((facet) => (
          <button
            key={facet.key}
            className="facet-row"
            type="button"
            onClick={() => onOpenFacet(facet.key)}
          >
            <span className="facet-label">{facet.label}</span>
            <span className="facet-value">{chipValue(facet.key, state)}</span>
          </button>
        ))}
      </div>

      <label className="refine">
        <span className="refine-label">Refine with a phrase</span>
        <input
          className="refine-input"
          type="text"
          value={state.prompt}
          onChange={(event) => setState((current) => ({ ...current, prompt: event.target.value }))}
          placeholder="cooler · quieter · good with Ruby"
        />
      </label>
    </Sheet>
  )
}

export interface PanelSheetProps {
  panel: PanelKey | null
  state: TuningState
  setState: SetState
  onClose: () => void
  onBack: () => void
}

export function PanelSheet({ panel, state, setState, onClose, onBack }: PanelSheetProps) {
  if (!panel) return null
  return (
    <Sheet isOpen onClose={onClose} onBack={onBack} title={panelTitle(panel)}>
      {panel === 'origin' ? (
        <OptionGroup
          label="Starting point"
          value={state.origin}
          onChange={(key) => setState((current) => ({ ...current, origin: key }))}
        >
          {originOptions.map((key) => (
            <OptionButton key={key} value={key}>
              {originLabels[key]}
            </OptionButton>
          ))}
        </OptionGroup>
      ) : null}

      {panel === 'when' ? (
        <OptionGroup
          label="Time frame"
          value={state.when}
          onChange={(key) => setState((current) => ({ ...current, when: key }))}
        >
          {whenOptions.map((key) => (
            <OptionButton key={key} value={key}>
              {whenLabels[key]}
            </OptionButton>
          ))}
        </OptionGroup>
      ) : null}

      {panel === 'effort' ? (
        <OptionGroup
          label="Effort"
          value={state.effort}
          onChange={(key) => setState((current) => ({ ...current, effort: key }))}
        >
          {effortOptions.map((key) => (
            <OptionButton key={key} value={key}>
              {effortLabels[key]}
            </OptionButton>
          ))}
        </OptionGroup>
      ) : null}

      {panel === 'party' ? (
        <OptionGroup
          label="Who is coming"
          value={state.party}
          onChange={(key) => setState((current) => ({ ...current, party: key }))}
        >
          {partyOptions.map((key) => (
            <OptionButton key={key} value={key}>
              {partyLabels[key]}
            </OptionButton>
          ))}
        </OptionGroup>
      ) : null}

      {panel === 'today' ? (
        <div className="today-sheet">
          <OptionGroup
            label="Today"
            value={state.today}
            onChange={(key) => setState((current) => ({ ...current, today: key }))}
          >
            {todayOptions.map((key) => (
              <OptionButton key={key} value={key}>
                {todayLabels[key]}
              </OptionButton>
            ))}
          </OptionGroup>
          <Toggle
            label="Match today’s readiness"
            description="Hide what today can’t support. Off unless you turn it on."
            isSelected={state.readinessOn}
            onChange={(on) => setState((current) => ({ ...current, readinessOn: on }))}
          />
        </div>
      ) : null}
    </Sheet>
  )
}
