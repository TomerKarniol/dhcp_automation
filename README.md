# DHCP Automation

DHCP Automation is a two-part system for managing Windows DHCP scopes:

- A **FastAPI backend** that runs PowerShell cmdlets on a Windows DHCP server
- A **Next.js frontend** for operators to create, inspect, and modify scopes

The backend handles scope lifecycle, DNS options, exclusions, and failover relationships. The frontend provides a dashboard, create wizard, detail panel, and lightweight login gate.

## Repository Layout

```text
.
├── src/                     # FastAPI backend
├── tests/                   # Python tests (backend)
├── frontend/                # Next.js UI
├── example_requests.json    # API request examples
├── requirements.txt
└── README.md
```

## Backend (FastAPI + PowerShell)

### What it does

- Validates DHCP scope payloads with Pydantic + custom validators
- Executes Windows DHCP cmdlets via `powershell.exe`
- Returns structured step-by-step provisioning results
- Supports partial success (`207`) when non-critical steps fail
- Protects all routes with `X-API-Key`

### Key backend files

```text
src/
├── main.py
├── core/
│   ├── config.py
│   ├── startup.py
│   ├── security.py
│   └── decorators.py
├── models/
│   ├── schemas.py
│   └── validators.py
├── services/
│   └── executor.py
└── api/
    ├── router.py
    ├── test_data.py
    └── routes/
        ├── health.py
        ├── scopes.py
        ├── dns.py
        ├── exclusions.py
        └── failover.py
```

## Frontend (Next.js 16)

### What it does

- Login page with session-based auth gate
- Dashboard with scope search/filter/grouping
- Create scope wizard (validated with Zod)
- Scope detail panel actions:
  - Activate/deactivate scope
  - Update DNS
  - Add/remove exclusions
  - Add/update failover
  - Delete scope
- Health indicator polling `/health`

### Important frontend behavior

- API is called from the browser with headers including `X-API-Key`
- `NEXT_PUBLIC_USE_TEST_DATA=true` switches list view to `/scopes/test`
- Current auth is client-side env-credential based (`NEXT_PUBLIC_AUTH_USER/PASS`), suitable for internal/demo use, not hardened SSO

## Prerequisites

### Backend host

- Windows Server with DHCP Server role
- Python 3.10+
- PowerShell available as `powershell.exe`
- User with DHCP admin rights

### Frontend host

- Node.js 20+
- npm

## Environment Configuration

### Backend `.env` (repo root)

```env
DHCP_API_KEY=your-secret-key
```

The backend startup validation fails if `DHCP_API_KEY` is missing.

### Frontend `.env.local` (`frontend/.env.local`)

```env
NEXT_PUBLIC_API_URL=http://localhost:8080
NEXT_PUBLIC_DHCP_API_KEY=your-secret-key
NEXT_PUBLIC_USE_TEST_DATA=false
NEXT_PUBLIC_AUTH_USER=admin
NEXT_PUBLIC_AUTH_PASS=change-me
```

## Installation

### 1) Backend

```bash
cd /path/to/dhcp_automation
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2) Frontend

```bash
cd frontend
npm install
```

## Running

### Start backend

```bash
cd src
uvicorn main:app --host 0.0.0.0 --port 8080
```

Docs: `http://localhost:8080/docs`

### Start frontend

```bash
cd frontend
npm run dev
```

UI: `http://localhost:3000`

## API Summary

Base URL: `http://<backend>:8080`

- `GET /health`
- `GET /scopes/test`
- `GET /scopes`
- `POST /scopes`
- `GET /scopes/{scope_id}`
- `GET /scopes/{scope_id}/exists`
- `DELETE /scopes/{scope_id}`
- `PATCH /scopes/{scope_id}/state`
- `PATCH /scopes/{scope_id}/dns`
- `POST /scopes/{scope_id}/exclusions?start=...&end=...`
- `DELETE /scopes/{scope_id}/exclusions?start=...&end=...`
- `POST /scopes/{scope_id}/failover`
- `PATCH /scopes/{scope_id}/failover`
- `GET /failover`

Common statuses:

- `200` success
- `201` created
- `207` partial success (scope created, some non-critical step failed)
- `401` invalid/missing API key
- `404` resource not found
- `409` conflict (already exists / active lease conflict)
- `422` validation error
- `500` command or server error
- `503` PowerShell unavailable / access denied / service unavailable

## Testing

### Backend tests

```bash
pytest -v
```

### Frontend tests

```bash
cd frontend
npx vitest run
```

### Frontend lint

```bash
cd frontend
npm run lint
```

## Security Notes

- All backend routes require `X-API-Key`.
- `NEXT_PUBLIC_*` variables are exposed to browser code. Do not treat frontend env values as secrets.
- For production, place backend behind HTTPS/reverse proxy and replace client-side login with real identity/authn.

## Example Requests

See [`example_requests.json`](example_requests.json) for full payload examples, including:

- Minimal scope creation
- Full scope creation with overrides
- LoadBalance failover example
- DNS update example
