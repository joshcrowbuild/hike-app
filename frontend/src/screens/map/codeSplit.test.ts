import { existsSync, readFileSync, statSync } from 'node:fs'
import { basename, dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { describe, expect, it } from 'vitest'

/**
 * Architectural guard for D6 / AC-2.1: the feed must never import the map
 * library. We walk the STATIC import graph from each feed entry (following
 * `import … from` / `export … from`, but NOT `import type` — erased — and NOT
 * dynamic `import()` — the code-split boundary). MapLibre must be unreachable
 * that way, and only `MapPanel` may import it, behind TerrainMap's lazy import.
 */
const here = dirname(fileURLToPath(import.meta.url))
const SRC = resolve(here, '../..')
const MAP_LIB = /(?:^|[/'"])(maplibre-gl|react-map-gl)/

function staticSpecifiers(code: string): string[] {
  const specs: string[] = []
  // `import …/export … from '…'`, excluding `import type`/`export type`.
  const fromRe = /^\s*(?:import|export)\s+(?!type\b)[^'"]*?from\s*['"]([^'"]+)['"]/gm
  // Bare side-effect imports: `import '…'`.
  const sideRe = /^\s*import\s+['"]([^'"]+)['"]/gm
  for (const re of [fromRe, sideRe]) {
    let m: RegExpExecArray | null
    while ((m = re.exec(code))) specs.push(m[1])
  }
  return specs
}

function resolveLocal(spec: string, fromFile: string): string | null {
  if (!spec.startsWith('.')) return null
  const base = resolve(dirname(fromFile), spec)
  const candidates = [base, `${base}.ts`, `${base}.tsx`, resolve(base, 'index.ts'), resolve(base, 'index.tsx')]
  return candidates.find((c) => existsSync(c) && statSync(c).isFile()) ?? null
}

interface Graph {
  files: Set<string>
  bareImports: Set<string>
}

function staticGraph(entry: string): Graph {
  const files = new Set<string>()
  const bareImports = new Set<string>()
  const stack = [entry]
  while (stack.length > 0) {
    const file = stack.pop()!
    if (files.has(file)) continue
    files.add(file)
    for (const spec of staticSpecifiers(readFileSync(file, 'utf8'))) {
      if (spec.startsWith('.')) {
        const resolved = resolveLocal(spec, file)
        if (resolved) stack.push(resolved)
      } else {
        bareImports.add(spec)
      }
    }
  }
  return { files, bareImports }
}

const FEED_ENTRIES = ['screens/Home.tsx', 'screens/RecommendationCard.tsx', 'screens/cardParts.tsx'].map((f) =>
  resolve(SRC, f),
)

describe('code split — the feed path is free of the map library (AC-2.1)', () => {
  for (const entry of FEED_ENTRIES) {
    it(`${basename(entry)} reaches no map-library import`, () => {
      const { files, bareImports } = staticGraph(entry)
      expect([...bareImports].filter((s) => MAP_LIB.test(s))).toEqual([])
      for (const file of files) {
        const hits = staticSpecifiers(readFileSync(file, 'utf8')).filter((s) => MAP_LIB.test(s))
        expect(hits, `${basename(file)} statically imports the map library`).toEqual([])
      }
    })
  }

  it('MapPanel is the real static importer of the map library', () => {
    const code = readFileSync(resolve(SRC, 'screens/map/MapPanel.tsx'), 'utf8')
    expect(staticSpecifiers(code).some((s) => MAP_LIB.test(s))).toBe(true)
  })

  it('TerrainMap reaches MapPanel only through a dynamic import', () => {
    const code = readFileSync(resolve(SRC, 'screens/map/TerrainMap.tsx'), 'utf8')
    expect(staticSpecifiers(code).some((s) => /MapPanel/.test(s))).toBe(false)
    expect(/import\(\s*['"][^'"]*MapPanel['"]\s*\)/.test(code)).toBe(true)
  })
})
