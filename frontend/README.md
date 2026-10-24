# Academia frontend

React + Vite + TypeScript + Tailwind 4 UI for the Smart Campus Analytics API. All data comes from the FastAPI backend in the parent folder; there is no mock data.

```bash
npm install
npm run dev      # http://localhost:5173, proxies /api to http://127.0.0.1:8000
npm run build    # type-checks, then writes dist/
```

Set `VITE_API_BASE_URL` (see `.env.example`) only if the API is on a different origin; then add the site origin to `CORS_ORIGINS` in the backend `.env`.

Roles are enforced by the backend and mirrored in the UI:

- `super_admin` manages institutions, account provisioning and platform audit logs.
- `college_admin` manages only one institution's students, imports, analytics and interventions.
- `student` can view only the linked personal student profile and permitted analytics.
