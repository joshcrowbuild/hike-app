/**
 * The repetition snapshot test (Epic 046 S6, AC-6.1) — the process-net guard
 * that would have caught the "just now" ×11 defect itself (sweep §1: the
 * Dickey Ridge Detail screen, root-caused to A3 in
 * `generated-string-integrity-sweep-2026-07.md`). Renders Detail and the Home
 * feed with a realistic ALL-FRESH live payload — every condition fetched in
 * one JIT batch, every fetched fact stamped "just now" — extracts the
 * assembled surface's VISIBLE text, and asserts no meaningful token repeats
 * more than 3× on either surface. A generated string is *individually*
 * correct at every call site (sweep §1 item 2); this is the guard that checks
 * the WHOLE assembled surface instead, which is exactly the blind spot a
 * literal-grep microcopy audit cannot see (S6 AC-6.3).
 *
 * Fixtures mirror `Detail.test.tsx`'s `card`/`readyClient`/`renderDetail` and
 * `Home.test.tsx`'s `feedWith`/`renderHomeWith` + the "Home Context Ribbon"
 * block's region-card pattern (same CardVM/FeedVM shapes, same live
 * full-source/short-status pairing) rather than a hand-rolled payload — see
 * those two files for the originals this one's local helpers are modeled on.
 *
 * Verified as a REAL (non-vacuous) guard by temporarily forcing `sharedAmong`
 * (`../data/feedConditions.ts` — the one primitive S1's block-scope stamp,
 * the Home compact-group age, and the Sources section descriptor all share)
 * to always return `undefined` — i.e. reverting S1's "collapse-when-agree"
 * behaviour everywhere it applies: Detail's "just now" count went 1 → 4 and
 * Home's went 3 → 4, both crossing the >3 threshold below and failing all
 * three tests in this file (confirmed by actually running it in that state).
 * The edit was reverted before landing; `sharedAmong` is untouched here.
 */
import { act, render } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { ANON_SCOPE } from '../data/api'
import { PlannerProvider } from '../data/PlannerProvider'
import type { PlannerClient } from '../data/source'
import type { CardVM, FeedVM } from '../data/vm'
import type { TuningState } from '../types'
import { Detail } from './Detail'
import { Home } from './Home'

// ── repetition-counting helpers ─────────────────────────────────────────────

/** Above this, a repeated token is the emergent noise the sweep named — at or
 *  below it, two or three rows/cards legitimately sharing one word (e.g. two
 *  "present" rows both reading "reported") is normal prose, not a defect. */
const REPEAT_LIMIT = 3

/**
 * What a SIGHTED user actually reads: `textContent` with every sr-only echo
 * stripped first. This codebase carries sr-only text two ways — the plain
 * `"sr-only"` class (`ConditionStates.tsx`, `cardParts.tsx`) and the
 * vanilla-extract `srOnly` token (`Icon`, `Confidence`; compiles to a
 * `*srOnly*`-bearing debug class name outside production builds) — both are a
 * *deliberate*, separate accessible-name echo of the same visible label, never
 * the visible-clutter repetition this test targets, so both are excluded
 * before counting.
 */
function visibleText(container: HTMLElement): string {
  const clone = container.cloneNode(true) as HTMLElement
  clone.querySelectorAll('.sr-only, [class*="srOnly"]').forEach((el) => el.remove())
  // Walk text nodes and join with a space rather than reading `.textContent`
  // directly: two adjacent sibling elements with no literal whitespace between
  // them in the JSX source (common — visual spacing comes from CSS) collapse
  // under plain `textContent` ("…checks" + "a" → "checksa"), silently merging
  // two real words into a token that matches neither — an undercount, never an
  // overcount, but one worth closing rather than leaving as a wobble in the
  // word-frequency pass below.
  const walker = document.createTreeWalker(clone, NodeFilter.SHOW_TEXT)
  const parts: string[] = []
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    if (node.textContent) parts.push(node.textContent)
  }
  return parts.join(' ')
}

function countOccurrences(text: string, phrase: string): number {
  return text.split(phrase).length - 1
}

/** Function words that legitimately recur throughout any prose (articles,
 *  prepositions, pronouns) — excluded so the generic sweep below targets
 *  CONTENT tokens (values, stamps, source names, state words), which is what
 *  the sweep's defect class actually is made of. Deliberately NOT excluding
 *  "just"/"now": those are exactly the tokens this test exists to watch. */
const STOPWORDS = new Set([
  'the', 'a', 'an', 'of', 'in', 'on', 'at', 'to', 'and', 'or', 'is', 'are',
  'this', 'that', 'your', 'you', 'it', 'its', 'for', 'with', 'as', 'by',
  'from', 'not', 'no', 'be', 'was', 'were', 'has', 'have', 'had', 'once',
])

/** Lower-cased word-ish tokens (length ≥ 3, so single-letter test ids and
 *  units like "ft" never enter the count) with the stopwords above dropped. */
function wordCounts(text: string): Map<string, number> {
  const counts = new Map<string, number>()
  for (const raw of text.toLowerCase().match(/[a-z][a-z'-]{2,}/g) ?? []) {
    if (STOPWORDS.has(raw)) continue
    counts.set(raw, (counts.get(raw) ?? 0) + 1)
  }
  return counts
}

/**
 * Asserts no meaningful token — the freshness stamp above all, and generally
 * any content word — repeats more than REPEAT_LIMIT times on one rendered
 * surface. This is deliberately over the WHOLE assembled surface (not one
 * component in isolation): the sweep's point (§1 item 2) is that each
 * generator is individually a clean, unit-tested honesty function — the noise
 * is emergent only once every caller lands on the same page at once.
 */
function assertNoOverRepetition(container: HTMLElement, surface: string): void {
  const text = visibleText(container)
  const justNow = countOccurrences(text, 'just now')
  expect(justNow, `"just now" appeared ${justNow}× on ${surface}: ${text}`).toBeLessThanOrEqual(REPEAT_LIMIT)
  for (const [word, count] of wordCounts(text)) {
    expect(count, `"${word}" repeated ${count}× on ${surface}: ${text}`).toBeLessThanOrEqual(REPEAT_LIMIT)
  }
}

// ── Detail surface (mirrors Detail.test.tsx's card/readyClient/renderDetail) ─

function detailClient(vm: CardVM): PlannerClient {
  return {
    plan: () =>
      Promise.resolve({
        query: '',
        cards: [],
        notices: [],
        setAside: [],
        heldBack: [],
        readiness: { on: false, state: 'off' },
        dataSource: 'live' as const,
      }),
    getCard: () => Promise.resolve(vm),
    trailWater: () => Promise.resolve(null),
    recentEpisodes: () => Promise.resolve([]),
    getEpisode: () => Promise.resolve(null),
    recordOutcome: () => Promise.reject(new Error('not used')),
  } as unknown as PlannerClient
}

async function renderDetailSurface(vm: CardVM) {
  const result = render(
    <PlannerProvider scope={ANON_SCOPE} client={detailClient(vm)}>
      <Detail id={vm.id} onBack={() => {}} onReplan={() => {}} />
    </PlannerProvider>,
  )
  await act(async () => {})
  return result
}

/**
 * All six condition kinds in the SAME JIT batch — the exact shape of the
 * "just now" ×11 defect (sweep §1): weather + air answered (a value line
 * each, Epic 046 S1's full-source/short-status live wire shape), fire checked
 * clear, water a coverage gap — four kinds an actual source answered, all
 * fetched at the same instant — plus closures a real-world mixed-outcome
 * failure (NPS timed out while the rest answered) and permits not fetched at
 * all (B8 — a facility count is never dressed up as a permit answer, so this
 * one carries no age to share).
 */
const ALL_FRESH_CARD: CardVM = {
  id: 'dickey-ridge',
  name: 'Dickey Ridge Trail',
  distanceMi: 2.4,
  warnings: [],
  conditionLines: [
    {
      text: 'Sunny 90°F · NWS, just now',
      body: 'Sunny 90°F',
      source: 'NWS api.weather.gov · single authoritative source (NWS LWX 56,65)',
      age: 'just now',
      confidence: 'stated',
      provenance: 'live',
    },
    {
      text: 'AQI 32 (Good) · AirNow, just now',
      body: 'AQI 32 (Good)',
      source: 'AirNow · single aggregated source',
      age: 'just now',
      confidence: 'stated',
      provenance: 'live',
    },
  ],
  conditions: [
    { kind: 'weather', state: 'present', source: 'NWS', checkedAgo: 'just now' },
    { kind: 'air', state: 'present', source: 'AirNow', checkedAgo: 'just now' },
    { kind: 'fire', state: 'no-hazard', source: 'NASA FIRMS', checkedAgo: 'just now' },
    { kind: 'water', state: 'no-data', source: 'USGS', checkedAgo: 'just now', detail: 'no gauge within 30 mi' },
    { kind: 'closures', state: 'unavailable' },
    { kind: 'permits', state: 'not-fetched' },
  ],
}

describe('Detail — repetition snapshot over the assembled surface (Epic 046 S6 AC-6.1)', () => {
  it('never lets the freshness stamp (or any other token) repeat more than 3× on a fully-fresh 6-kind batch', async () => {
    const { container } = await renderDetailSurface(ALL_FRESH_CARD)
    assertNoOverRepetition(container, 'Detail')
  })

  it('collapses the fully-agreeing batch to exactly ONE freshness stamp (pins the count the collapse should produce)', async () => {
    const { container } = await renderDetailSurface(ALL_FRESH_CARD)
    // Four of the six kinds were actually probed (weather, air, fire, water)
    // and all share "just now" (binding decision 2 / AC-1.4): one block-scope
    // stamp for the whole table, not one per row. A regression that
    // re-expands the per-row age would jump this straight to 4 — already past
    // the >3 guard above, but pinned exactly here so the regression is
    // visible at its first row, not just once it crosses the generic
    // threshold.
    expect(countOccurrences(visibleText(container), 'just now')).toBeLessThanOrEqual(1)
  })
})

// ── Home feed surface (mirrors Home.test.tsx's feedWith/renderHomeWith and
//    the "Home Context Ribbon" block's region-card pattern) ────────────────

const TUNING: TuningState = {
  origin: 'frontRoyal',
  when: 'weekendMorning',
  effort: 'moderate',
  party: 'solo',
  today: 'standard',
  readinessOn: false,
  prompt: '',
}

function homeClient(feed: FeedVM): PlannerClient {
  return {
    plan: () => Promise.resolve(feed),
    recentEpisodes: () => Promise.resolve([]),
  } as unknown as PlannerClient
}

async function renderHomeSurface(feed: FeedVM) {
  const result = render(
    <PlannerProvider scope={ANON_SCOPE} client={homeClient(feed)}>
      <Home
        tuning={TUNING}
        anonymous
        onOpenTuning={() => {}}
        onOpenTrail={() => {}}
        onOpenOutcome={() => {}}
        onApplyTuning={() => {}}
      />
    </PlannerProvider>,
  )
  await act(async () => {})
  return result
}

/**
 * One card of a region-wide all-fresh batch — the region-scope half of the
 * same JIT batch `ALL_FRESH_CARD` exercises on Detail (weather + air
 * answered, fire + closures checked clear). Two of these, identical, are the
 * minimum `splitFeedConditions` (F3/F9a) needs for a strict majority
 * (`SHARED_MIN_CARDS`) to hoist to the ONE feed ribbon — a card carrying
 * nothing distinct from its neighbour is precisely when the old per-card
 * repetition (and, on the ribbon itself, an uncollapsed age) would show.
 * Deliberately the minimum, not more: each card's own <Verdict> is NEVER
 * hoisted (F1 — a card's go/no-go must never be hidden), so it legitimately
 * repeats once per card regardless of how many cards share it; two keeps that
 * expected per-card echo inside the >3 tolerance instead of stacking a third
 * independent "nothing flagged" alongside it for no reason this test needs.
 */
function regionCard(id: string): CardVM {
  return {
    id,
    name: id,
    distanceMi: 2,
    warnings: [],
    conditionLines: [
      {
        text: 'Mostly Cloudy 61°F · NWS, just now',
        body: 'Mostly Cloudy 61°F',
        source: 'NWS api.weather.gov · single authoritative source (NWS LWX 56,65)',
        age: 'just now',
        confidence: 'stated',
        provenance: 'live',
      },
      {
        text: 'AQI 30 (Good) · AirNow, just now',
        body: 'AQI 30 (Good)',
        source: 'AirNow · single aggregated source',
        age: 'just now',
        confidence: 'stated',
        provenance: 'live',
      },
    ],
    conditions: [
      { kind: 'weather', state: 'present', source: 'NWS', checkedAgo: 'just now' },
      { kind: 'air', state: 'present', source: 'AirNow', checkedAgo: 'just now' },
      { kind: 'fire', state: 'no-hazard', source: 'NASA FIRMS', checkedAgo: 'just now' },
      { kind: 'closures', state: 'no-hazard', source: 'NPS', checkedAgo: 'just now' },
    ],
  }
}

function feedWith(cards: CardVM[]): FeedVM {
  return {
    query: '',
    cards,
    notices: [],
    setAside: [],
    heldBack: [],
    readiness: { on: false, state: 'off' },
    dataSource: 'live',
  }
}

describe('Home feed — repetition snapshot over the assembled surface (Epic 046 S6 AC-6.1)', () => {
  it('never lets the freshness stamp (or any other token) repeat more than 3× once a fully-fresh reading is shared feed-wide', async () => {
    const cards = [regionCard('a'), regionCard('b')]
    const { container } = await renderHomeSurface(feedWith(cards))
    assertNoOverRepetition(container, 'Home feed')
  })
})
