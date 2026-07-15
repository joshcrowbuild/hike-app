/**
 * Whether the OS-level reduced-motion preference is on. Checked via `matchMedia`
 * (not a CSS-only `prefers-reduced-motion` query) so callers can gate JS-driven
 * animation decisions — and so the behaviour is a unit-testable fact rather than
 * a stylesheet assertion jsdom can't evaluate.
 */
export function prefersReducedMotion(): boolean {
  try {
    return typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches
  } catch {
    return false
  }
}

/**
 * Whether the primary pointer is coarse (touch) rather than fine (mouse/trackpad).
 * Checked via `matchMedia` so callers can gate UI elements that assume fine pointer
 * affordances. On SSR or when matchMedia is unavailable, defaults to false (assumes fine pointer).
 */
export function isCoarsePointer(): boolean {
  try {
    return typeof window !== 'undefined' && window.matchMedia('(pointer: coarse)').matches
  } catch {
    return false
  }
}
