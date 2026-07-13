import React from 'react'
import ReactDOM from 'react-dom/client'

import App from './App'
import { Gallery } from './Gallery'
import { PlannerProvider } from './data/PlannerProvider'
import { resolveScope } from './data/resolveScope'
import { BootShell } from './screens/BootShell'
import './design/tokens.css'
import './styles.css'

const params = new URLSearchParams(window.location.search)

// The viewer scope is a real product axis (Rule #4): `?anon` browses the world
// with an empty scope (the n=0 floor, R7); otherwise the single-user overlay —
// but only when a dev secret was baked into this build (H1: prod ships none,
// so prod is always anonymous). Stage 8 replaces this with real auth + grants
// — the same ScopeContext shape.
const scope = resolveScope(params, import.meta.env.VITE_DEV_VIEWER_SECRET)

// `?gallery` is the trunk's component-gallery dev surface; it is provider-free.
const isGallery = params.has('gallery')

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    {isGallery ? (
      <Gallery />
    ) : (
      // BootShell is the designed cold-start first paint (craft review H1):
      // staged loading copy + skeleton chrome while /regions wakes the API.
      <PlannerProvider scope={scope} fallback={<BootShell />}>
        <App />
      </PlannerProvider>
    )}
  </React.StrictMode>,
)
