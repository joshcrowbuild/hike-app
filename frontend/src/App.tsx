import { useState } from 'react'

import { useRoute } from './app/useRoute'
import { useIsAnonymous } from './data/PlannerProvider'
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
  const [tuning, setTuning] = useState<TuningState>(defaultState)
  const [tuningOpen, setTuningOpen] = useState(false)
  const [openPanel, setOpenPanel] = useState<PanelKey | null>(null)

  return (
    <>
      {route.name === 'trail' ? (
        <Detail
          id={route.id}
          origin={anonymous ? undefined : tuning.origin}
          onBack={back}
          onReplan={() => navigate({ name: 'home' })}
        />
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
