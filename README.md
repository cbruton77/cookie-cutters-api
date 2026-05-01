# Cookie Cutters Staff Scheduling API

A FastAPI backend connected to Snowflake, designed as a reusable platform
for multiple projects (Cookie Cutters scheduling, AI analytics, etc.).

## Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  React Frontend │────▶│   FastAPI API    │────▶│    Snowflake    │
│  (Vercel/PWA)   │◀────│  (Vercel/Render) │◀────│   Warehouse    │
└─────────────────┘     └─────────────────┘     └─────────────────┘
                              │
                        ┌─────┴─────┐
                        │  Supabase │
                        │   Auth    │
                        └───────────┘
```

## Quick Start

### 1. Prerequisites
- Python 3.11+
- A Snowflake account with the SCHEDULING_APP schema created
- A Supabase project (free tier) for authentication
- Git

### 2. Clone & Install

```bash
git clone <your-repo-url>
cd cookie-cutters-api
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Configure Environment

Copy the example env file and fill in your credentials:

```bash
cp .env.example .env
```

Edit `.env` with your Snowflake and Supabase credentials.
NEVER commit the `.env` file to git.

### 4. Run Locally

```bash
uvicorn app.main:app --reload --port 8000
```

API docs available at: http://localhost:8000/docs

### 5. Deploy

**Option A: Vercel (recommended)**
```bash
npm i -g vercel
vercel
```

**Option B: Render**
- Connect your GitHub repo at render.com
- Set environment variables in the Render dashboard
- Auto-deploys on every push

**Option C: Railway**
```bash
npm i -g @railway/cli
railway login
railway init
railway up
```

## Project Structure

```
cookie-cutters-api/
├── app/
│   ├── main.py              # FastAPI app entry point, CORS, routers
│   ├── config/
│   │   └── settings.py      # Environment variable management
│   ├── db/
│   │   └── snowflake.py     # Snowflake connection pool
│   ├── auth/
│   │   └── middleware.py     # Supabase JWT validation
│   ├── models/
│   │   ├── users.py         # User schemas
│   │   ├── shifts.py        # Shift schemas
│   │   ├── time_off.py      # Time-off request schemas
│   │   └── admin.py         # Templates, closed dates, blackouts
│   └── routers/
│       ├── users.py         # /api/scheduling/users endpoints
│       ├── shifts.py        # /api/scheduling/shifts endpoints
│       ├── time_off.py      # /api/scheduling/time-off endpoints
│       ├── templates.py     # /api/scheduling/templates endpoints
│       ├── admin.py         # /api/scheduling/admin endpoints
│       └── health.py        # /api/health endpoint
├── tests/
├── requirements.txt
├── .env.example
├── .gitignore
├── vercel.json              # Vercel deployment config
└── README.md
```

## Adding a New Project (e.g., AI Analytics)

1. Create a new schema in Snowflake
2. Create a new Snowflake role for that schema
3. Add a new router folder: `app/routers/analytics/`
4. Register the router in `app/main.py`
5. Same auth, same connection pool — just a new set of endpoints

## API Endpoints

### Auth
- `POST /api/auth/login` — Login with email/password
- `POST /api/auth/register` — Register new user (manager only)

### Shifts
- `GET /api/scheduling/shifts?week_start=2026-05-04&location_id=1`
- `POST /api/scheduling/shifts`
- `PUT /api/scheduling/shifts/{shift_id}`
- `DELETE /api/scheduling/shifts/{shift_id}`

### Users
- `GET /api/scheduling/users?location_id=1`
- `POST /api/scheduling/users`
- `PUT /api/scheduling/users/{user_id}`
- `DELETE /api/scheduling/users/{user_id}`

### Time Off
- `GET /api/scheduling/time-off?status=pending&location_id=1`
- `POST /api/scheduling/time-off`
- `PUT /api/scheduling/time-off/{request_id}` (approve/deny)

### Templates
- `GET /api/scheduling/templates`
- `POST /api/scheduling/templates`
- `PUT /api/scheduling/templates/{template_id}`
- `DELETE /api/scheduling/templates/{template_id}`

### Admin
- `GET /api/scheduling/closed-dates`
- `POST /api/scheduling/closed-dates`
- `DELETE /api/scheduling/closed-dates/{id}`
- `GET /api/scheduling/blackout-periods`
- `POST /api/scheduling/blackout-periods`
- `DELETE /api/scheduling/blackout-periods/{id}`
