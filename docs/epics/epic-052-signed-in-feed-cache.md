# Epic 052 — Signed-in feed cache + HTTP caching (WP-5: the reload perf fix)

**Status:** DONE ✅
**Phase:** 1 (look-and-feel layer's perf lane; independent of WP-0's token work)
**Spec refs:** `docs/design-system/spec-v0.2.md` Part III (the performance
layer — the corrected root cause), Part IV.3 (WP-5 scope + sequencing)

---

## Capability statement

A signed-in viewer's reload now paints the last feed from a namespaced local
cache in well under the 300ms budget — no skeleton — where before `useFeed`'s
`hydrateStale` returned `null` for anyone but `viewerId === 'anonymous'`, so
every signed-in reload refetched cold. `GET /regions` and the `/plan`
graph-only shell phase now carry `ETag` + `Cache-Control`, so a background
revalidate within a session (or a warm browser disk cache across reloads for
`/regions`) is a cheap `304` instead of a full recompute-and-reparse. The
loading-copy ladder (`loadingStages.ts`) is re-tuned for a paid Render Starter
that no longer spins down, replacing the earlier free-tier-cold-start
assumption baked into its thresholds and several nearby comments.

## Architectural context

**Corrected root cause (D4):** the reload skeleton felt like a Render
cold-start, but Render is a paid Starter (no idle spin-down). The actual
cause was `frontend/src/data/feedCache.ts`'s `hydrateStale()` gating on
`scope.viewerId === 'anonymous'` — a signed-in viewer's feed never entered
`localStorage`, so every signed-in reload was a genuine cold fetch.

**Builds on:** Epic 039 S3 (the anonymous SWR cache + `toStalePaint` honesty
transform) and Epic 040 (two-phase render, `conditions_complete` /
`phase:"cards"`). Neither is replaced — `toStalePaint` is reused verbatim
(Rule #1: honest stale-paint), and the two-phase wire contract is unchanged;
this epic only widens WHO gets cached and adds a validator to the existing
shell response.

**Touches:**
- `frontend/src/data/feedCache.ts` — namespaced-by-viewer `localStorage` slots
  (`adventure-planner:feed-cache:<viewerId>`), any-viewer read/write, new
  `evictFeedCache(viewerId)`.
- `frontend/src/data/PlannerProvider.tsx` — `hydrateStale`/`useFeed`'s two
  write-through sites lift the anonymous-only gate.
- `frontend/src/data/auth/AuthProvider.tsx` — `signOut` evicts the
  signed-out viewer's slot (local guarantee, independent of whether the
  remote Supabase sign-out call succeeds).
- `api/app.py` — `GET /regions` and the `/plan` `phase:"cards"` shell response
  gain `ETag` + `Cache-Control`; the classic complete `/plan` response and
  `POST /plan/conditions` deliberately do not (Rule #3 — ephemeral/live).
- `frontend/src/data/http/httpPlanner.ts` — a small in-memory ETag cache for
  the shell POST (browsers never HTTP-cache POST, so the server's ETag is
  otherwise inert here) plus a corrected free-tier comment.
- `frontend/src/data/loadingStages.ts` — `REASSURE_MS`/`COLDSTART_MS`
  re-tuned down.

**Does NOT include:**
- No token/component work (WP-0/1/2/3/4/6/7's scope) — no file under
  `frontend/tokens/`, `theme.css.ts`, `contracts.ts`, or
  `frontend/src/components|screens` changed.
- No change to the two-phase wire contract itself, `toStalePaint`'s
  transform, or `/plan/conditions` (kept uncached by design).
- No persisted (`localStorage`) transport-level cache for the `/plan` shell —
  the client-side ETag cache is deliberately in-memory only (see Deviations).

---

## Stories

### S1 — Namespace the feed cache by viewer; hydrate + write for any viewer

**Given** `feedCache.ts`'s single anonymous-only `localStorage` slot
**When** the slot becomes namespaced per `viewerId` and the anonymous-only
gate is removed from the caller
**Then** a signed-in viewer's reload paints instantly from its own cached
feed, and two viewers on the same device can never read or evict each
other's cache.

**AC-1.1:** `storageKeyFor(viewerId)` → `adventure-planner:feed-cache:<viewerId>`;
`readFeedCache`/`writeFeedCache` take a `viewerId` (defaulted to `'anonymous'`
for source compatibility with any caller that doesn't pass one yet) and
read/write ONLY that viewer's slot.
**AC-1.2:** `PlannerProvider.tsx`'s `hydrateStale` and both `useFeed`
write-through sites drop the `scope.viewerId === 'anonymous'` gate — any
viewer with a matching, non-empty, non-stale cache entry paints on the first
committed render (mirrors the existing AC-3.1 guarantee, now for every
viewer).
**AC-1.3:** `resetFeedCacheForTests()` sweeps every namespaced slot (there is
no registry of which viewers a test touched).
**AC-1.4:** A new `evictFeedCache(viewerId)` clears exactly one viewer's slot,
never throws, and is a no-op on a slot that was never written.

### S2 — Evict on sign-out (Rule #5)

**Given** a signed-in viewer's cached feed is personal
**When** that viewer signs out
**Then** their slot is gone before the sign-out call resolves (or rejects) —
the device never keeps a readable feed for whoever uses it next.

**AC-2.1:** `AuthProvider.tsx`'s `signOut` captures the current session's
`sub` before calling Supabase, then evicts that viewer's slot in a `finally`
— eviction happens even if the remote sign-out call rejects (the local
privacy guarantee never depends on network success).
**AC-2.2:** Nothing here ever persists a GRANTED party's raw substrate —
only the resolving caller's own derived `FeedVM` ever reaches
`writeFeedCache`, into that caller's own slot alone.

### S3 — HTTP caching: ETag + Cache-Control on `/regions` and the `/plan` shell

**Given** the `/plan` `phase:"cards"` shell response and `GET /regions` are
the two surfaces a background revalidate re-fetches
**When** both carry a strong `ETag` + an appropriate `Cache-Control`
**Then** a matching `If-None-Match` gets a cheap, bodyless `304` instead of a
full JSON payload — and the ephemeral, live-conditions-bearing responses
(`/plan/conditions`, the classic complete `/plan`) carry neither header, so a
stale hazard can never read back as fresh off a validator.

**AC-3.1:** `_etag_for`/`_conditional_json` (api/app.py) compute a strong
SHA-256 validator over the sorted-key JSON payload and honor `If-None-Match`
with a `304` + repeated headers on a match, else the full `200`.
**AC-3.2:** `GET /regions` → `Cache-Control: public, max-age=60,
must-revalidate` (public/non-viewer-specific config, changes only on
deploy) — `regionsCatalog.ts`'s plain `fetch()` gets this for free via the
browser's own HTTP cache; no client code change needed for this surface.
**AC-3.3:** `POST /plan` with `phase:"cards"` AND the two-phase server switch
on → `Cache-Control: private, no-cache` (viewer-scoped, always revalidates).
The classic complete response, the D6 kill-switch fallback, and `POST
/plan/conditions` carry neither header.
**AC-3.4:** `httpPlanner.ts`'s `planWith` adds a small in-memory
`planShellCache` (keyed by the exact stringified request body) that sends
`If-None-Match` on a repeat shell request and reuses the cached body on a
`304` — real POST responses never enter the browser's own HTTP cache, so
without this the server's validator would be inert for `/plan`.

### S4 — Re-tune the loading-copy ladder for a paid, non-spinning-down Starter

**Given** `loadingStages.ts`'s `REASSURE_MS`/`COLDSTART_MS` were tuned around
a 30–60s Render free-tier wake
**When** the thresholds come down and nearby comments stop asserting a
spin-down free tier
**Then** the ladder still degrades honestly on a genuinely slow request, but
no longer waits out a wake that no longer happens.

**AC-4.1:** `REASSURE_MS: 10_000 → 5_000`; `COLDSTART_MS: 25_000 → 15_000`;
both stay comfortably inside the unchanged 60s `/plan` abort budget
(`PLAN_TIMEOUT_MS`, kept as a safety net for a genuine post-deploy restart or
outage, not a routine wake).
**AC-4.2:** Every comment in `PlannerProvider.tsx`, `loadingStages.ts`, and
`httpPlanner.ts` that asserted a free-tier idle spin-down is corrected to
describe the paid-Starter reality (the `LOADING_COPY` user-facing strings
themselves are untouched — copy is WP-6's scope, and the existing hedged
wording ("this can take up to a minute") never literally claimed "free
tier").

---

## Definition of Done
- [x] All ACs covered by at least one passing test.
- [x] Backend `make check` green (`ruff format --check` + ruff + mypy +
      pytest, 1807 passed / 2 skipped).
- [x] Frontend `npm run build` (tsc --noEmit + vite build) and `npm test`
      green (587 passed).
- [x] Targeted self-review; no CRITICALs found (see commit message for
      summary; documented deviations below).
- [ ] Epic row added to `docs/epics/README.md` — intentionally deferred:
      this WP's brief excludes that file (merge-risk discipline while other
      v0.2 lanes are in flight); the merge desk (WP-7) adds it.
- [x] Committed on this worktree's branch — not pushed, per kickoff
      instructions (the PO/merge-desk handles integration).

## Deviations from spec (documented, not blocking)

- **The client-side `/plan` shell ETag cache is in-memory, not persisted.**
  Part III.3 doesn't specify storage; a `localStorage`-backed version would
  survive reloads (helping the very first post-reload revalidate hit a
  304), but that duplicates Fix 1's job at the wire level — a second
  persisted copy of a viewer's shell response that `AuthProvider`'s sign-out
  eviction would also need to cover (Rule #5's blast radius). Since Fix 1
  already owns the reload-to-first-paint budget via the localStorage VM
  cache, the transport-level ETag cache only needs to help WITHIN a session
  (a retune, a periodic revalidate) — an in-memory `Map` does that and
  vanishes with the tab, so there's nothing extra to evict on sign-out.
- **`readFeedCache`/`writeFeedCache`'s `viewerId` parameter defaults to
  `'anonymous'`** rather than being strictly required. One screens-layer
  test (`frontend/src/screens/Home.test.tsx`, out of scope for this
  data/perf WP per the kickoff brief) calls `writeFeedCache` with the
  pre-WP-5 two-argument signature; defaulting preserves that call's meaning
  (the anonymous slot) with zero screens-layer edits, while every WP-5-aware
  call site (`PlannerProvider.tsx`, the new tests) passes `viewerId`
  explicitly.
- **`PLAN_TIMEOUT_MS` (the 60s `/plan` fetch-abort budget) is unchanged.**
  The brief's "re-tune `loadingStages.ts` thresholds down" names that one
  module; the 60s hard abort in `httpPlanner.ts` is a different kind of
  value (a safety net against a genuinely hung request, not a UX copy
  threshold) and reducing it risks aborting a legitimate slow multi-provider
  fan-out. Its stale comment is corrected; the value itself is not lowered.
- **Loading-copy strings (`LOADING_COPY` in `loadingStages.ts`) are
  unchanged.** Microcopy is WP-6's scope (spec IV.3's work-package table);
  this WP only re-tunes the numeric thresholds and fixes comments that
  asserted an inaccurate cause.
