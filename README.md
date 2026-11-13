# Agri Vision — Smart Farm Advisory Council

Agri Vision brings farm observations, weather forecasts, agricultural knowledge and prior farm context into a coordinated advisory. The repository contains a FastAPI backend and a React frontend built with Vite.

## Features

- Weather, soil, pest and disease retrieval, irrigation and advisory-manager agents.
- Fan-out/fan-in orchestration with Semantic Kernel.
- Agricultural RAG retrieval backed by ChromaDB.
- MongoDB Atlas observation and advisory persistence keyed by a stable `farm_id`, stored in `smart_farm_db`.
- Responsive frontend for farm assessment and reviewing the returned advisory.
- Browser-persisted selected demo farm and latest actual backend response.
- Clearly marked demo access; authentication is not implemented by the backend.

## Architecture

```text
React + Vite frontend
  └── POST /api/advisory
        └── FastAPI → Advisory Manager
              ├── Weather, Soil, Pest/Disease agents (parallel)
              ├── Irrigation Planner (after forecast fan-in)
              ├── ChromaDB agricultural knowledge retrieval
              └── MongoDB Atlas farm observations and advisories
```

The browser keeps the selected farm profile and latest response so the same farm ID can be reused. Persistent farm history is read from MongoDB through credential-protected routes. The browser stores only the farm ID in local storage; a persistent HttpOnly cookie carries the single active farm credential.

## Technology

- Backend: Python 3.11, FastAPI, Semantic Kernel, Groq, ChromaDB, MongoDB Atlas, Open-Meteo.
- Frontend: React 18, Vite, React Router, Axios, CSS.

## Repository layout

```text
backend/                 Existing FastAPI and agent implementation
frontend/public/images/  Locally stored generated agricultural photographs
frontend/src/            React routes, views, context, API client and styles
frontend/.env.example    Frontend API URL example
```

## Local setup

### Backend

Use the existing backend setup and its local environment configuration. Do not commit `backend/.env` or any API keys/database credentials.

```powershell
cd backend
Copy-Item .env.example .env
python -m venv .venv
\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
uvicorn main:app --reload
```

Populate the copied `.env` with your local credentials and settings before starting the backend; the example leaves secrets empty. Never commit `.env`. The backend expects `GROQ_API_KEY`, `GROQ_MODEL`, `MONGODB_URI`, `MONGODB_DB_NAME=smart_farm_db`, `FARM_TOKEN_PEPPER`, `APP_ENV`, `COOKIE_SECURE`, and `ALLOWED_ORIGINS`. Configure `MONGODB_URI` with the original Atlas database user limited to `smart_farm_db`; the backend fails closed if another database name is configured. The `MONGODB_URI` value is preserved as-is and must contain the credentials for that user.

### Frontend

```powershell
cd frontend
npm install
Copy-Item .env.example .env.local
npm run dev
```

The frontend uses a same-origin API path. During local development, Vite proxies `/api` to `AGRI_VISION_BACKEND_ORIGIN` (default `http://127.0.0.1:8000`). The backend must allow the Vite origin in `ALLOWED_ORIGINS`.

```env
AGRI_VISION_BACKEND_ORIGIN=http://127.0.0.1:8000
```

The frontend registers a farm at `POST /api/farms` before its first assessment. The service issues a per-farm HttpOnly cookie; the assessment JSON schema remains `farm_id`, `latitude`, `longitude`, `soil_moisture`, `soil_ph`, `nitrogen`, `phosphorus`, `potassium`, `crop_name`, `growth_stage`, and `symptoms` (array of strings). Farm history is available at `GET /api/farms/{farm_id}/observations` and `/api/farms/{farm_id}/advisories`, with a maximum limit of 100.

## Pages

Landing page, About, Login and Signup demo-access screens, Dashboard, Farm Profile, Farm Assessment, Weather Insights, Soil Health, Crop Health, Irrigation Planner, Weekly Advisory, Farm History, and Settings.

Login and Signup validate entered values locally, but do not authenticate or create accounts. The demo flow does not persist passwords. Current advisory content is always rendered from a real API response; the landing dashboard preview is labelled illustrative.

The history view contains only records returned by the backend. No operational history is seeded or substituted when data is unavailable. A browser can hold one active farm credential at a time; changing farm IDs does not switch or replace the credential. Restore the registered farm ID to continue in that browser. Login and Signup pages remain informational and do not provide server-side accounts.

## Verification

```powershell
cd frontend
npm run build
npm test
```

Backend tests can be run with `python -m pytest tests/test_farm_access.py tests/test_history_routes.py tests/test_history_integration.py tests/test_main.py`. MongoDB integration tests are skipped unless `AGRIVISION_TEST_MONGODB_URI` is configured and `AGRIVISION_TEST_DB_NAME` is exactly `agrivision_test_db`. They never use the application database.

## Deployment

### Vercel frontend

Import the repository into Vercel and set **Root Directory** to `frontend`. Use the Vite defaults: install `npm install`, build `npm run build`, output directory `dist`. The included `frontend/vercel.json` rewrites SPA routes to `index.html`.

Set the server-side Vercel environment variable `BACKEND_API_ORIGIN` to the deployed Render HTTPS origin. The Vercel function under `frontend/api/` proxies `/api` requests so the browser uses a same-origin HttpOnly cookie. Do not put backend credentials or token material in `VITE_` variables.

### Render backend

Deploy the existing `backend` as a separate Python web service. Set **Root Directory** to `backend`, select Python 3.11, and set the start command to `uvicorn main:app --host 0.0.0.0 --port $PORT`. Configure the backend secrets in Render's environment settings. Configure MongoDB Atlas network access for the Render service as appropriate.

Set `APP_ENV=production`, `COOKIE_SECURE=true`, `MONGODB_DB_NAME=smart_farm_db`, a strong `FARM_TOKEN_PEPPER`, and `ALLOWED_ORIGINS` to the exact Vercel origin. Cookie authentication uses HttpOnly, SameSite=Lax and Path=/api. State-changing requests also require an allowed Origin and the application request header; CORS is not used as authentication or as the sole CSRF control. Before deployment, verify the Atlas user used by `MONGODB_URI` has access only to `smart_farm_db`. This repository cannot verify Atlas user grants or configure them.

## Known limitations

- Farm access uses a per-farm capability cookie, not user accounts. The browser supports one active farm credential; loss of that cookie is not recoverable.
- Existing `smart_farm_db` records are not inspected, migrated, or modified by configuration changes. Farm persistence uses this database through the collections selected by the backend.
- Production safety depends on configuring a database-scoped Atlas user, exact allowed origins, and the server-side Vercel backend origin.
- A deployed Render URL and production secrets are not present in this repository.
- Advice is based on the provided measurements and retrieved references; it is not a substitute for local expert inspection.
