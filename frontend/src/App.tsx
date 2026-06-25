import { useMemo, useState } from 'react'

import {
  buildFitLine,
  effortLabels,
  originLabels,
  partyLabels,
  selectTrails,
  todayLabels,
  whenLabels,
} from './data'
import type { EffortKey, OriginKey, PartyKey, TodayKey, Trail, TuningState, WhenKey } from './types'

type PanelKey = 'origin' | 'when' | 'effort' | 'party' | 'today'

const defaultState: TuningState = {
  origin: 'frontRoyal',
  when: 'weekendMorning',
  effort: 'moderate',
  party: 'ruby',
  today: 'standard',
  readinessOn: false,
  prompt: '',
}

const originOptions: OriginKey[] = ['frontRoyal', 'luray', 'charlottesville']
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

const formatDrive = (minutes: number) => `${minutes} min`

const contextSentence = (state: TuningState) =>
  `${whenLabels[state.when]} · from ${originLabels[state.origin]} · ${partyLabels[state.party]}`

const tunedNote = (state: TuningState) => {
  if (state.today === 'seekShade') return 'Tuned for shade'
  if (state.today === 'bigViews') return 'Tuned for views'
  if (state.today === 'quieter') return 'Tuned for quiet'
  if (state.readinessOn) return 'Tuned to today'
  return ''
}

function App() {
  const [state, setState] = useState<TuningState>(defaultState)
  const [openPanel, setOpenPanel] = useState<PanelKey | null>(null)
  const [tuningOpen, setTuningOpen] = useState(false)
  const [detailId, setDetailId] = useState<string | null>(null)

  const selected = useMemo(() => selectTrails(state), [state])
  const detailTrail = selected.find(({ trail }) => trail.id === detailId)?.trail ?? null

  if (detailTrail) {
    return (
      <div className="app-shell">
        <DetailView trail={detailTrail} state={state} onBack={() => setDetailId(null)} />
      </div>
    )
  }

  const note = tunedNote(state)
  const count = selected.length

  return (
    <div className="app-shell">
      <header className="topbar">
        <span className="wordmark">Curation</span>
      </header>

      <section className="frame">
        <button className="context" type="button" onClick={() => setTuningOpen(true)}>
          <span className="context-text">{contextSentence(state)}</span>
          <span className="context-adjust">Adjust</span>
        </button>
        {note ? <p className="frame-note">{note}</p> : null}
      </section>

      <section className="stack">
        <p className="stack-meta">{count === 1 ? '1 option' : `${count} options`} · Shenandoah</p>
        <div className="card-stack">
          {selected.map(({ trail }) => (
            <RecommendationCard
              key={trail.id}
              trail={trail}
              state={state}
              onOpen={() => setDetailId(trail.id)}
            />
          ))}
        </div>
        {count === 1 ? (
          <p className="sparse-note">One option really holds under this frame. Widen effort or party for more.</p>
        ) : null}
      </section>

      <AdjustSheet
        open={tuningOpen}
        state={state}
        setState={setState}
        onClose={() => setTuningOpen(false)}
        onOpenFacet={(key) => {
          setTuningOpen(false)
          setOpenPanel(key)
        }}
      />

      <PanelSheet
        panel={openPanel}
        state={state}
        setState={setState}
        onClose={() => setOpenPanel(null)}
        onBack={() => {
          setOpenPanel(null)
          setTuningOpen(true)
        }}
      />
    </div>
  )
}

type RecommendationCardProps = {
  trail: Trail
  state: TuningState
  onOpen: () => void
}

function RecommendationCard({ trail, state, onOpen }: RecommendationCardProps) {
  return (
    <article className="card">
      <button className="card-tap" type="button" onClick={onOpen} aria-label={`Open ${trail.name}`}>
        <p className="card-place">{trail.placeCue}</p>

        <div className="card-id">
          <h3 className="card-name">{trail.name}</h3>
          <p className="card-area">
            {trail.area} · {trail.routeShape}
          </p>
        </div>

        <TerrainGlyph trail={trail} />

        <div className="decision">
          <DecisionItem label="Drive" value={formatDrive(trail.drives[state.origin])} />
          <DecisionItem
            label="Trail"
            value={`${trail.distanceMiles.toFixed(1)} mi · ${trail.ascentFeet.toLocaleString()} ft`}
          />
        </div>

        <div className="condition">
          <span className="condition-label">Now</span>
          <span className="condition-value">{trail.conditionValue}</span>
        </div>

        {trail.caution ? <p className="signal">{trail.caution}</p> : null}

        <p className="fit">{buildFitLine(trail, state)}</p>

        <div className="card-foot">
          <span className="freshness">{trail.freshness}</span>
          <span className="open-detail">Open detail</span>
        </div>
      </button>
    </article>
  )
}

type DecisionItemProps = {
  label: string
  value: string
}

function DecisionItem({ label, value }: DecisionItemProps) {
  return (
    <div className="decision-item">
      <span className="decision-label">{label}</span>
      <span className="decision-value">{value}</span>
    </div>
  )
}

type TerrainGlyphProps = {
  trail: Trail
}

function TerrainGlyph({ trail }: TerrainGlyphProps) {
  const points = trail.profilePath
    .map((value, index) => `${index * 36},${44 - value * 0.42}`)
    .join(' ')

  return (
    <svg className="glyph" viewBox="0 0 288 46" preserveAspectRatio="none" aria-hidden="true">
      <line x1="0" y1="45" x2="288" y2="45" className="glyph-base" />
      <polyline points={points} className="glyph-line" />
    </svg>
  )
}

type TerrainPreviewProps = {
  trail: Trail
  variant: 'terrain' | 'profile'
}

function TerrainPreview({ trail, variant }: TerrainPreviewProps) {
  const values = variant === 'terrain' ? trail.terrainPath : trail.profilePath
  const points = values
    .map((value, index) => `${12 + index * 34},${96 - value}`)
    .join(' ')

  return (
    <div className="terrain-preview">
      <div className="terrain-preview__label">{variant === 'terrain' ? 'Route / terrain' : 'Elevation profile'}</div>
      <svg viewBox="0 0 320 120" aria-hidden="true">
        {[24, 48, 72, 96].map((line) => (
          <path
            key={line}
            d={`M 0 ${line} C 44 ${line - 7}, 94 ${line + 4}, 160 ${line - 3} S 250 ${line + 7}, 320 ${line - 1}`}
            className="terrain-contour"
          />
        ))}
        <polyline points={points} className="terrain-path" />
      </svg>
    </div>
  )
}

type TrustCueProps = {
  trail: Trail
  compact: boolean
}

function TrustCue({ trail, compact }: TrustCueProps) {
  return (
    <div className={`trust-cue ${compact ? 'trust-cue--compact' : ''}`}>
      <p>{trail.freshness}</p>
      {!compact ? (
        <ul className="source-list">
          {trail.sources.map((source) => (
            <li key={source}>{source}</li>
          ))}
        </ul>
      ) : null}
    </div>
  )
}

type PanelSheetProps = {
  panel: PanelKey | null
  state: TuningState
  setState: React.Dispatch<React.SetStateAction<TuningState>>
  onClose: () => void
  onBack: () => void
}

function PanelSheet({ panel, state, setState, onClose, onBack }: PanelSheetProps) {
  if (!panel) {
    return null
  }

  return (
    <div className="sheet-overlay" role="presentation" onClick={onClose}>
      <div className="sheet" role="dialog" aria-modal="true" onClick={(event) => event.stopPropagation()}>
        <div className="sheet-header">
          <button className="sheet-back" type="button" onClick={onBack}>
            Back
          </button>
          <h3 className="sheet-title">{panelTitle(panel)}</h3>
          <button className="sheet-close" type="button" onClick={onClose}>
            Done
          </button>
        </div>

        {panel === 'origin' ? (
          <OptionGrid
            options={originOptions}
            selected={state.origin}
            getLabel={(key) => originLabels[key]}
            onSelect={(key) => {
              setState((current) => ({ ...current, origin: key }))
              onClose()
            }}
          />
        ) : null}

        {panel === 'when' ? (
          <OptionGrid
            options={whenOptions}
            selected={state.when}
            getLabel={(key) => whenLabels[key]}
            onSelect={(key) => {
              setState((current) => ({ ...current, when: key }))
              onClose()
            }}
          />
        ) : null}

        {panel === 'effort' ? (
          <OptionGrid
            options={effortOptions}
            selected={state.effort}
            getLabel={(key) => effortLabels[key]}
            onSelect={(key) => {
              setState((current) => ({ ...current, effort: key }))
              onClose()
            }}
          />
        ) : null}

        {panel === 'party' ? (
          <OptionGrid
            options={partyOptions}
            selected={state.party}
            getLabel={(key) => partyLabels[key]}
            onSelect={(key) => {
              setState((current) => ({ ...current, party: key }))
              onClose()
            }}
          />
        ) : null}

        {panel === 'today' ? (
          <div className="today-sheet">
            <OptionGrid
              options={todayOptions}
              selected={state.today}
              getLabel={(key) => todayLabels[key]}
              onSelect={(key) => setState((current) => ({ ...current, today: key }))}
            />
            <button
              className={`toggle-row ${state.readinessOn ? 'toggle-row--active' : ''}`}
              type="button"
              onClick={() => setState((current) => ({ ...current, readinessOn: !current.readinessOn }))}
            >
              <div>
                <span className="toggle-label">Match today’s readiness</span>
                <p className="toggle-copy">Hide what today can’t support. Off unless you turn it on.</p>
              </div>
              <span className="toggle-switch">{state.readinessOn ? 'On' : 'Off'}</span>
            </button>
          </div>
        ) : null}
      </div>
    </div>
  )
}

type AdjustSheetProps = {
  open: boolean
  state: TuningState
  setState: React.Dispatch<React.SetStateAction<TuningState>>
  onClose: () => void
  onOpenFacet: (key: PanelKey) => void
}

function AdjustSheet({ open, state, setState, onClose, onOpenFacet }: AdjustSheetProps) {
  if (!open) {
    return null
  }

  return (
    <div className="sheet-overlay" role="presentation" onClick={onClose}>
      <div className="sheet" role="dialog" aria-modal="true" onClick={(event) => event.stopPropagation()}>
        <div className="sheet-header">
          <h3 className="sheet-title">Adjust</h3>
          <button className="sheet-close" type="button" onClick={onClose}>
            Done
          </button>
        </div>

        <div className="facet-list">
          {facetMeta.map((facet) => (
            <button key={facet.key} className="facet-row" type="button" onClick={() => onOpenFacet(facet.key)}>
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
      </div>
    </div>
  )
}

type OptionGridProps<T extends string> = {
  options: readonly T[]
  selected: T
  getLabel: (option: T) => string
  onSelect: (option: T) => void
}

function OptionGrid<T extends string>({ options, selected, getLabel, onSelect }: OptionGridProps<T>) {
  return (
    <div className="option-grid">
      {options.map((option) => (
        <button
          key={option}
          className={`option-button ${selected === option ? 'option-button--selected' : ''}`}
          type="button"
          onClick={() => onSelect(option)}
        >
          {getLabel(option)}
        </button>
      ))}
    </div>
  )
}

type DetailViewProps = {
  trail: Trail
  state: TuningState
  onBack: () => void
}

function DetailView({ trail, state, onBack }: DetailViewProps) {
  return (
    <section className="detail">
      <header className="detail-top">
        <button className="back" type="button" onClick={onBack}>
          Back
        </button>
        <span className="wordmark">Detail</span>
      </header>

      <section className="detail-head">
        <p className="kicker">Viability</p>
        <h1 className="detail-name">{trail.name}</h1>
        <p className="detail-area">
          {trail.area} · {trail.routeShape}
        </p>

        <div className="detail-facts">
          <DecisionItem label="Drive" value={formatDrive(trail.drives[state.origin])} />
          <DecisionItem label="Distance" value={`${trail.distanceMiles.toFixed(1)} mi`} />
          <DecisionItem label="Ascent" value={`${trail.ascentFeet.toLocaleString()} ft`} />
          <DecisionItem label="Duration" value={trail.durationHours} />
        </div>

        <div className="condition condition--detail">
          <span className="condition-label">Now</span>
          <span className="condition-value">{trail.conditionValue}</span>
        </div>

        {trail.caution ? <p className="signal signal--detail">{trail.caution}</p> : null}
        <p className="detail-practical">{trail.practicalNote}</p>
      </section>

      <section className="detail-block">
        <p className="kicker">Terrain</p>
        <div className="terrain-grid terrain-grid--detail">
          <TerrainPreview trail={trail} variant="terrain" />
          <TerrainPreview trail={trail} variant="profile" />
        </div>
      </section>

      <section className="detail-block">
        <p className="kicker">Character</p>
        <p className="prose">{trail.detailCharacter}</p>
      </section>

      <section className="detail-block">
        <p className="kicker">Why it fits</p>
        <p className="prose">{buildFitLine(trail, state)}</p>
      </section>

      <section className="detail-block">
        <p className="kicker">Sources</p>
        <TrustCue trail={trail} compact={false} />
      </section>
    </section>
  )
}

type MetricProps = {
  label: string
  value: string
}

function Metric({ label, value }: MetricProps) {
  return (
    <div className="metric">
      <span className="metric-label">{label}</span>
      <strong className="metric-value">{value}</strong>
    </div>
  )
}

function chipValue(panel: PanelKey, state: TuningState) {
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
      return state.readinessOn ? `${todayLabels[state.today]} · Ready` : todayLabels[state.today]
  }
}

function panelTitle(panel: PanelKey) {
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

export default App
