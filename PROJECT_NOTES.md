# Cookie Cutters Staff Scheduling Platform — Project Notes

## Overview
Custom staff scheduling PWA for Cookie Cutters Haircuts for Kids franchise. Owned by Chad Bruton. Two salons currently (Fort Worth TX, Arlington TX) with 120 franchisees ready to onboard.

## Tech Stack
- **Frontend**: React (JSX with Babel, served as static files from FastAPI)
  - `static/index.html` — HTML shell, loads React from CDN
  - `static/app.jsx` — Full React app with all components
  - Font: Plus Jakarta Sans, accent color: #3b82f6 (muted blue)
- **Backend**: Python FastAPI with 43+ API endpoints
- **Database**: Snowflake (COOKIECUTTERSCORP.SCHEDULING_APP schema)
- **Auth**: Dev bypass via `?user=USER_ID` URL param (Supabase auth planned)
- **Hosting**: Railway at `https://cookie-cutters-api-production.up.railway.app`
- **AI**: Claude API (claude-sonnet-4-6) for auto-schedule generation
- **Git**: github.com/cbruton77/cookie-cutters-api, `main` branch auto-deploys to Railway

## Git Workflow
- `main` branch = production (auto-deploys to Railway)
- `dev` branch = development (test locally, merge to main when ready)
- Merge: `git checkout main && git merge dev && git push`

## Snowflake Configuration
- **Account**: VVIZEMO-MEC90094
- **Database/Schema**: COOKIECUTTERSCORP.SCHEDULING_APP
- **Role**: SCHEDULING_SERVICE_ROLE / Warehouse: SCHEDULING_APP_WH
- **API User**: SCHEDULING_API_USER (key-pair auth, unencrypted key, password=None)
- **SNOWFLAKE_PRIVATE_KEY_BASE64**: env var (not PATH)
- **LOCATION_ID is VARCHAR** — all queries must use CAST or string comparison

## Location IDs
- Fort Worth = "153"
- Arlington = "187"

## User IDs (SiteID + 4-digit sequence)
Format: {LocationID}{0001-9999}

### Fort Worth (153)
| User ID | Name | Role | Type |
|---------|------|------|------|
| 1530001 | Marinna G. | Regional Mgr/Stylist | Full-time |
| 1530002 | Chad B. | Owner | Full-time |
| 1530003 | Heather B. | Owner | Full-time |
| 1530004 | Christina G. | Stylist | Full-time |
| 1530005 | Ashley H. | Stylist | Part-time |
| 1530006 | Kaitlin H. | Receptionist/Stylist | Full-time |
| 1530007 | Audrey M. | Stylist | Full-time |
| 1530008 | Arlena P. | Stylist | Full-time |
| 1530009 | Hadassah T. | Stylist | Full-time |
| 1530010 | Sally O. | Receptionist | Part-time |

### Arlington (187)
| User ID | Name | Role | Type |
|---------|------|------|------|
| 1870001 | Marinna G. | Regional Mgr/Stylist | Full-time |
| 1870002 | Amy R. | Manager/Stylist | Full-time |
| 1870003 | Lanore G. | Stylist | Full-time |
| 1870004 | Ruth J. | Stylist | Part-time |
| 1870005 | Diana L. | Stylist | Full-time |
| 1870006 | Heather B. | Receptionist/Stylist | Full-time |

## Permission Model
- **EDITORS** (can edit schedule, manage team, admin access): Chad (1530002), Heather (1530003), Marinna FW (1530001), Marinna ARL (1870001) — hardcoded in `app.jsx`
- **Managers** (IS_MANAGER=true): see all locations, approve time-off
- **Staff**: view own location only, only see PUBLISHED shifts

## Database Tables
LOCATIONS, USERS (with EMPLOYMENT_TYPE, STATUS columns), POSITIONS, USER_POSITIONS, SHIFTS (with STATUS: DRAFT/PUBLISHED), TIME_OFF_REQUESTS, CLOSED_DATES, BLACKOUT_PERIODS, SHIFT_TEMPLATES, ANNOUNCEMENTS, USER_LOGIN_LOG, BUSINESS_HOURS, SCHEDULING_RULES, DRAFT_SCHEDULES, EMPLOYEE_HOURS_HAIRCUTS_HISTORY (2,427 rows historical data)

## Key Files
- `app/main.py` — FastAPI entry, mounts static files, serves index.html at root
- `app/config/settings.py` — Pydantic settings (includes ANTHROPIC_API_KEY)
- `app/db/snowflake.py` — Connection pool (password=None for unencrypted keys)
- `app/auth/middleware.py` — Dev bypass via `dev_user_id` query param
- `app/routers/shifts.py` — CRUD + move + publish/unpublish endpoints
- `app/routers/time_off.py` — Time-off requests with approve/deny/delete
- `app/routers/admin.py` — Closed dates, blackouts, announcements, rules, hours
- `app/routers/autoschedule.py` — AI auto-scheduler using Claude API
- `app/routers/users.py` — User CRUD
- `app/routers/templates.py` — Shift templates
- `app/models/` — Pydantic models (all location_id as str)
- `static/index.html` — HTML shell loading React from CDN
- `static/app.jsx` — Full React frontend app
- `Procfile` — `web: uvicorn app.main:app --host 0.0.0.0 --port $PORT`

## Railway Configuration
- **URL**: https://cookie-cutters-api-production.up.railway.app
- **GitHub**: cbruton77/cookie-cutters-api (main branch)
- **CORS_ORIGINS**: includes localhost, railway domain, claude.ai, claude.site
- **SNOWFLAKE_ACCOUNT**: VVIZEMO-MEC90094
- **SNOWFLAKE_PRIVATE_KEY_BASE64**: set in env vars
- **ANTHROPIC_API_KEY**: set (for auto-scheduler, needs Railway payment for outbound networking)

## Auto-Scheduler
- Uses Claude API (claude-sonnet-4-6) with 5-min read timeout
- Async httpx client for uvicorn event loop compatibility
- System message forces JSON-only output
- Calculates staffing targets from EMPLOYEE_HOURS_HAIRCUTS_HISTORY using math.ceil, capped at 5 stylists max
- Writes directly to SHIFTS table (status=DRAFT)
- Prescriptive day-by-day targets from historical data
- Receptionist rules: Fort Worth only, Mon/Thu/Fri/Sat/Sun only
- Employment type aware: FT=35-37hrs/wk, PT=16-24hrs/wk
- Audrey McDonald: max 3 consecutive days rule
- Works locally but blocked on Railway until outbound networking payment added

## Current Features (React rebuild)
- [x] Calendar view — all 7 days visible, staff rows, shift pills with role colors
- [x] List view toggle — WhenIWork-style shift cards per day
- [x] Date picker — jump to any week, "Today" button
- [x] Drag-and-drop shifts between days
- [x] Draft/Published workflow — dashed borders + hatched overlay for drafts
- [x] Publish/Unpublish per week
- [x] Non-managers only see PUBLISHED shifts
- [x] Time-off requests on calendar grid (striped=pending, solid gray=approved)
- [x] Time-off management — deny with comment, admin delete
- [x] People/Team editing — add, edit, remove employees
- [x] Admin tab — view templates, rules, business hours
- [x] Overview/Home tab — announcements, pending requests count, upcoming holidays
- [x] Location filter for managers
- [x] Toast notifications
- [x] Shift modal — add/edit with role selection, time pickers, templates

## Pending / Future Work
- [ ] Full admin CRUD (add/edit/delete rules, templates, hours, announcements from React)
- [ ] Auto-scheduler UI in React admin tab
- [ ] Desktop responsive layout (wider grids, sidebar nav)
- [ ] Supabase authentication (replace ?user= URL param)
- [ ] PWA manifest + app icon for home screen install
- [ ] Multi-tenancy — FRANCHISE_ID for 120 franchisees
- [ ] Auto-scheduler tuning — staffing levels from historical data
- [ ] Railway outbound networking — add payment for Claude API access
- [ ] Rotate credentials (Supabase keys, RSA key pair shared in chat)

## Business Rules
- Max 5 stylists per day (never 6)
- Fort Worth: Receptionist on Mon, Thu, Fri, Sat, Sun only (not Tue/Wed)
- Arlington: No receptionist position
- Full-time: 35-37 hours/week, 4-5 shifts
- Part-time: 15-25 hours/week, 2-3 shifts
- Audrey McDonald: max 3 consecutive working days
- Every employee: at least 1 Saturday AND 1 Sunday off per month
- Shifts start 10 min before salon opens

## Testing URLs
```
Production: https://cookie-cutters-api-production.up.railway.app/?user=1530002
Local:      http://localhost:8000/?user=1530002

Chad (owner):        ?user=1530002
Heather (owner):     ?user=1530003
Marinna FW (mgr):    ?user=1530001
Amy ARL (mgr):       ?user=1870002
Christina (stylist): ?user=1530004
```

## Local Development
```powershell
cd C:\Users\cdb3\Dropbox\AI-Projects\cookie-cutters-api
.\venv\Scripts\Activate
uvicorn app.main:app --reload --port 8000
```
