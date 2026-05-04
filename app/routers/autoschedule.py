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
    """Build the Claude prompt with prescriptive day-by-day staffing targets."""
    import math

    first = date.fromisoformat(context["first_of_month"])
    last = date.fromisoformat(context["last_of_month"])
    
    # Build mandatory staffing requirements from actual data
    day_names_map = {0: "Sunday", 1: "Monday", 2: "Tuesday", 3: "Wednesday", 4: "Thursday", 5: "Friday", 6: "Saturday"}
    staffing_requirements = {}
    for sl in context.get("staffing_levels", []):
        dow = int(sl.get("DOW", 0))
        required = math.ceil(float(sl.get("AVG_STAFF_PER_DAY", 3)))
        # Cap at 5 stylists max — that's the full team
        if required > 5:
            required = 5
        staffing_requirements[dow] = required
    
    # Build day-by-day schedule with exact targets
    schedule_spec = ""
    d = first
    total_days = 0
    while d <= last:
        dow_py = d.weekday()  # Python: 0=Mon, 6=Sun
        sf_dow = (dow_py + 1) % 7  # Snowflake: 0=Sun, 1=Mon, ..., 6=Sat
        target = staffing_requirements.get(sf_dow, 3)
        
        if sf_dow == 6:  # Saturday
            times = "08:50:00 to 17:00:00"
        elif sf_dow == 0:  # Sunday
            times = "11:50:00 to 17:00:00"
        else:
            times = "09:50:00 to 18:00:00"
        
        closed = any(str(c.get("CLOSED_DATE", "")) == str(d) for c in context.get("closed_dates", []))
        if closed:
            schedule_spec += f"  {d} ({d.strftime('%A')}): CLOSED\n"
        else:
            schedule_spec += f"  {d} ({d.strftime('%A')}): EXACTLY {target} stylists, shift {times}\n"
        
        d += timedelta(days=1)
        total_days += 1

    # Receptionist rules
    has_receptionist = context.get("has_receptionist", False)
    if has_receptionist:
        recept_rules = """RECEPTIONIST RULES:
- ALSO schedule 1 Receptionist on Monday, Thursday, Friday, Saturday, and Sunday (IN ADDITION to stylists above)
- Do NOT schedule a Receptionist on Tuesday or Wednesday
- Sally Olivas is Receptionist ONLY
- Kaitlin Hoover can work as Stylist OR Receptionist — if scheduled as Receptionist, she does NOT count toward the stylist number"""
    else:
        recept_rules = "NO Receptionist at this location. Only schedule Stylist shifts."

    # Employee list with hours targets
    emp_lines = ""
    for emp in context["employees"]:
        et = emp.get("EMPLOYMENT_TYPE", "FULL_TIME")
        pos = emp.get("POSITIONS", "Stylist")
        if et == "FULL_TIME":
            emp_lines += f"  user_id={emp['USER_ID']}, {emp['DISPLAY_NAME']}, {pos}, FULL_TIME → 35-37 hrs/week (4-5 shifts)\n"
        else:
            emp_lines += f"  user_id={emp['USER_ID']}, {emp['DISPLAY_NAME']}, {pos}, PART_TIME → 16-24 hrs/week (2-3 shifts)\n"

    prompt = f"""Generate a JSON schedule for {location_name}. Respond with ONLY a JSON array — no other text.

EMPLOYEES:
{emp_lines}

MANDATORY DAILY STAFFING (from actual sales data — DO NOT CHANGE THESE NUMBERS):
{schedule_spec}

{recept_rules}

HOURS PER SHIFT: weekday=8.17h, saturday=8.17h, sunday=5.17h

RULES:
- FULL_TIME: 35-37 hours/week. Best pattern: 3 weekdays + 1 saturday + 1 sunday = 29.68h TOO LOW. Try 4 weekdays + 1 sunday = 37.85h OVER. So use 4 weekdays only = 32.68h, or 3 weekdays + 1 saturday = 32.68h + add sunday some weeks.
- Actually the BEST full-time pattern: 4 weekdays (32.68h) + rotate weekend shifts. Some weeks add 1 sunday (5.17h) = 37.85h which is slightly over. So target 4 weekdays per week = 32.68h and add 1 sunday every other week.
- PART_TIME: 2-3 shifts/week, 16-24 hours
- Audrey McDonald: MAX 3 consecutive days, then 1 day off
- Every employee: at least 1 Saturday off and 1 Sunday off per month
- NEVER exceed 37 hours in any week for any employee

WORK PATTERNS (who typically works which days):
{json.dumps(context.get('employee_patterns', []), indent=2, default=str)}

TIME OFF:
{json.dumps(context.get('time_off', []), indent=2, default=str)}

OUTPUT: JSON array only. Each element:
{{"user_id":123,"shift_date":"YYYY-MM-DD","start_time":"HH:MM:SS","end_time":"HH:MM:SS","position":"Stylist","reasoning":"brief"}}

Generate ALL {total_days} days. Do not stop early."""

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
        async with httpx.AsyncClient(timeout=httpx.Timeout(connect=30.0, read=300.0, write=30.0, pool=30.0)) as client:
            response = await client.post(
                CLAUDE_API,
                headers={
                    "Content-Type": "application/json",
                    "x-api-key": settings.anthropic_api_key,
                    "anthropic-version": "2023-06-01",
                },
                json={
                    "model": CLAUDE_MODEL,
                    "max_tokens": 32000,
                    "system": "You are a JSON API. Respond with ONLY a raw JSON array. No explanation, no markdown fencing, no thinking. Your entire response must be valid JSON starting with [ and ending with ].",
                    "messages": [
                        {"role": "user", "content": prompt}
                    ],
                },
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
        ai_text = ai_text.strip()
        
        # Remove markdown fencing if present
        if ai_text.startswith("```"):
            ai_text = ai_text.split("\n", 1)[1] if "\n" in ai_text else ai_text[3:]
            if ai_text.endswith("```"):
                ai_text = ai_text[:-3]
            ai_text = ai_text.strip()
        
        # Find the JSON array in the response
        bracket_start = ai_text.find("[")
        bracket_end = ai_text.rfind("]")
        if bracket_start != -1 and bracket_end != -1 and bracket_end > bracket_start:
            ai_text = ai_text[bracket_start:bracket_end + 1]
        
        # Handle double brackets [[...]] — flatten to single array
        if ai_text.startswith("[["):
            ai_text = ai_text[1:]
            if ai_text.endswith("]]"):
                ai_text = ai_text[:-1]
        
        # If response was truncated (no closing bracket), try to fix it
        if not ai_text.rstrip().endswith("]"):
            # Find the last complete JSON object (ends with })
            last_brace = ai_text.rfind("}")
            if last_brace != -1:
                ai_text = ai_text[:last_brace + 1] + "]"
                logger.warning(f"AI response was truncated, salvaged up to last complete shift")
        
        logger.info(f"Parsing JSON response: {len(ai_text)} chars")
        shifts = json.loads(ai_text)
        logger.info(f"Parsed {len(shifts)} shifts from AI response")
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
