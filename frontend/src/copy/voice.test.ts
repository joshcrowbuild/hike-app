/**
 * Voice & content lint (WP-6 / Epic 053).
 *
 * Flags banned-builder nouns in user-facing strings, per design-system-v0.2.md §I.7.
 * Banned words: Curation, Adjust, N checks, Checked N sources, frame, context,
 * personal context, fetched, not fetched, Couldn't verify:, options.
 *
 * The baseline allowlist documents EXISTING occurrences that pre-date v0.2 migration.
 * NEW violations are caught. WP-7 burns down the allowlist as components migrate.
 */
import { describe, it, expect } from 'vitest'
import fs from 'fs'
import path from 'path'

/**
 * Baseline allowlist of pre-v0.2 occurrences.
 * Each entry is { file, pattern, reason }. When the component/file migrates,
 * remove the entry here. WP-7 burns down this list as components migrate to v0.2.
 *
 * Files: 40+ violations across data/, screens/, and component layers.
 * Scope: type names, state strings, internal comments, test data shapes.
 * Reason: All pre-v0.2 code that will migrate during WP-2 (cards), WP-3 (detail),
 *   WP-4 (system states), and WP-7 (assembly + audit).
 */
const BASELINE_ALLOWLIST: Array<{
  file: string
  pattern: string
  reason: string
}> = [
  // ---- Data layer (vm.ts, feedConditions.ts, http) ----
  {
    file: 'vm.ts',
    pattern: 'SilenceState|not-fetched|frame',
    reason:
      'View model type definitions for coverage states + drive-distance frame (Phase 2 feature)',
  },
  {
    file: 'feedConditions.ts',
    pattern: 'not-fetched',
    reason: 'Data shape mapping coverage states to silence rows',
  },
  {
    file: 'httpPlanner.ts',
    pattern: 'not-fetched|fetched',
    reason: 'Type guard and state mapping for condition coverage (Epic 014)',
  },
  {
    file: 'source.ts',
    pattern: 'frame',
    reason: 'Internal data model comment (Phase 2 feature)',
  },
  {
    file: 'mockPlanner.ts',
    pattern: 'frame',
    reason: 'Test mock data setup',
  },
  {
    file: 'regionsCatalog.ts',
    pattern: 'Fetched',
    reason: 'Internal comment about region config lifecycle',
  },
  {
    file: 'AuthProvider.tsx',
    pattern: 'context',
    reason: 'React context API usage (architectural, not user-facing string)',
  },
  // ---- Screens layer (cards, detail, home, tuning) ----
  {
    file: 'BootShell.tsx',
    pattern: 'wordmark.*Curation',
    reason: 'Home screen pre-v0.2 heading (WP-7 replaces)',
  },
  {
    file: 'EvidencePanel.tsx',
    pattern: 'not-fetched|not checked here',
    reason: 'WP-3 string matching on legacy/wire values',
  },
  {
    file: 'ConditionStates.tsx',
    pattern: 'not-fetched|not checked here',
    reason: 'Coverage state to rendering logic (WP-2 owns the tier engine)',
  },
  {
    file: 'cardParts.tsx',
    pattern: 'not-fetched|Conditions not',
    reason: 'Condition silence rendering (WP-2 owns the tier engine)',
  },
  {
    file: 'Detail.tsx',
    pattern: 'not-fetched|ConditionSilence',
    reason: 'Detail-level condition rendering (WP-3 owns restyle)',
  },
  {
    file: 'RecommendationCard.tsx',
    pattern: 'frame|fetched|not-fetched',
    reason: 'TrailCard internal comments + condition rendering (WP-2 owns restyle)',
  },
  {
    file: 'Home.tsx',
    pattern: 'frame|options|fetched|Curation|Context|Adjust',
    reason:
      'Home screen state comments, feed logic, and tuning button (WP-7 assembly owns restyle)',
  },
  {
    file: 'Tuning.tsx',
    pattern: 'frame|context|Adjust',
    reason:
      'Tuning sheet pre-v0.2 labels (WP-3 renames; low priority internal refactor)',
  },
  {
    file: 'Gallery.tsx',
    pattern: 'Time frame|options|OptionGroup',
    reason: 'Storybook gallery demo only (not user-facing in production)',
  },
  {
    file: 'VisionPrototype.tsx',
    pattern: 'Options',
    reason: 'Prototype screen only (not in production)',
  },
  // ---- Map layer ----
  {
    file: 'svg.ts',
    pattern: 'frame',
    reason: 'SVG coordinate projection function comment (internal utility)',
  },
  // ---- Test files ----
  {
    file: 'ConditionStates.test.tsx',
    pattern: 'not-fetched|not checked here',
    reason: 'Test data shape & expectation (tests cover ConditionStates coverage states)',
  },
  {
    file: 'Detail.test.tsx',
    pattern: 'not-fetched|not checked here',
    reason: 'Test data shape & expectation (Epic 014 coverage states)',
  },
]

describe('Voice: banned-builder-noun lint', () => {
  it('should not introduce new uses of banned words in user-facing code', () => {
    const bannedPatterns = [
      /\bCuration\b/g, // not "Curated"
      /\bCurated\b/g,
      /\bAdjust\b(?!Sheet)/g, // AdjustSheet is a component name (refactor debt, in allowlist)
      /\bN checks\b/g,
      /\bChecked.*sources\b/g,
      /\bframe\b(?!work|ing|-[a-z])/gi, // allow "framework", "framing", compound words like "frame-X"
      /\bcontext\b(?!Text|Sentence|ribbon|button|adjust)/gi, // allow specific compounds
      /\bpersonal context\b/gi,
      /\bfetched(?!Sheet|At)\b/gi, // allow "AdjustSheet", "PanelSheet", "fetchedAt" if used
      /\bnot fetched\b/gi,
      /\bfetched\s+(at|on)\b/gi, // e.g. "fetched at runtime" — general usage, in allowlist
      /\bCouldn't verify:\b/g,
      /\boptions\b(?!Group|Sheet)/gi, // allow "OptionGroup" and "OptionSheet" (component names)
    ]

    const srcDir = path.join(process.cwd(), 'src')
    const violations: Array<{
      file: string
      line: number
      match: string
      lineText: string
    }> = []

    // Scan all TS/TSX files (excluding tests and node_modules)
    const walkDir = (dir: string) => {
      const files = fs.readdirSync(dir)
      for (const file of files) {
        const filePath = path.join(dir, file)
        const relPath = path.relative(srcDir, filePath)

        // Skip tests, node_modules, design tokens
        if (
          file.includes('.test.') ||
          file.includes('.stories.') ||
          file === 'node_modules' ||
          relPath.startsWith('tokens')
        ) {
          continue
        }

        const stat = fs.statSync(filePath)
        if (stat.isDirectory()) {
          walkDir(filePath)
        } else if (file.endsWith('.ts') || file.endsWith('.tsx')) {
          const content = fs.readFileSync(filePath, 'utf-8')
          const lines = content.split('\n')

          for (let i = 0; i < lines.length; i++) {
            const line = lines[i]

            // Skip comments and internal types/comments
            if (
              line.trim().startsWith('//') ||
              line.trim().startsWith('*') ||
              line.includes('@deprecated')
            ) {
              continue
            }

            for (const pattern of bannedPatterns) {
              const match = line.match(pattern)
              if (match) {
                // Check if this is in the allowlist
                const isAllowed = BASELINE_ALLOWLIST.some((entry) => {
                  if (!relPath.endsWith(entry.file)) return false
                  const allowRe = new RegExp(entry.pattern)
                  return allowRe.test(line)
                })

                if (!isAllowed) {
                  violations.push({
                    file: relPath,
                    line: i + 1,
                    match: match[0],
                    lineText: line.trim(),
                  })
                }
              }
            }
          }
        }
      }
    }

    walkDir(srcDir)

    if (violations.length > 0) {
      const report = violations
        .map(
          (v) =>
            `  ${v.file}:${v.line} — "${v.match}" in: ${v.lineText.substring(0, 80)}...`
        )
        .join('\n')
      expect.fail(
        `Found ${violations.length} banned-word violation(s):\n${report}\n\n` +
          'To fix: replace the banned word with the v0.2 equivalent from design-system-v0.2.md §I.7.\n' +
          'If this is pre-v0.2 code that should be allowlisted, add an entry to BASELINE_ALLOWLIST above.'
      )
    }
  })

  it('documents the baseline allowlist', () => {
    // This test just documents what's in the allowlist and why.
    // It always passes; it's a record of migration progress.
    expect(BASELINE_ALLOWLIST).toBeDefined()
    expect(BASELINE_ALLOWLIST.length).toBeGreaterThan(0)

    // Print the allowlist for debugging
    const summary = BASELINE_ALLOWLIST.map(
      (e) => `- ${e.file}: ${e.pattern} (${e.reason})`
    ).join('\n')

    console.log(
      `\nVoice allowlist (${BASELINE_ALLOWLIST.length} entries) — WP-7 burns this down:\n${summary}`
    )
  })
})
