import { cleanup } from '@testing-library/react'
import { afterEach } from 'vitest'

// jest-dom matchers (.toBeInTheDocument, etc.) + their vitest type augmentation.
import '@testing-library/jest-dom/vitest'

// jsdom implements no canvas/WebGL context. Stub it to a quiet `null` so the
// map's `supportsWebGL()` probe resolves to the static fallback without jsdom's
// noisy "Not implemented: getContext" warnings (the GL path runs in a browser).
if (typeof HTMLCanvasElement !== 'undefined') {
  HTMLCanvasElement.prototype.getContext = (() => null) as typeof HTMLCanvasElement.prototype.getContext
}

// Unmount between tests without relying on Vitest globals being enabled.
afterEach(() => {
  cleanup()
})
