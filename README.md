# AcademiaAI

AcademiaAI is a CSV-backed student analytics platform with FastAPI, React/Vite, role-based access control, institution isolation, student imports, dashboards, interventions, placement readiness insights and an AI data assistant.

The current SaaS version uses the existing storage model: student data stays in CSV files and accounts stay in a local JSON auth store. There is no MySQL migration in this checkout.

## Backend Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
notepad .env
```

Set `AUTH_SECRET_KEY` in `.env` to a generated secret:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Create the first Super Admin offline while the API is stopped:

```powershell
python scripts/saas_admin.py bootstrap-super-admin --username skmuzamill
```

Start the API:

```powershell
uvicorn app.main:app --reload --env-file .env
```

## Frontend Setup

```powershell
cd frontend
npm install
npm run dev
```

Open the Vite URL, usually `http://localhost:5173`. The dev server proxies `/api` to FastAPI.

## SaaS Workflow

1. Sign in as the Super Admin and open the Platform dashboard.
2. Create an institution and its initial College Admin username.
3. Activate the institution, then issue a one-time administrator setup link from the institution detail panel.
4. The College Admin sets a password, signs in, and manages only that institution's students, imports, analytics, interventions and student accounts.
5. College Admins provision student accounts from existing student records. Each student gets a one-time setup link and can view only `/api/student/me`.

Existing top-level `data/*.csv` records are not silently assigned to a college. Use `python scripts/saas_admin.py migrate-legacy-data --help` with an explicit manifest to move records into institution folders when ownership is known.

## Asking Questions About Student Data

The AI assistant calculates supported factual questions directly from the signed-in institution's currently loaded CSV records. Ask for a field by its name or a familiar alias, such as “average attendance,” “top 5 students by coding score,” “how many students have CGPA above 8,” or “placement status distribution.” It supports the student fields loaded from the CSV schemas, including academic, attendance, LMS, engagement, placement, skills, and feedback data. Ask “Which fields are available?” to see the fields loaded for your institution.

Numeric averages and rankings use recorded numeric values; missing values are not treated as zero. Lists, counts, comparisons, and distributions are computed locally when the question matches a supported query. Questions seeking advice or interpretation may use the configured Groq model and its dataset summaries; AI-generated recommendations are not official decisions. Verify important results against the source data.

## Storage And Security Notes

- Auth state lives in `data/users.json` unless `AUTH_USERS_FILE` is set.
- Tenant CSVs live under `data/tenants/<institution_uuid>/`.
- Passwords use salted PBKDF2 hashes; setup/reset tokens are stored hashed and shown only once.
- Protected routes resolve role and institution from the signed token and JSON store; clients cannot choose `institution_id`.
- Run one API worker with durable local storage for CSV/JSON writes. The app takes process locks for the auth store and tenant data root.
- Use HTTPS and a strong `AUTH_SECRET_KEY` outside local development.

## Deployment Checklist

- See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for the Vercel frontend and Render backend setup, environment variables and launch checks.
- Configure `ENVIRONMENT=production` and a unique `AUTH_SECRET_KEY` generated with `python -c "import secrets; print(secrets.token_urlsafe(48))"`. Production startup rejects the development default, example placeholders, and secrets shorter than 32 characters.
- Set `CORS_ORIGINS` to the exact HTTPS origin(s) serving the frontend; do not leave the local development origins in a public deployment.
- Keep `GROQ_API_KEY` only in the backend environment if the AI assistant is enabled. It is optional and must never be set as a `VITE_*` variable.
- Mount durable private storage for `SMART_CAMPUS_DATA_DIR` and `AUTH_USERS_FILE`; back up this storage securely. Keep one API worker because writes use local files and process locks.
- The frontend uses a relative `/api` path by default. If frontend and API are hosted separately, set `VITE_API_BASE_URL` at frontend build time and allow the frontend origin in backend `CORS_ORIGINS`.
- Keep real `.env` files, credentials, user stores, and student CSVs out of Git. Commit only the `.env.example` templates.

## Verification

```powershell
python -m pytest
npm.cmd test --prefix frontend
npm.cmd run build --prefix frontend
```

Scores and risk indicators are transparent rule-based guidance, not official decisions. Review data quality and thresholds before institutional use.
