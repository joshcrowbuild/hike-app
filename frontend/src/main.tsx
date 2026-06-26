import React from 'react'
import ReactDOM from 'react-dom/client'

import App from './App'
import { ANON_SCOPE, type ScopeContext } from './data/api'
import { PlannerProvider } from './data/PlannerProvider'
import './design/tokens.css'
import './styles.css'

// The viewer scope is a real product axis (Rule #4): `?anon` browses the world
// with an empty scope (the n=0 floor, R7); otherwise the single-user overlay.
// Stage 8 replaces this with real auth + grants — the same ScopeContext shape.
const JOSH: ScopeContext = { viewerId: 'josh', grantedIds: [] }
const scope = new URLSearchParams(window.location.search).has('anon') ? ANON_SCOPE : JOSH

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <PlannerProvider scope={scope}>
      <App />
    </PlannerProvider>
  </React.StrictMode>,
)
