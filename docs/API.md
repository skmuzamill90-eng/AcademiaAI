# API Reference

Local base URL: `http://127.0.0.1:8000`. Swagger UI: `/docs`.

Success responses use `{ "status": "success", "data": ..., "meta": {...} }`. Errors use `{ "status": "error", "error": { "code", "type", "message", "details" } }`.

## Roles

| Role | Scope |
|---|---|
| `super_admin` | Platform institutions, lifecycle, College Admin provisioning, usage and audit logs |
| `college_admin` | One institution's students, imports, analytics, interventions and student accounts |
| `student` | Own linked student record and permitted personal analytics |

## Main Endpoints

| Endpoint | Access | Description |
|---|---|---|
| `GET /api/health` | Public | API liveness only |
| `POST /api/auth/login` | Public | Username/password login; returns a bearer token |
| `GET /api/auth/me` | Signed in | Current account, role, institution and password-change status |
| `POST /api/auth/setup` | Setup token | One-time password setup for provisioned accounts |
| `POST /api/auth/password` | Signed in | Change current password and revoke older tokens |
| `POST /api/auth/logout` | Signed in | Revoke existing account tokens |
| `GET /api/platform/summary` | Super Admin | Platform institution and account totals |
| `GET /api/platform/institutions` | Super Admin | Search, filter, sort and paginate institutions |
| `POST /api/platform/institutions` | Super Admin | Create institution and initial College Admin account |
| `PATCH /api/platform/institutions/{id}` | Super Admin | Edit profile/status/limits |
| `POST /api/platform/institutions/{id}/administrator/setup` | Super Admin | Issue one-time College Admin setup token |
| `GET /api/dashboard/summary` | College Admin | Institution-scoped dashboard KPIs |
| `GET /api/students` | College Admin | Institution-scoped student search |
| `GET /api/students/{id}` | College Admin | Student profile within the admin's institution |
| `POST /api/students` | College Admin | Add a student to the admin's institution CSVs |
| `PATCH /api/students/{id}` | College Admin | Update a student within the admin's institution |
| `GET /api/analytics/*`, `/api/risks`, `/api/segments` | College Admin | Institution-scoped analytics |
| `GET/POST/PATCH /api/interventions...` | College Admin | Institution-scoped intervention history and writes |
| `GET/POST /api/imports/*` | College Admin | Institution-scoped bulk CSV/XLS/XLSX imports |
| `GET /api/institution/accounts` | College Admin | Institution student account list |
| `POST /api/institution/accounts` | College Admin | Provision a student account mapped to an existing student ID |
| `POST /api/institution/accounts/{username}/setup` | College Admin | Issue one-time student setup token |
| `GET /api/student/me` | Student | Own student profile only |

College Admin endpoints never accept a client-supplied institution as authorization. The backend selects the tenant CSV service from the authenticated user's stored `institution_id`.

## Storage

No SQL database is used. Account hashes, role assignments, institutions, setup tokens and audit events are stored in `data/users.json`. Tenant student data is stored in `data/tenants/<institution_uuid>/*.csv`. Legacy top-level CSVs must be explicitly migrated with `scripts/saas_admin.py migrate-legacy-data`; the application will not guess ownership.

Bulk import details remain in [STUDENT_IMPORT.md](STUDENT_IMPORT.md).
