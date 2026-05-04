"""
Auto-Schedule Generator — Uses Claude API to create optimized monthly schedules.
"""
import json
import uuid
from datetime import date, timedelta
from fastapi import APIRouter, Depends, HTTPException
from app.db import get_db, SnowflakeSession
from app.auth import require_manager, AuthenticatedUser
from app.config import get_settings
import httpx
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/scheduling", tags=["Auto-Schedule"])

CLAUDE_API = "https://api.anthropic.com/v1/messages"
CLAUDE_MODEL = "claude-sonnet-4-6"


def _gather_context(db: SnowflakeSession, location_id: str, target_month: int, target_year: int):
    """Gather all scheduling context from Snowflake for the AI."""

    # 1. Employees at this location with positions
    employees = db.execute_all("""
        SELECT u.USER_ID, u.FIRST_NAME, u.LAST_NAME, u.DISPLAY_NAME, u.IS_MANAGER,
               u.EMPLOYMENT_TYPE,
               LISTAGG(p.POSITION_NAME, ', ') WITHIN GROUP (ORDER BY p.POSITION_NAME) AS POSITIONS
        FROM USERS u
        JOIN USER_POSITIONS up ON u.USER_ID = up.USER_ID
        JOIN POSITIONS p ON up.POSITION_ID = p.POSITION_ID
        WHERE u.LOCATION_ID = %s AND u.IS_ACTIVE = TRUE
        GROUP BY u.USER_ID, u.FIRST_NAME, u.LAST_NAME, u.DISPLAY_NAME, u.IS_MANAGER, u.EMPLOYMENT_TYPE
        ORDER BY u.DISPLAY_NAME
    """, [location_id])

    # 2. Business hours for this location
    hours = db.execute_all("""
        SELECT DAY_OF_WEEK, DAY_NAME, 
               TO_CHAR(OPEN_TIME, 'HH24:MI') AS OPEN_TIME, 
               TO_CHAR(CLOSE_TIME, 'HH24:MI') AS CLOSE_TIME,
               IS_OPEN, SHIFT_START_OFFSET
        FROM BUSINESS_HOURS
        WHERE LOCATION_ID = %s
        ORDER BY DAY_OF_WEEK
    """, [location_id])

    # 3. Scheduling rules (global + location-specific)
    rules = db.execute_all("""
        SELECT sr.RULE_TYPE, sr.RULE_NAME, sr.RULE_DESCRIPTION, sr.PARAM_1, sr.PARAM_2,
               u.DISPLAY_NAME AS APPLIES_TO
        FROM SCHEDULING_RULES sr
        LEFT JOIN USERS u ON sr.USER_ID = u.USER_ID
        WHERE sr.IS_ACTIVE = TRUE
          AND (sr.LOCATION_ID IS NULL OR sr.LOCATION_ID = %s)
        ORDER BY sr.RULE_TYPE
    """, [location_id])

    # 4. Closed dates for the target month
    first_of_month = date(target_year, target_month, 1)
    if target_month == 12:
        last_of_month = date(target_year + 1, 1, 1) - timedelta(days=1)
    else:
        last_of_month = date(target_year, target_month + 1, 1) - timedelta(days=1)

    closed = db.execute_all("""
        SELECT CLOSED_DATE, LABEL FROM CLOSED_DATES
        WHERE CLOSED_DATE BETWEEN %s AND %s
          AND (LOCATION_ID IS NULL OR LOCATION_ID = %s)
        ORDER BY CLOSED_DATE
    """, [first_of_month, last_of_month, location_id])

    # 5. Approved time-off for the target month
    time_off = db.execute_all("""
        SELECT u.DISPLAY_NAME, tor.START_DATE, tor.END_DATE, tor.REASON
        FROM TIME_OFF_REQUESTS tor
        JOIN USERS u ON tor.USER_ID = u.USER_ID
        WHERE tor.STATUS = 'APPROVED'
          AND tor.START_DATE <= %s AND tor.END_DATE >= %s
          AND u.LOCATION_ID = %s
        ORDER BY tor.START_DATE
    """, [last_of_month, first_of_month, location_id])

    # 6. Historical haircut data — same month last year
    last_year_month_start = date(target_year - 1, target_month, 1)
    if target_month == 12:
        last_year_month_end = date(target_year, 1, 1) - timedelta(days=1)
    else:
        last_year_month_end = date(target_year - 1, target_month + 1, 1) - timedelta(days=1)

    # Get location name for the history table
    loc_info = db.execute_one("""
        SELECT LOCATION_NAME FROM LOCATIONS WHERE LOCATION_ID = %s
    """, [location_id])
    loc_name_pattern = f"%{loc_info['LOCATION_NAME']}%"

    historical_by_day = db.execute_all("""
        SELECT DAYNAME(TO_DATE(WORK_DATE, 'YYYY-MM-DD')) AS DAY_NAME,
               DAYOFWEEK(TO_DATE(WORK_DATE, 'YYYY-MM-DD')) AS DOW,
               ROUND(SUM(HAIRCUT_COUNT) / COUNT(DISTINCT WORK_DATE), 1) AS AVG_DAILY_HAIRCUTS,
               ROUND(AVG(WORKEDHOURS), 1) AS AVG_HOURS_PER_PERSON,
               COUNT(DISTINCT EMPLOYEE_FULL_NAME) AS AVG_STAFF_COUNT
        FROM EMPLOYEE_HOURS_HAIRCUTS_HISTORY
        WHERE WORK_DATE BETWEEN %s AND %s
          AND LOCATION LIKE %s
        GROUP BY DAY_NAME, DOW
        ORDER BY DOW
    """, [str(last_year_month_start), str(last_year_month_end), loc_name_pattern])

    # 7. Recent 3-month trends (to see if demand is up or down vs last year)
    three_months_ago = first_of_month - timedelta(days=90)
    recent_trends = db.execute_all("""
        SELECT DAYNAME(TO_DATE(WORK_DATE, 'YYYY-MM-DD')) AS DAY_NAME,
               DAYOFWEEK(TO_DATE(WORK_DATE, 'YYYY-MM-DD')) AS DOW,
               ROUND(SUM(HAIRCUT_COUNT) / COUNT(DISTINCT WORK_DATE), 1) AS AVG_DAILY_HAIRCUTS,
               COUNT(DISTINCT EMPLOYEE_FULL_NAME) AS AVG_STAFF_COUNT
        FROM EMPLOYEE_HOURS_HAIRCUTS_HISTORY
        WHERE WORK_DATE BETWEEN %s AND %s
          AND LOCATION LIKE %s
        GROUP BY DAY_NAME, DOW
        ORDER BY DOW
    """, [str(three_months_ago), str(first_of_month - timedelta(days=1)), loc_name_pattern])

    # 8. Employee work patterns — which days each person typically works
    employee_patterns = db.execute_all("""
        SELECT EMPLOYEE_FULL_NAME,
               DAYNAME(TO_DATE(WORK_DATE, 'YYYY-MM-DD')) AS DAY_NAME,
               DAYOFWEEK(TO_DATE(WORK_DATE, 'YYYY-MM-DD')) AS DOW,
               COUNT(*) AS TIMES_WORKED
        FROM EMPLOYEE_HOURS_HAIRCUTS_HISTORY
        WHERE WORK_DATE >= DATEADD(MONTH, -6, CURRENT_DATE())
          AND LOCATION LIKE %s
        GROUP BY EMPLOYEE_FULL_NAME, DAY_NAME, DOW
        ORDER BY EMPLOYEE_FULL_NAME, DOW
    """, [loc_name_pattern])

    # 9. Calculate recommended staffing levels from actual historical data
    staffing_levels = db.execute_all("""
        SELECT DAYNAME(TO_DATE(WORK_DATE, 'YYYY-MM-DD')) AS DAY_NAME,
               DAYOFWEEK(TO_DATE(WORK_DATE, 'YYYY-MM-DD')) AS DOW,
               ROUND(SUM(HAIRCUT_COUNT)/COUNT(DISTINCT WORK_DATE),1) AS AVG_DAILY_HAIRCUTS,
               ROUND(SUM(HAIRCUT_COUNT)/NULLIF(SUM(WORKEDHOURS),0),1) AS HAIRCUTS_PER_HOUR,
               ROUND(COUNT(*)/COUNT(DISTINCT WORK_DATE),1) AS AVG_STAFF_PER_DAY
        FROM EMPLOYEE_HOURS_HAIRCUTS_HISTORY
        WHERE WORK_DATE >= DATEADD(MONTH, -6, CURRENT_DATE())
          AND LOCATION LIKE %s
        GROUP BY DAY_NAME, DOW
        ORDER BY DOW
    """, [loc_name_pattern])

    # 10. Check which positions exist at this location (for receptionist logic)
    location_positions = db.execute_all("""
        SELECT DISTINCT p.POSITION_NAME
        FROM USER_POSITIONS up
        JOIN POSITIONS p ON up.POSITION_ID = p.POSITION_ID
        JOIN USERS u ON up.USER_ID = u.USER_ID
        WHERE u.LOCATION_ID = %s AND u.IS_ACTIVE = TRUE
    """, [location_id])
    has_receptionist = any(p["POSITION_NAME"] == "Receptionist" for p in location_positions)

    return {
        "employees": [dict(e) for e in employees],
        "business_hours": [dict(h) for h in hours],
        "scheduling_rules": [dict(r) for r in rules],
        "closed_dates": [dict(c) for c in closed],
        "time_off": [dict(t) for t in time_off],
        "historical_by_day": [dict(h) for h in historical_by_day],
        "recent_trends": [dict(r) for r in recent_trends],
        "employee_patterns": [dict(e) for e in employee_patterns],
        "staffing_levels": [dict(s) for s in staffing_levels],
        "has_receptionist": has_receptionist,
        "location_name": loc_info["LOCATION_NAME"],
        "target_month": target_month,
        "target_year": target_year,
        "first_of_month": str(first_of_month),
        "last_of_month": str(last_of_month),
    }


def _build_prompt(context: dict, location_name: str) -> str:
    """Build the Claude prompt with all scheduling context."""

    first = date.fromisoformat(context["first_of_month"])
    last = date.fromisoformat(context["last_of_month"])
    days = []
    d = first
    while d <= last:
        days.append({"date": str(d), "day_name": d.strftime("%A"), "dow": d.weekday()})
        d += timedelta(days=1)

    # Build staffing targets from actual data
    staffing_table = ""
    for sl in context.get("staffing_levels", []):
        staff_count = round(float(sl.get("AVG_STAFF_PER_DAY", 3)))
        staffing_table += f"  {sl['DAY_NAME']}: {sl['AVG_DAILY_HAIRCUTS']} avg haircuts, historically staffed {sl['AVG_STAFF_PER_DAY']} stylists → target {staff_count} stylists\n"

    # Receptionist rules
    has_receptionist = context.get("has_receptionist", False)
    if has_receptionist:
        recept_rules = """RECEPTIONIST RULES (Fort Worth only):
- Schedule exactly 1 Receptionist on Monday, Thursday, Friday, Saturday, and Sunday
- Do NOT schedule a Receptionist on Tuesday or Wednesday
- Kaitlin Hoover can work as Receptionist OR Stylist — when she works as Receptionist, she does NOT count toward the stylist target
- Sally Olivas is Receptionist only"""
    else:
        recept_rules = "This location does NOT have a Receptionist position. Do not schedule any Receptionist shifts."

    prompt = f"""You are an expert staff scheduler for Cookie Cutters Haircuts for Kids in {location_name}. Generate a COMPLETE schedule for every day in the month of {context['first_of_month']} through {context['last_of_month']}.

## EMPLOYEES AT THIS LOCATION
{json.dumps(context['employees'], indent=2, default=str)}

## BUSINESS HOURS
{json.dumps(context['business_hours'], indent=2, default=str)}

## CLOSED DATES — NO SHIFTS
{json.dumps(context['closed_dates'], indent=2, default=str)}

## APPROVED TIME OFF — DO NOT SCHEDULE
{json.dumps(context['time_off'], indent=2, default=str)}

## EMPLOYEE WORK PATTERNS (last 6 months — who works which days)
{json.dumps(context['employee_patterns'], indent=2, default=str)}

## ===== STAFFING LEVELS FROM ACTUAL SALES DATA =====
This is the most important section. These numbers come from real haircut data at THIS location.
Use them to determine exactly how many stylists to schedule each day:
{staffing_table}

## {recept_rules}

## SHIFT TIMES (10 min before open)
- Monday-Friday: 09:50 to 18:00 (8h 10m = 8.17 hours)
- Saturday: 08:50 to 17:00 (8h 10m = 8.17 hours)
- Sunday: 11:50 to 17:00 (5h 10m = 5.17 hours)

## ===== HARD RULES (NEVER VIOLATE) =====
1. **MAX 37 HOURS PER WEEK per employee.** No exceptions. Count hours as: weekday=8.17h, saturday=8.17h, sunday=5.17h. A full-time employee working 5 weekdays = 40.85h which EXCEEDS the limit. Full-time employees must work 4 weekdays + 1 weekend day OR similar combinations that stay UNDER 37 hours.
2. **FULL_TIME employees: 4-5 shifts per week, NEVER exceeding 37 hours.** Typical pattern: 4 weekdays (32.68h) + 0-1 weekend days.
3. **PART_TIME employees: 2-3 shifts per week, target 15-25 hours.**
4. **Audrey McDonald: MAX 3 consecutive working days**, then must have at least 1 day off.
5. **Weekend balance: Every employee gets at least 1 Saturday AND 1 Sunday off per month.**
6. **Never schedule anyone on closed dates or approved time-off dates.**
7. **Match staffing to the data-driven targets above** — do NOT over-staff or under-staff.

## SCHEDULING RULES FROM DATABASE
{json.dumps(context['scheduling_rules'], indent=2, default=str)}

## ALL DAYS TO SCHEDULE
{json.dumps(days, indent=2)}

## OUTPUT FORMAT
Return ONLY a JSON array. No other text, no markdown, no explanation.
Each element: {{"user_id": 123, "shift_date": "YYYY-MM-DD", "start_time": "HH:MM:SS", "end_time": "HH:MM:SS", "position": "Stylist", "reasoning": "brief"}}

CRITICAL: Generate shifts for ALL {len(days)} days. Do not stop partway through the month."""

    return prompt


@router.post("/auto-generate")
async def auto_generate_schedule(
    data: dict,
    user: AuthenticatedUser = Depends(require_manager),
    db: SnowflakeSession = Depends(get_db),
):
    """
    Generate an AI-optimized schedule for a location and month.
    Expects: { "location_id": "153", "month": 6, "year": 2026 }
    """
    location_id = data["location_id"]
    target_month = data["month"]
    target_year = data["year"]

    # Get location name
    loc = db.execute_one("SELECT LOCATION_NAME FROM LOCATIONS WHERE LOCATION_ID = %s", [location_id])
    if not loc:
        raise HTTPException(status_code=404, detail="Location not found")
    location_name = loc["LOCATION_NAME"]

    # Gather all context
    logger.info(f"Gathering scheduling context for {location_name}, {target_month}/{target_year}")
    context = _gather_context(db, location_id, target_month, target_year)

    if not context["employees"]:
        raise HTTPException(status_code=400, detail="No employees with positions found at this location")

    # Build prompt
    prompt = _build_prompt(context, location_name)
    logger.info(f"Prompt built: {len(prompt)} chars, sending to Claude API")

    # Call Claude API
    settings = get_settings()
    if not settings.anthropic_api_key:
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY not configured")

    try:
        response = httpx.post(
            CLAUDE_API,
            headers={
                "Content-Type": "application/json",
                "x-api-key": settings.anthropic_api_key,
                "anthropic-version": "2023-06-01",
            },
            json={
                "model": CLAUDE_MODEL,
                "max_tokens": 32000,
                "system": "You are a JSON API. You MUST respond with ONLY a valid JSON array. No text, no explanation, no markdown, no thinking out loud. Start your response with [ and end with ]. Nothing else.",
                "messages": [
                    {"role": "user", "content": prompt},
                    {"role": "assistant", "content": "["}
                ],
            },
            timeout=httpx.Timeout(connect=30.0, read=300.0, write=30.0, pool=30.0),
        )
        response.raise_for_status()
        result = response.json()
    except httpx.HTTPStatusError as e:
        logger.error(f"Claude API HTTP error: {e.response.status_code} - {e.response.text[:500]}")
        raise HTTPException(status_code=500, detail=f"AI generation failed: HTTP {e.response.status_code}")
    except Exception as e:
        logger.error(f"Claude API error: {type(e).__name__}: {e}")
        raise HTTPException(status_code=500, detail=f"AI generation failed: {type(e).__name__}: {str(e)}")

    # Parse the response
    try:
        ai_text = result["content"][0]["text"]
        # Prepend the [ we used as assistant prefill
        ai_text = "[" + ai_text
        # Clean potential markdown fencing
        ai_text = ai_text.strip()
        if ai_text.startswith("```"):
            ai_text = ai_text.split("\n", 1)[1] if "\n" in ai_text else ai_text[3:]
            if ai_text.endswith("```"):
                ai_text = ai_text[:-3]
            ai_text = ai_text.strip()

        shifts = json.loads(ai_text)
    except (json.JSONDecodeError, KeyError, IndexError) as e:
        logger.error(f"Failed to parse AI response: {e}\n{ai_text[:500]}")
        raise HTTPException(status_code=500, detail="Failed to parse AI-generated schedule")

    # Write directly to SHIFTS table
    batch_id = str(uuid.uuid4())[:8]
    position_map = {}
    pos_rows = db.execute_all("SELECT POSITION_ID, POSITION_NAME FROM POSITIONS")
    for p in pos_rows:
        position_map[p["POSITION_NAME"]] = p["POSITION_ID"]

    inserted = 0
    skipped = 0
    for shift in shifts:
        pos_id = position_map.get(shift.get("position", "Stylist"), 1)
        start = shift["start_time"]
        end = shift["end_time"]

        # Calculate hours
        sh, sm = map(int, start.split(":")[0:2])
        eh, em = map(int, end.split(":")[0:2])
        hours = (eh + em / 60) - (sh + sm / 60)

        try:
            # Check for existing shift (avoid duplicates)
            existing = db.execute_one("""
                SELECT SHIFT_ID FROM SHIFTS 
                WHERE USER_ID = %s AND SHIFT_DATE = %s
            """, [shift["user_id"], shift["shift_date"]])
            
            if existing:
                skipped += 1
                continue

            db.execute("""
                INSERT INTO SHIFTS (USER_ID, LOCATION_ID, SHIFT_DATE, START_TIME, END_TIME, POSITION_ID, HOURS_SCHEDULED, CREATED_BY, NOTES)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, [shift["user_id"], location_id, shift["shift_date"], start, end, pos_id, 
                  round(hours, 2), user.user_id, f"AI-generated ({batch_id}): {shift.get('reasoning', '')}"])
            inserted += 1
        except Exception as e:
            logger.error(f"Failed to insert shift: {e}")

    # Also save to drafts for record-keeping
    for shift in shifts:
        pos_id = position_map.get(shift.get("position", "Stylist"), 1)
        start = shift["start_time"]
        end = shift["end_time"]
        sh, sm = map(int, start.split(":")[0:2])
        eh, em = map(int, end.split(":")[0:2])
        hours = (eh + em / 60) - (sh + sm / 60)
        try:
            db.execute("""
                INSERT INTO DRAFT_SCHEDULES (BATCH_ID, LOCATION_ID, USER_ID, SHIFT_DATE, START_TIME, END_TIME, POSITION_ID, HOURS_SCHEDULED, AI_REASONING, STATUS)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'APPROVED')
            """, [batch_id, location_id, shift["user_id"], shift["shift_date"], start, end, pos_id, round(hours, 2), shift.get("reasoning", "")])
        except Exception:
            pass

    return {
        "batch_id": batch_id,
        "location": location_name,
        "month": target_month,
        "year": target_year,
        "shifts_generated": inserted,
        "shifts_skipped": skipped,
        "message": f"Created {inserted} shifts for {location_name} (skipped {skipped} existing)"
    }


@router.get("/drafts/{batch_id}")
async def get_draft_schedule(
    batch_id: str,
    user: AuthenticatedUser = Depends(require_manager),
    db: SnowflakeSession = Depends(get_db),
):
    """Get all shifts in a draft batch for review."""
    rows = db.execute_all("""
        SELECT ds.DRAFT_ID, ds.BATCH_ID, CAST(ds.LOCATION_ID AS VARCHAR) AS LOCATION_ID,
               ds.USER_ID, u.DISPLAY_NAME, ds.SHIFT_DATE,
               TO_CHAR(ds.START_TIME, 'HH12:MI AM') AS START_TIME,
               TO_CHAR(ds.END_TIME, 'HH12:MI AM') AS END_TIME,
               p.POSITION_NAME, ds.HOURS_SCHEDULED, ds.AI_REASONING, ds.STATUS
        FROM DRAFT_SCHEDULES ds
        JOIN USERS u ON ds.USER_ID = u.USER_ID
        JOIN POSITIONS p ON ds.POSITION_ID = p.POSITION_ID
        WHERE ds.BATCH_ID = %s
        ORDER BY ds.SHIFT_DATE, u.DISPLAY_NAME
    """, [batch_id])
    return [dict(r) for r in rows]


@router.post("/drafts/{batch_id}/approve")
async def approve_draft_schedule(
    batch_id: str,
    user: AuthenticatedUser = Depends(require_manager),
    db: SnowflakeSession = Depends(get_db),
):
    """Approve a draft and copy all shifts to the live SHIFTS table."""
    drafts = db.execute_all("""
        SELECT * FROM DRAFT_SCHEDULES
        WHERE BATCH_ID = %s AND STATUS = 'DRAFT'
    """, [batch_id])

    if not drafts:
        raise HTTPException(status_code=404, detail="No draft shifts found")

    inserted = 0
    for d in drafts:
        try:
            db.execute("""
                INSERT INTO SHIFTS (USER_ID, LOCATION_ID, SHIFT_DATE, START_TIME, END_TIME, POSITION_ID, HOURS_SCHEDULED, CREATED_BY, NOTES)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, [d["USER_ID"], d["LOCATION_ID"], d["SHIFT_DATE"], d["START_TIME"], d["END_TIME"],
                  d["POSITION_ID"], d["HOURS_SCHEDULED"], user.user_id, f"AI-generated (batch {batch_id})"])
            inserted += 1
        except Exception as e:
            logger.error(f"Failed to insert approved shift: {e}")

    # Mark drafts as approved
    db.execute("""
        UPDATE DRAFT_SCHEDULES SET STATUS = 'APPROVED', APPROVED_BY = %s, APPROVED_AT = CURRENT_TIMESTAMP()
        WHERE BATCH_ID = %s
    """, [user.user_id, batch_id])

    return {"message": f"Approved {inserted} shifts", "shifts_created": inserted}


@router.delete("/drafts/{batch_id}")
async def discard_draft_schedule(
    batch_id: str,
    user: AuthenticatedUser = Depends(require_manager),
    db: SnowflakeSession = Depends(get_db),
):
    """Discard a draft batch."""
    db.execute("UPDATE DRAFT_SCHEDULES SET STATUS = 'REJECTED' WHERE BATCH_ID = %s", [batch_id])
    return {"message": "Draft discarded"}
