# Privacy Policy — Adventure Planner

**Draft — for owner review; take to counsel. This is not legal advice.**

**Effective date:** [VERIFY — set before publication]
**Last updated:** 2026-07-14

---

Adventure Planner is a calm, private hiking trip planner. This policy tells you plainly what data we collect, why, where it goes, and what rights you have over it. Where a right has a limit, we state the limit.

We are not an advertising company. We are not a social network. We do not sell data. We do not train models on your data. We exist to give you a better answer about your next hike, and nothing else.

---

## 1. What we collect

### Data you provide directly

| Data | Why we collect it |
|---|---|
| **Email address** | To create and secure your account (via Supabase Auth). |
| **Trip logs** (date, trail, distance, duration, ascent, pace, party composition) | To learn your hiking patterns so your future answers improve. |
| **Post-hike ratings and reflections** | To understand what you enjoyed and sharpen recommendations. |
| **Settings and preferences** (e.g., privacy toggles, export requests) | To honor your choices about how the app behaves. |

### Data we derive

| Data | Why we derive it |
|---|---|
| **Capability beliefs** (e.g., "comfortable with moderate climbs") | Derived from your logged trips to set an honest physical floor — never to rank you. |
| **Preference beliefs** (e.g., "prefers waterfall hikes") | Derived from your logged outcomes to improve recommendations. Capability and preference are always kept separate — a long hike does not mean you prefer long hikes. |

### Data from a connected watch (if you link one)

| Data | Why we collect it |
|---|---|
| **GPS track** | To record where you hiked. |
| **Pace and duration** | To calibrate your capability floor. |

### What we explicitly do NOT collect

- **No heart-rate, HRV, SpO2, or other biometric streams.** Watch data like Body Battery or readiness may be read in real time to inform a capability hedge, but it is **never stored** in the database or any log.
- **No client analytics or tracking SDK.** We do not run Google Analytics, Mixpanel, Amplitude, or any equivalent.
- **No ad identifiers or fingerprinting.** None.
- **No location tracking.** We do not track your location in the background. GPS data exists only in trip logs you explicitly create.

---

## 2. Where your data lives — our service providers

We use five service providers. Each is named here with exactly what it does and does not touch.

| Provider | Role | What it accesses |
|---|---|---|
| **Supabase** | Authentication only | Your email, hashed password, session tokens. Supabase holds **no** app data — no trips, no beliefs, no GPS tracks. Its database is not used for application data. |
| **Neo4j Aura** | Graph database | All application data: your trips, beliefs, preferences, and the trail corpus. This is the single source of truth for the app. |
| **Render** | API server | Processes your requests. Sees the data needed to compose your answer, subject to the privacy rules below. |
| **Vercel** | Frontend hosting | Serves the web application. Has no access to your personal data. |
| **Anthropic** (Claude) | Language model | Composes natural-language plan answers from the trail corpus and live weather/conditions overlays. **Anthropic never receives your personal overlay** — see Section 3. |

---

## 3. The private overlay never reaches a cloud model

This is a core promise. Your personal data — your beliefs, preferences, capability profile, trip history, and outcomes — **never leaves your logical boundary to reach a cloud language model.**

The cloud model (Anthropic Claude) receives only:

- The un-personalized trail corpus (public trail data from government sources and OpenStreetMap)
- Live condition overlays (weather, air quality, stream flow, fire, permits — all public data)

Your personal context is processed locally [VERIFY — confirm "locally" vs. "server-side in the API without forwarding to Anthropic"]. This is enforced by a code-level egress guard (the C4 guard) and verified by automated tests on every code change.

---

## 4. No model training — ever

Your data is used exclusively to serve your own answers. It is never used to:

- Train or fine-tune any language model
- Power recommendations for other users
- Build aggregate profiles for advertising
- Sell or share with data brokers

This is not a setting you can change. It is a structural invariant enforced in the architecture.

---

## 5. Commons contributions — opt-in, off by default

You may choose to contribute de-identified observations to the Adventure Planner commons — an aggregate dataset that helps improve trail information for everyone. **This is off by default.** You must explicitly turn it on in Settings → Privacy, and you can turn it off at any time.

### What is contributed (if you opt in)

Only de-identified observations:

- **Trail observations** (e.g., trail condition, approximate effort) — never your raw GPS track
- **Coarse capability band** (e.g., "moderate") — never your actual pace
- **Month of visit** — never the exact date

### How we de-identify your contribution

Every commons observation goes through four transformations before it enters the commons:

1. **Endpoint trimming.** The first and last 250 meters of any GPS data are stripped, removing locations that could reveal your home, workplace, or parking spot.
2. **Capability banding.** Your raw pace is replaced with one of four coarse bands (easy, easy-moderate, moderate, strenuous). The raw value is never stored on the commons observation.
3. **Writer-hash.** Your identity is replaced with an irreversible, salted hash. There is no relationship in the database from a commons observation back to your account. Even a full database export cannot trace a commons observation to you.
4. **Month bucketing.** The exact date is replaced with a year-month bucket.

### What is never contributed to the commons

- Your GPS tracks
- Your personal overlay (beliefs, preferences, taste model)
- Your trip details (when you hiked, with whom)
- Any biometric data
- Any data about dependents (e.g., a pet who hikes with you)

### Irreversibility — stated plainly

Once enough hikers have contributed for a statistic to appear (we require a minimum number of contributors — the k-anonymity threshold — before any statistic is published), your individual contribution is blended into the anonymous aggregate and **cannot be pulled back out.** We can stop your future contributions and remove contributions that have not yet been blended, but blended ones are part of the anonymous aggregate permanently.

### Revoking your commons contribution

- **Toggle off** in Settings → Privacy at any time.
- Toggling off immediately stops future contributions.
- Contributions that have not yet reached the anonymity threshold are removed.
- Contributions already blended into the aggregate cannot be individually removed (see above).
- On account deletion, the salt used to generate your writer-hash is destroyed, making it impossible for anyone — including us — to link your past contributions to your identity.

### Licensing

Commons data carries an Open Database License (ODbL), consistent with the OpenStreetMap data in the corpus [VERIFY — pending counsel confirmation at Stage 9 gate G-6].

---

## 6. Operational logs

We retain scrubbed operational logs (API response times, error rates, cost metrics) to keep the service running. These logs:

- Contain **no** user IDs, IP addresses, or GPS coordinates
- Are rotated within 90 days
- Exist solely for debugging and cost management

---

## 7. Your data rights

### Access

You can view all your data within the app at any time.

### Export

You can export your data in machine-readable formats from Settings → Data → Export:

- **JSON** for your beliefs and episodes
- **GPX** for your GPS tracks

[VERIFY — the export endpoint is being built as part of the ToS/deletion scaffold; not yet shipped]

### Deletion

You can delete your account and all personal data at any time. Here is exactly what happens:

1. **Immediate hard delete.** All personal-overlay nodes (beliefs, context, persona, profile) and episode records are permanently deleted from the graph database in the same request. Once deleted, they are irrecoverable.
2. **Auth record.** Your Supabase authentication record is marked as deleted, retained for 30 days for abuse prevention, then permanently deleted.
3. **Backups.** Database backups (daily snapshots) cannot be selectively purged. They age out within 30 days.
4. **Commons contributions.** These are not deleted — they were born without any link to your identity. On deletion, the salt used for your writer-hash is destroyed, so even the operator can no longer associate them with you.

[VERIFY — the deletion endpoint is being built as part of the ToS/deletion scaffold; not yet shipped]

### Commons revocation

See Section 5 above. You can revoke future commons contributions at any time. Already-aggregated contributions cannot be individually removed.

---

## 8. Retention

| Data | Retention |
|---|---|
| Personal data (overlay, episodes, beliefs) | Kept until you delete your account. |
| Auth record after deletion | 30 days, then hard-deleted. |
| Database backups | Age out within 30 days. |
| Operational logs (scrubbed) | Rotated within 90 days. |
| Commons contributions (de-identified) | Permanent, but unlinkable to you. |

---

## 9. Children

Adventure Planner is available only to users 18 and older. We do not knowingly collect data from anyone under 18. If you believe a minor has created an account, contact us and we will delete it.

---

## 10. Data about dependents

If you log trips with a dependent (such as a pet), the app may derive capability beliefs about them (e.g., "Ruby can handle 6-mile hikes"). This data:

- Is stored under your account and subject to your privacy controls
- Is never shared with other users unless you explicitly grant access to your derived conclusions
- Is **never** contributed to the commons, even if you have commons contributions turned on
- Is deleted when you delete your account

---

## 11. Third-party data sources

The trail corpus includes data from:

- **OpenStreetMap contributors** — licensed under the Open Database License (ODbL). © OpenStreetMap contributors. [openstreetmap.org/copyright](https://www.openstreetmap.org/copyright)
- **U.S. government sources** (NPS, USFS, USGS) — public domain
- **Live condition feeds** (NWS weather, AirNow air quality, USGS stream gauges, FIRMS fire data) — public data, each displayed with its source and fetch timestamp

We never ingest data from Strava, AllTrails, Gaia, Komoot, or onX. These sources are permanently off-limits.

---

## 12. Security

- All data in transit is encrypted (HTTPS/TLS).
- Database access is restricted to the application server.
- Access control is enforced at the query layer — every database query is scoped to the authenticated user. This is verified by automated tests, including adversarial penetration tests, on every code change.
- Secrets (API keys, database credentials) are stored in environment variables, never in the code repository.
- [VERIFY — encryption at rest posture for Neo4j Aura / Supabase]

---

## 13. Changes to this policy

If we make material changes to this policy, we will notify you by [VERIFY — email? in-app notice? both?] before the changes take effect. Non-material clarifications (typo fixes, formatting) may be made without notice.

---

## 14. Contact

To exercise any of your data rights (access, export, deletion, commons revocation), or to ask a question about this policy:

**[VERIFY — contact email or method]**

---

## 15. Promise-to-mechanism map

Each material promise in this policy is traceable to a specific mechanism. See [promise-mechanism-map.md](promise-mechanism-map.md) for the full table, including which promises are already enforced in code and which are being built.

---

*This document is a draft prepared for owner review. It is not legal advice. The owner should review it with qualified legal counsel before publication.*
