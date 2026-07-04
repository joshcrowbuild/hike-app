import { useState } from 'react'

import { OptionButton, OptionGroup, Sheet, Toggle } from '../components'
import { effortLabels, partyLabels, todayLabels, whenLabels } from '../data/labels'
import { orderOrigins, useOrigins, type OriginOption } from '../data/regionsCatalog'
import type { EffortKey, PartyKey, TodayKey, TuningState, WhenKey } from '../types'

export type PanelKey = 'origin' | 'when' | 'effort' | 'party' | 'today'

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

function chipValue(panel: PanelKey, state: TuningState, origins: OriginOption[]): string {
  switch (panel) {
    case 'origin':
      return state.originCoords
        ? 'Your location'
        : (origins.find((o) => o.key === state.origin)?.label ?? '')
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

/**
 * "Near me": drives the search origin from a live device fix, not just the
 * map (Josh's stated preference — see PR notes). Button-triggered, so
 * permission is requested only on tap. Source-or-silence for location itself:
 * a denial or an unavailable API surfaces an honest message and falls back to
 * the named picker below — it never fabricates a position.
 */
function NearMeControl({ state, setState }: { state: TuningState; setState: SetState }) {
  const [locating, setLocating] = useState(false)
  const [note, setNote] = useState<string | null>(null)

  const useMyLocation = () => {
    if (typeof navigator === 'undefined' || !navigator.geolocation) {
      setNote('Location isn’t available here — pick a starting point below.')
      return
    }
    setLocating(true)
    setNote(null)
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setLocating(false)
        setState((current) => ({
          ...current,
          originCoords: { lat: pos.coords.latitude, lon: pos.coords.longitude },
        }))
      },
      (err) => {
        setLocating(false)
        setNote(
          err.code === err.PERMISSION_DENIED
            ? 'Location permission denied — pick a starting point below.'
            : 'Couldn’t get your location — pick a starting point below.',
        )
      },
      { enableHighAccuracy: true, timeout: 10_000 },
    )
  }

  if (state.originCoords) {
    return (
      <div className="facet-row" role="status">
        <span className="facet-label">Near me</span>
        <button
          type="button"
          className="text-action"
          onClick={() => setState((current) => ({ ...current, originCoords: undefined }))}
        >
          Use a named place instead
        </button>
      </div>
    )
  }

  return (
    <div>
      <button type="button" className="facet-row" onClick={useMyLocation} disabled={locating}>
        <span className="facet-label">Near me</span>
        <span className="facet-value">{locating ? 'Locating…' : 'Use current location'}</span>
      </button>
      {note ? (
        <p className="near-me-note" role="alert">
          {note}
        </p>
      ) : null}
    </div>
  )
}

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
  const { origins } = useOrigins()
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
            <span className="facet-value">{chipValue(facet.key, state, origins)}</span>
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
  const { origins } = useOrigins()
  if (!panel) return null
  return (
    <Sheet isOpen onClose={onClose} onBack={onBack} title={panelTitle(panel)}>
      {panel === 'origin' ? (
        <div className="origin-sheet">
          <NearMeControl state={state} setState={setState} />
          <OptionGroup
            label="Starting point"
            value={state.origin}
            onChange={(key) => setState((current) => ({ ...current, origin: key, originCoords: undefined }))}
          >
            {orderOrigins(origins, state.originCoords).map((o) => (
              <OptionButton key={o.key} value={o.key}>
                {o.label}
              </OptionButton>
            ))}
          </OptionGroup>
        </div>
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
