from fastapi import APIRouter, Depends
from app.db import get_db, SnowflakeSession
from app.auth import require_manager, get_current_user, AuthenticatedUser
from app.models.admin import (
    ClosedDateCreate, ClosedDateOut,
    BlackoutCreate, BlackoutOut,
)

router = APIRouter(prefix="/api/scheduling/admin", tags=["Admin"])


# ===== CLOSED DATES =====

@router.get("/closed-dates", response_model=list[ClosedDateOut])
async def list_closed_dates(
    user: AuthenticatedUser = Depends(get_current_user),
    db: SnowflakeSession = Depends(get_db),
):
    rows = db.execute_all("""
        SELECT cd.CLOSED_DATE_ID, cd.CLOSED_DATE, cd.LABEL,
               l.LOCATION_NAME
        FROM CLOSED_DATES cd
        LEFT JOIN LOCATIONS l ON cd.LOCATION_ID = l.LOCATION_ID
        ORDER BY cd.CLOSED_DATE
    """)
    return [
        ClosedDateOut(
            closed_date_id=r["CLOSED_DATE_ID"], closed_date=r["CLOSED_DATE"],
            label=r["LABEL"], location_name=r.get("LOCATION_NAME"),
        ) for r in rows
    ]


@router.post("/closed-dates", response_model=dict)
async def add_closed_date(
    data: ClosedDateCreate,
    user: AuthenticatedUser = Depends(require_manager),
    db: SnowflakeSession = Depends(get_db),
):
    db.execute("""
        INSERT INTO CLOSED_DATES (CLOSED_DATE, LABEL, LOCATION_ID, CREATED_BY)
        VALUES (%s, %s, %s, %s)
    """, [data.closed_date, data.label, data.location_id, user.user_id])
    return {"message": "Closed date added"}


@router.delete("/closed-dates/{closed_date_id}", response_model=dict)
async def remove_closed_date(
    closed_date_id: int,
    user: AuthenticatedUser = Depends(require_manager),
    db: SnowflakeSession = Depends(get_db),
):
    db.execute("DELETE FROM CLOSED_DATES WHERE CLOSED_DATE_ID = %s", [closed_date_id])
    return {"message": "Closed date removed"}


# ===== BLACKOUT PERIODS =====

@router.get("/blackout-periods", response_model=list[BlackoutOut])
async def list_blackout_periods(
    user: AuthenticatedUser = Depends(get_current_user),
    db: SnowflakeSession = Depends(get_db),
):
    rows = db.execute_all("""
        SELECT bp.BLACKOUT_ID, bp.START_DATE, bp.END_DATE, bp.LABEL,
               l.LOCATION_NAME
        FROM BLACKOUT_PERIODS bp
        LEFT JOIN LOCATIONS l ON bp.LOCATION_ID = l.LOCATION_ID
        ORDER BY bp.START_DATE
    """)
    return [
        BlackoutOut(
            blackout_id=r["BLACKOUT_ID"], start_date=r["START_DATE"],
            end_date=r["END_DATE"], label=r["LABEL"],
            location_name=r.get("LOCATION_NAME"),
        ) for r in rows
    ]


@router.post("/blackout-periods", response_model=dict)
async def add_blackout_period(
    data: BlackoutCreate,
    user: AuthenticatedUser = Depends(require_manager),
    db: SnowflakeSession = Depends(get_db),
):
    db.execute("""
        INSERT INTO BLACKOUT_PERIODS (START_DATE, END_DATE, LABEL, LOCATION_ID, CREATED_BY)
        VALUES (%s, %s, %s, %s, %s)
    """, [data.start_date, data.end_date, data.label, data.location_id, user.user_id])
    return {"message": "Blackout period added"}


@router.delete("/blackout-periods/{blackout_id}", response_model=dict)
async def remove_blackout_period(
    blackout_id: int,
    user: AuthenticatedUser = Depends(require_manager),
    db: SnowflakeSession = Depends(get_db),
):
    db.execute("DELETE FROM BLACKOUT_PERIODS WHERE BLACKOUT_ID = %s", [blackout_id])
    return {"message": "Blackout period removed"}


# ===== ANNOUNCEMENTS =====

@router.get("/announcements")
async def list_announcements(
    user: AuthenticatedUser = Depends(get_current_user),
    db: SnowflakeSession = Depends(get_db),
):
    rows = db.execute_all("""
        SELECT ANNOUNCEMENT_ID, TITLE, BODY, CREATED_AT
        FROM ANNOUNCEMENTS
        WHERE IS_ACTIVE = TRUE
        ORDER BY CREATED_AT DESC
    """)
    return [
        {"announcement_id": r["ANNOUNCEMENT_ID"], "title": r["TITLE"], "body": r["BODY"],
         "created_at": str(r["CREATED_AT"])} for r in rows
    ]


@router.post("/announcements", response_model=dict)
async def add_announcement(
    data: dict,
    user: AuthenticatedUser = Depends(require_manager),
    db: SnowflakeSession = Depends(get_db),
):
    db.execute("""
        INSERT INTO ANNOUNCEMENTS (TITLE, BODY, CREATED_BY)
        VALUES (%s, %s, %s)
    """, [data["title"], data["body"], user.user_id])
    return {"message": "Announcement posted"}


@router.delete("/announcements/{announcement_id}", response_model=dict)
async def remove_announcement(
    announcement_id: int,
    user: AuthenticatedUser = Depends(require_manager),
    db: SnowflakeSession = Depends(get_db),
):
    db.execute("UPDATE ANNOUNCEMENTS SET IS_ACTIVE = FALSE WHERE ANNOUNCEMENT_ID = %s", [announcement_id])
    return {"message": "Announcement removed"}


# ===== LOGIN TRACKING =====

@router.post("/log-login", response_model=dict)
async def log_login(
    data: dict,
    user: AuthenticatedUser = Depends(get_current_user),
    db: SnowflakeSession = Depends(get_db),
):
    db.execute("""
        INSERT INTO USER_LOGIN_LOG (USER_ID, DISPLAY_NAME, IP_ADDRESS, USER_AGENT, DEVICE_TYPE)
        VALUES (%s, %s, %s, %s, %s)
    """, [user.user_id, user.display_name, data.get("ip", ""), data.get("user_agent", ""), data.get("device_type", "")])
    return {"message": "Login logged"}


@router.get("/login-log")
async def get_login_log(
    user: AuthenticatedUser = Depends(require_manager),
    db: SnowflakeSession = Depends(get_db),
):
    rows = db.execute_all("""
        SELECT LOG_ID, USER_ID, DISPLAY_NAME, LOGIN_AT, DEVICE_TYPE
        FROM USER_LOGIN_LOG
        ORDER BY LOGIN_AT DESC
        LIMIT 50
    """)
    return [{"log_id": r["LOG_ID"], "user_id": r["USER_ID"], "display_name": r["DISPLAY_NAME"],
             "login_at": str(r["LOGIN_AT"]), "device_type": r["DEVICE_TYPE"]} for r in rows]


# ===== BUSINESS HOURS =====

@router.get("/business-hours")
async def get_business_hours(
    location_id: str | None = None,
    user: AuthenticatedUser = Depends(get_current_user),
    db: SnowflakeSession = Depends(get_db),
):
    query = """
        SELECT bh.HOURS_ID, CAST(bh.LOCATION_ID AS VARCHAR) AS LOCATION_ID, l.LOCATION_NAME,
               bh.DAY_OF_WEEK, bh.DAY_NAME,
               TO_CHAR(bh.OPEN_TIME, 'HH12:MI AM') AS OPEN_TIME,
               TO_CHAR(bh.CLOSE_TIME, 'HH12:MI AM') AS CLOSE_TIME,
               bh.IS_OPEN, bh.SHIFT_START_OFFSET
        FROM BUSINESS_HOURS bh
        JOIN LOCATIONS l ON bh.LOCATION_ID = l.LOCATION_ID
    """
    params = []
    if location_id:
        query += " WHERE bh.LOCATION_ID = %s"
        params.append(location_id)
    query += " ORDER BY bh.LOCATION_ID, bh.DAY_OF_WEEK"
    rows = db.execute_all(query, params)
    return [dict(r) for r in rows]


@router.put("/business-hours/{hours_id}", response_model=dict)
async def update_business_hours(
    hours_id: int,
    data: dict,
    user: AuthenticatedUser = Depends(require_manager),
    db: SnowflakeSession = Depends(get_db),
):
    updates, params = [], []
    if "open_time" in data:
        updates.append("OPEN_TIME = %s")
        params.append(data["open_time"])
    if "close_time" in data:
        updates.append("CLOSE_TIME = %s")
        params.append(data["close_time"])
    if "is_open" in data:
        updates.append("IS_OPEN = %s")
        params.append(data["is_open"])
    if "shift_start_offset" in data:
        updates.append("SHIFT_START_OFFSET = %s")
        params.append(data["shift_start_offset"])
    if updates:
        updates.append("UPDATED_AT = CURRENT_TIMESTAMP()")
        params.append(hours_id)
        db.execute(f"UPDATE BUSINESS_HOURS SET {', '.join(updates)} WHERE HOURS_ID = %s", params)
    return {"message": "Business hours updated"}


# ===== SCHEDULING RULES =====

@router.get("/scheduling-rules")
async def get_scheduling_rules(
    user: AuthenticatedUser = Depends(get_current_user),
    db: SnowflakeSession = Depends(get_db),
):
    rows = db.execute_all("""
        SELECT sr.RULE_ID, CAST(sr.LOCATION_ID AS VARCHAR) AS LOCATION_ID, sr.USER_ID,
               u.DISPLAY_NAME AS USER_NAME, sr.RULE_TYPE, sr.RULE_NAME,
               sr.RULE_DESCRIPTION, sr.PARAM_1, sr.PARAM_2, sr.IS_ACTIVE
        FROM SCHEDULING_RULES sr
        LEFT JOIN USERS u ON sr.USER_ID = u.USER_ID
        WHERE sr.IS_ACTIVE = TRUE
        ORDER BY sr.RULE_TYPE, sr.RULE_NAME
    """)
    return [dict(r) for r in rows]


@router.post("/scheduling-rules", response_model=dict)
async def add_scheduling_rule(
    data: dict,
    user: AuthenticatedUser = Depends(require_manager),
    db: SnowflakeSession = Depends(get_db),
):
    db.execute("""
        INSERT INTO SCHEDULING_RULES (LOCATION_ID, USER_ID, RULE_TYPE, RULE_NAME, RULE_DESCRIPTION, PARAM_1, PARAM_2, CREATED_BY)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """, [data.get("location_id"), data.get("user_id"), data["rule_type"], data["rule_name"],
          data.get("rule_description", ""), data.get("param_1", ""), data.get("param_2", ""), user.user_id])
    return {"message": "Rule added"}


@router.put("/scheduling-rules/{rule_id}", response_model=dict)
async def update_scheduling_rule(
    rule_id: int,
    data: dict,
    user: AuthenticatedUser = Depends(require_manager),
    db: SnowflakeSession = Depends(get_db),
):
    updates, params = [], []
    for field in ["rule_name", "rule_description", "param_1", "param_2"]:
        if field in data:
            updates.append(f"{field.upper()} = %s")
            params.append(data[field])
    if "user_id" in data:
        updates.append("USER_ID = %s")
        params.append(data["user_id"])
    if updates:
        updates.append("UPDATED_AT = CURRENT_TIMESTAMP()")
        params.append(rule_id)
        db.execute(f"UPDATE SCHEDULING_RULES SET {', '.join(updates)} WHERE RULE_ID = %s", params)
    return {"message": "Rule updated"}


@router.delete("/scheduling-rules/{rule_id}", response_model=dict)
async def remove_scheduling_rule(
    rule_id: int,
    user: AuthenticatedUser = Depends(require_manager),
    db: SnowflakeSession = Depends(get_db),
):
    db.execute("UPDATE SCHEDULING_RULES SET IS_ACTIVE = FALSE WHERE RULE_ID = %s", [rule_id])
    return {"message": "Rule removed"}
