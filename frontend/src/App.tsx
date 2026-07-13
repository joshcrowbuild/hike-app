import { useEffect, useState } from 'react'

import { useRoute } from './app/useRoute'
import { useIsAnonymous } from './data/PlannerProvider'
import { useOrigins } from './data/regionsCatalog'
import { readStoredTuning, writeStoredTuning } from './data/tuningStorage'
import { Detail } from './screens/Detail'
import { Home } from './screens/Home'
import { Outcome } from './screens/Outcome'
import { AdjustSheet, PanelSheet, type PanelKey } from './screens/Tuning'
import type { TuningState } from './types'

// Default party is SOLO (R6) so the canonical solo→Ruby reshape is visible:
// switching to Ruby visibly sets the committing option aside, disclosed.
const defaultState: TuningState = {
  origin: 'frontRoyal',
  when: 'weekendMorning',
  effort: 'moderate',
  party: 'solo',
  today: 'standard',
  readinessOn: false,
  prompt: '',
}

function App() {
  const anonymous = useIsAnonymous()
  const { route, navigate, back } = useRoute()
  // The frame survives a reload (craft review M4): initialized from the
  // device-local store — lazily, so the persisted frame paints on the FIRST
  // committed render (no default-then-swap flash) — and written back on every
  // change. `readStoredTuning` degrades to null on any doubt.
  const [tuning, setTuning] = useState<TuningState>(() => readStoredTuning() ?? defaultState)
  const [tuningOpen, setTuningOpen] = useState(false)
  const [openPanel, setOpenPanel] = useState<PanelKey | null>(null)

  useEffect(() => {
    writeStoredTuning(tuning)
  }, [tuning])

  // A persisted origin can outlive the catalog that named it (a region file
  // removed between visits): once the catalog is loaded, an unknown key falls
  // back to the built-in default — or the first cataloged origin if even that
  // is gone — rather than planning from a place that no longer exists.
  const { origins } = useOrigins()
  useEffect(() => {
    if (origins.length === 0) return
    if (origins.some((o) => o.key === tuning.origin)) return
    const fallback = origins.some((o) => o.key === defaultState.origin)
      ? defaultState.origin
      : origins[0].key
    setTuning((current) => ({ ...current, origin: fallback }))
  }, [origins, tuning.origin])

  return (
    <>
      {route.name === 'trail' ? (
        <Detail id={route.id} onBack={back} onReplan={() => navigate({ name: 'home' })} />
      ) : route.name === 'outcome' ? (
        <Outcome episodeId={route.episodeId} onDone={() => navigate({ name: 'home' })} />
      ) : (
        <Home
          tuning={tuning}
          anonymous={anonymous}
          onOpenTuning={() => setTuningOpen(true)}
          onOpenTrail={(id) => navigate({ name: 'trail', id })}
          onOpenOutcome={(episodeId) => navigate({ name: 'outcome', episodeId })}
          onApplyTuning={(next) => setTuning(next)}
        />
      )}

      {/* Sheets are overlays, not routes — they do not push history (R12). */}
      <AdjustSheet
        open={tuningOpen}
        state={tuning}
        setState={setTuning}
        anonymous={anonymous}
        onClose={() => setTuningOpen(false)}
        onOpenFacet={(key) => {
          setTuningOpen(false)
          setOpenPanel(key)
        }}
      />

      <PanelSheet
        panel={openPanel}
        state={tuning}
        setState={setTuning}
        onClose={() => setOpenPanel(null)}
        onBack={() => {
          setOpenPanel(null)
          setTuningOpen(true)
        }}
      />
    </>
  )
}

export default App
