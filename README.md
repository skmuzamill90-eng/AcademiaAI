# AcademiaAI

**AI-Powered Student Analytics and Success Platform**

AcademiaAI helps educational institutions monitor student performance, identify students who may need support, analyze engagement and placement readiness, and coordinate interventions.

## Features

- Student academic and attendance analytics
- Student success scores and risk indicators
- Placement readiness and skills insights
- Student data import and validation
- Student interventions and recommendations
- Role-based access for Super Admins, College Admins, and Students
- Institution-specific data isolation
- AI assistant for supported student-data questions

## Prerequisites

Install the following before starting:

- Python 3.10 or a compatible version supported by the project dependencies
- Node.js and npm
- Git

## Backend Setup

Run these commands from the project root in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
notepad .env
```

Generate a secure authentication secret:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Copy the generated value into `AUTH_SECRET_KEY` in your `.env` file. Keep this secret private.

Create the first Super Admin while the API is stopped:

```powershell
python scripts/saas_admin.py bootstrap-super-admin --username skmuzamill
```

Follow the script's prompts to complete setup.

Start the API:

```powershell
uvicorn app.main:app --reload --env-file .env
```

## Frontend Setup

Open a second terminal in the project root:

```powershell
cd frontend
npm install
npm run dev
```

Open the Vite URL shown in your terminal, usually:

http://localhost:5173

The development server is configured to proxy `/api` requests to FastAPI.

## SaaS Workflow

1. Sign in as the Super Admin and open the Platform dashboard.
2. Create an institution and its initial College Admin username.
3. Activate the institution and issue a one-time administrator setup link.
4. The College Admin sets a password and manages that institution's students, imports, analytics, interventions, and student accounts.
5. College Admins provision student accounts from existing student records. Students use their own accounts to access their permitted student information.

Existing top-level `data/*.csv` records are not automatically assigned to an institution. Use the migration script's help and an explicit manifest when ownership of legacy records is known.

## AI Assistant

The AI assistant can answer supported factual questions using the signed-in institution's loaded student records.

Example questions:

- What is the average attendance?
- Show the top five students by coding score.
- How many students have a CGPA above 8?
- Show the placement status distribution.
- Which fields are available?

Missing numeric values are not treated as zero. Verify important results against the source data. AI-generated recommendations are guidance, not official decisions.

## Storage and Security

- Authentication data is stored in `data/users.json` unless `AUTH_USERS_FILE` is configured.
- Tenant data is stored under `data/tenants/<institution_uuid>/`.
- Passwords are stored as salted PBKDF2 hashes.
- Setup and reset tokens are stored hashed and shown only once.
- Protected routes derive the user's role and institution from authenticated server-side state.
- Keep `.env` files, credentials, user stores, and private student records out of Git.
- Use HTTPS and a unique, strong `AUTH_SECRET_KEY` in production.
- Use durable private storage and follow the project's deployment guidance for file writes and worker configuration.

## Deployment

See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for deployment guidance for the Vercel frontend and Render backend.

Before deploying:

- Set `ENVIRONMENT=production`.
- Configure a unique production `AUTH_SECRET_KEY`.
- Set `CORS_ORIGINS` to the exact frontend HTTPS origin.
- Keep `GROQ_API_KEY` on the backend only, if the AI assistant is enabled.
- Configure persistent private storage for application data.
- Set `VITE_API_BASE_URL` if the frontend and backend are hosted separately.
- Never commit real `.env` files, API keys, passwords, or private student data.

## Verification

Run the backend tests from the project root:

```powershell
python -m pytest
```

Run frontend tests and build:

```powershell
npm.cmd test --prefix frontend
npm.cmd run build --prefix frontend
```

Student scores and risk indicators are decision-support guidance, not official academic decisions. Review data quality and model limitations before institutional use.
