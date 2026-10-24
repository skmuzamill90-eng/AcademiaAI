# Vercel frontend and Render backend deployment

This project deploys as two services. The React frontend is a static Vite app on Vercel; the FastAPI backend runs on Render and stores authentication and institution data on a persistent disk.

## 1. Prepare the Vercel project and frontend origin

1. Import the repository into Vercel and set **Root Directory** to `frontend`.
2. Choose the Vercel project name or assign its production custom domain, so you know the exact frontend origin (for example `https://your-project.vercel.app`). You can finish the Vercel environment variable and deployment after creating the backend.

The Blueprint uses the Starter plan and attaches a 1 GB persistent disk at `/var/data`. A persistent disk is required: without it, the JSON auth store and tenant CSV records would be lost when the service restarts or is replaced. The service intentionally starts one Uvicorn worker because this app uses file-backed writes and process locks.

## 2. Deploy the backend on Render

1. Create a new **Blueprint** in Render from the repository. Keep the repository root as the Blueprint root so it can read `render.yaml` and `requirements.txt`.
2. The Blueprint requests `CORS_ORIGINS`. Enter the Vercel production origin from step 1 exactly, with no trailing slash or path.
3. Review the `academia-ai-api` web service and create it. The Blueprint generates `AUTH_SECRET_KEY` on Render; do not replace it with the local `.env` key.
4. Wait for `/api/health` to report healthy, then copy the backend base URL, such as `https://academia-ai-api.onrender.com`. Do not include `/api` or a trailing slash.

## 3. Configure and deploy the frontend on Vercel

1. In the Vercel project settings, add the following variable for the **Production** environment:

   | Name | Value |
   | --- | --- |
   | `VITE_API_BASE_URL` | The Render backend base URL, e.g. `https://academia-ai-api.onrender.com` |

   This is a public API URL, not a secret. Do not put backend keys or passwords in any `VITE_*` variable.
2. Deploy the frontend. Confirm its production origin matches the value configured in Render `CORS_ORIGINS`. If Vercel assigned a different origin or a custom domain is used, update `CORS_ORIGINS` in Render and redeploy/restart the backend. Additional approved origins can be comma-separated; do not add trailing slashes.

The Vercel rewrite serves the SPA entry point for client-side routes. API calls use `VITE_API_BASE_URL` directly and are not rewritten through Vercel.

## Render environment variables

The checked-in `render.yaml` configures the following:

| Variable | Configuration |
| --- | --- |
| `PYTHON_VERSION` | `3.12.8` |
| `ENVIRONMENT` | `production` |
| `AUTH_SECRET_KEY` | Generated privately by Render; keep the generated value |
| `ACCESS_TOKEN_MINUTES` | `30` |
| `AUTH_USERS_FILE` | `/var/data/users.json` |
| `SMART_CAMPUS_DATA_DIR` | `/var/data` |
| `CORS_ORIGINS` | Required; exact frontend origin(s), comma-separated |
| `IMPORT_MAX_UPLOAD_MB` | `10` |
| `IMPORT_MAX_ROWS` | `20000` |

Optional AI assistant variables (only set these in Render if enabling Groq):

| Variable | Value |
| --- | --- |
| `GROQ_API_KEY` | Your private key from Groq; never commit it or expose it to Vercel |
| `GROQ_MODEL` | `openai/gpt-oss-120b` |
| `GROQ_TIMEOUT_SECONDS` | `45` |

Optional storage overrides should keep both `AUTH_USERS_FILE` and `SMART_CAMPUS_DATA_DIR` under the persistent disk mount. Do not use ephemeral paths for production records.

## Vercel environment variables

| Variable | Value |
| --- | --- |
| `VITE_API_BASE_URL` | Render backend base URL, with HTTPS and no trailing slash |

No private API key belongs on Vercel. If using Vercel Preview deployments against the production backend, add each approved preview origin to Render `CORS_ORIGINS`; avoid allowing arbitrary preview origins.

## Create the first platform administrator

After the Render service is running, open its Shell and run:

```sh
python scripts/saas_admin.py bootstrap-super-admin --username YOUR_ADMIN_USERNAME
```

Enter a unique strong password at the prompts. The command writes the account to `/var/data/users.json` through `AUTH_USERS_FILE`; it does not print the password. Do not add a bootstrap password or administrator credential to the Render or Vercel environment.

## Pre-launch checks

- Confirm `https://<render-service>.onrender.com/api/health` returns a healthy response.
- Confirm Render has its persistent disk mounted and `CORS_ORIGINS` contains the Vercel production origin exactly.
- Confirm Vercel Production has `VITE_API_BASE_URL` set to the Render URL, then redeploy after changing it.
- Sign in with the newly provisioned Super Admin, create an institution, and verify a test import and page refresh preserve records.
- Use HTTPS domains only. Keep the `.env` file, admin credentials, Groq key, and student CSV data out of Git.
- Configure backups for the Render persistent disk; the disk protects against redeploy loss but is not itself a backup.
