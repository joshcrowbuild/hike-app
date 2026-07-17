# Epic 057 — Feed chrome & polish (SAVED pill · header avatar · metric density · case holdouts)

**Status:** DONE ✅
**Phase:** 1 (frame-conditions wave, polish lane — launches after Epic 055 merges)
**Spec refs:** `docs/design-system/frame-conditions-wave.md` §7; `docs/design-system/mocks/states-gallery.html`, `happy-path-before-after.html`

---

## Capability statement

The feed chrome matches the mocks: the Saved pill and trail count sit quietly
in the stack-controls row, the anonymous "Browsing" chip recedes, a signed-in
viewer gets an initial-circle avatar opening the account/sign-out sheet, the
mono metric line has its final density pass, and the last uppercase holdouts
outside Epic-055 files are migrated to sentence case.

## Architectural context

Builds on: Epic 055's settled Home layout (hard dependency — this lane edits
`Home.tsx`'s chrome regions and MUST branch after 055 merges).
Does NOT include: the This-feed card internals (055), data layer (056).

---

## Stories

### S1 — Stack controls
**AC-1.1:** Saved pill placement/styling per mocks ("Saved"/"Saved (N)"/"Show
all" logic unchanged); trail count in quiet mono.

### S2 — Top bar
**AC-2.1:** Anonymous: quiet "Browsing" chip + "Sign in" text button.
**AC-2.2:** Signed-in: initial-circle avatar (slate-fill, ≥30px target)
opening the existing account/sign-out surface; no new auth logic.

### S3 — Metric line + case
**AC-3.1:** Metric-line density per mock (mono, middot separators, weight/
spacing tokens — no raw values).
**AC-3.2:** Remaining `text-transform: uppercase`/case holdouts outside
Epic-055 files migrated (overline role stays the one exception).

### S4 — Tests
**AC-4.1:** Component tests for avatar states + Saved pill; visual/case
assertions updated, none deleted.

---

## Definition of Done
- [x] All ACs covered by at least one passing test
- [x] `npm run build` + `npm test` green (710 tests)
- [x] Targeted review agent run; CRITICALs fixed (desk diff review — clean)
- [x] Committed and pushed
