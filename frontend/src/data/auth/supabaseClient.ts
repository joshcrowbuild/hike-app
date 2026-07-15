/**
 * Supabase auth client (Epic 043 S4) — the single place supabase-js is
 * constructed. Built lazily from `VITE_SUPABASE_URL` + `VITE_SUPABASE_ANON_KEY`;
 * when either is absent, `getSupabase()` returns null and the app stays
 * anonymous-only — sign-in is simply unavailable, and anonymous browsing never
 * needs these values (the fail-closed default the backend also holds).
 *
 * The publishable/anon key is frontend-safe by design (it is the `sb_publishable_…`
 * key, NOT a service-role key). Session persistence + refresh are supabase-js's
 * defaults (localStorage), so a signed-in session survives a reload (AC-4.1).
 */
import { createClient, type SupabaseClient } from '@supabase/supabase-js'

let cached: SupabaseClient | null | undefined

/** The configured Supabase client, or null when sign-in isn't configured. Cached
 *  so only one client (and one auth listener) exists for the app's lifetime. */
export function getSupabase(): SupabaseClient | null {
  if (cached !== undefined) return cached
  const url = import.meta.env.VITE_SUPABASE_URL
  const anonKey = import.meta.env.VITE_SUPABASE_ANON_KEY
  cached = url && anonKey ? createClient(url, anonKey) : null
  return cached
}

/** True when sign-in is configured — the UI offers a sign-in affordance only then,
 *  never a dead button that can't work (calm: no affordance you can't fulfil). */
export function authConfigured(): boolean {
  return getSupabase() !== null
}
