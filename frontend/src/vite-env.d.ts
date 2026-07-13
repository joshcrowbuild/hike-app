/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** When 'false', the app talks to a live backend; otherwise the mock runs. */
  readonly VITE_USE_MOCK?: string
  /** Base URL for the FastAPI backend when not mocking. */
  readonly VITE_API_BASE_URL?: string
  /** Dev-viewer secret the backend's fail-closed auth requires for a non-anonymous viewer. Set in `.env` only. */
  readonly VITE_DEV_VIEWER_SECRET?: string
  /** Age cap (ms) for the anonymous stale-while-revalidate Home feed cache (feedCache.ts). `0` disables read
   *  AND write. Unset defaults to 6h. Build-time baked (Vite) — changing it needs a rebuild. */
  readonly VITE_ANON_FEED_STALE_MAX_MS?: string
  /** Two-phase render client kill switch (Epic 040 D6): `0` restores the single-call flow
   *  byte-identically. Unset/blank = enabled. Build-time baked (Vite). */
  readonly VITE_TWO_PHASE?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
