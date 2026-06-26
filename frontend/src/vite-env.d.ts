/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** When 'false', the app talks to a live backend; otherwise the mock runs. */
  readonly VITE_USE_MOCK?: string
  /** Base URL for the FastAPI backend when not mocking. */
  readonly VITE_API_BASE_URL?: string
  /** Dev-viewer secret the backend's fail-closed auth requires for a non-anonymous viewer. Set in `.env` only. */
  readonly VITE_DEV_VIEWER_SECRET?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
