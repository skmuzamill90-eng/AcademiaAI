# Incremental SaaS implementation plan

Inspection: React 19, TypeScript, React Router, Vite, shared CSS/components; FastAPI
`app/main.py`, shared `get_service`, pandas analytics, nine CSV datasets plus detailed
skills; JSON users, PBKDF2 and bearer JWT. No MySQL, ORM, SQL migrations, or git metadata
exist in this checkout. Existing student operations are create/read/update (no delete).
Imports have validation and background jobs bound to the uploading username.

1. Extend the existing JSON auth store with a versioned envelope for institutions,
   users, setup-token hashes and audits. Atomic replacement provides control-plane
   transactions. Preserve legacy users, but deny them access until explicitly mapped.
2. Select a separate CSV DataService by trusted identity institution UUID. No shared
   legacy fallback. Keep scoring, imports and response envelopes. Student routes use
   server-side account mapping and an allowlisted personal response.
3. Add platform lifecycle/account provisioning APIs, single-use password setup, live
   institution checks, token-version revocation, login throttling and bootstrap CLI.
4. Reuse existing layouts/API clients for platform, college and student pages.
5. Add explicit negative security tests and run backend/frontend regressions/build.

Storage constraint: retain the actual stores; do not invent an existing MySQL backend.
Support one API process on local durable storage, enforced by an exclusive process lock.
No automatic legacy ownership assignment. Offline manifest migration is explicit and
non-destructive. A transactional SQL conversion remains a separate deployment project.
