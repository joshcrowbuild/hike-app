/**
 * WebGL capability probe. MapLibre needs a GL context; when one can't be made —
 * jsdom under test, or a rare GL-less browser — the Detail map degrades to the
 * static route fallback (S3 AC-3.3) instead of throwing. Keeping this gate also
 * means the heavy `MapPanel` chunk is never imported in tests, so the code-split
 * boundary is honoured without mocking the map library.
 */
export function supportsWebGL(): boolean {
  if (typeof document === 'undefined' || typeof window === 'undefined') return false
  try {
    const canvas = document.createElement('canvas')
    const gl = canvas.getContext('webgl') ?? canvas.getContext('experimental-webgl')
    return Boolean(window.WebGLRenderingContext && gl)
  } catch {
    return false
  }
}
