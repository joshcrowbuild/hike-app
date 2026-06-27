import { pointAtFraction } from '../../data/geo'
import type { TrailGeo } from '../../data/vm'
import { projectRoute } from './svg'

/**
 * The map's no-tiles / no-WebGL fallback (S3 AC-3.3): the route — which is app
 * data and always renders — drawn over a neutral background, never a blank
 * panel. Also the render under test (jsdom has no WebGL), so the honest states
 * and the scrub cursor are verifiable without a GL context. Approximate routes
 * stay dashed here too (D5).
 */
const BOX = { width: 320, height: 200, padX: 16, padY: 16 }

export function StaticRoute({
  geo,
  cursorFraction,
}: {
  geo: TrailGeo
  cursorFraction: number | null
}) {
  const { route, trailhead, summit, project } = projectRoute(geo.geometry, geo.trailhead, BOX, geo.summit)
  const dashed = geo.quality === 'approximate'
  const cursor =
    geo.geometry && cursorFraction != null ? project(pointAtFraction(geo.geometry, cursorFraction)) : null

  return (
    <svg
      className="map-static"
      viewBox={`0 0 ${BOX.width} ${BOX.height}`}
      preserveAspectRatio="xMidYMid meet"
      role="img"
      aria-label={geo.geometry ? 'Route over a neutral background (map tiles unavailable)' : 'Trailhead location'}
    >
      {route.length > 1 ? (
        <polyline
          points={route.map(([x, y]) => `${x},${y}`).join(' ')}
          className={dashed ? 'map-static-route map-static-route--dashed' : 'map-static-route'}
        />
      ) : null}
      {summit ? <circle cx={summit[0]} cy={summit[1]} r={4} className="map-static-summit" /> : null}
      <circle cx={trailhead[0]} cy={trailhead[1]} r={5.5} className="map-static-trailhead" />
      {cursor ? <circle cx={cursor[0]} cy={cursor[1]} r={5} className="map-static-cursor" /> : null}
    </svg>
  )
}
