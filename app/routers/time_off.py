from fastapi import APIRouter, Depends, HTTPException
from app.db import get_db, SnowflakeSession
from app.auth import get_current_user, require_manager, AuthenticatedUser
from app.models.time_off import TimeOffCreate, TimeOffReview, TimeOffOut

router = APIRouter(prefix="/api/scheduling/time-off", tags=["Time Off"])


@router.get("", response_model=list[TimeOffOut])
async def list_time_off(
    status: str | None = None,
    location_id: str | None = None,
    user: AuthenticatedUser = Depends(get_current_user),
    db: SnowflakeSession = Depends(get_db),
):
    """List time-off requests. Non-managers see only their own."""
    query = """
        SELECT tor.REQUEST_ID, tor.USER_ID, u.DISPLAY_NAME, l.LOCATION_NAME,
               tor.START_DATE, tor.END_DATE, tor.REASON, tor.NOTES, tor.STATUS,
               r.DISPLAY_NAME AS REVIEWED_BY, tor.CREATED_AT
        FROM TIME_OFF_REQUESTS tor
        JOIN USERS u ON tor.USER_ID = u.USER_ID
        JOIN LOCATIONS l ON u.LOCATION_ID = l.LOCATION_ID
        LEFT JOIN USERS r ON tor.REVIEWED_BY = r.USER_ID
        WHERE 1=1
    """
    params = []

    if not user.is_manager:
        query += " AND tor.USER_ID = %s"
        params.append(user.user_id)
    elif location_id:
        query += " AND u.LOCATION_ID = %s"
        params.append(location_id)

    if status:
        query += " AND tor.STATUS = %s"
        params.append(status.upper())

    query += " ORDER BY tor.CREATED_AT DESC"
    rows = db.execute_all(query, params)

    return [
        TimeOffOut(
            request_id=r["REQUEST_ID"], user_id=r["USER_ID"],
            display_name=r["DISPLAY_NAME"], location_name=r["LOCATION_NAME"],
            start_date=r["START_DATE"], end_date=r["END_DATE"],
            reason=r["REASON"], notes=r.get("NOTES"), status=r["STATUS"],
            reviewed_by=r.get("REVIEWED_BY"), created_at=str(r["CREATED_AT"]),
        ) for r in rows
    ]


@router.post("", response_model=dict)
async def create_time_off(
    data: TimeOffCreate,
    user: AuthenticatedUser = Depends(get_current_user),
    db: SnowflakeSession = Depends(get_db),
):
    """Submit a time-off request. Enforces blackout dates."""
    # Check for blackout periods
    blackout = db.execute_one("""
        SELECT LABEL FROM BLACKOUT_PERIODS
        WHERE %s <= END_DATE AND %s >= START_DATE
    """, [data.start_date, data.end_date])

    if blackout:
        raise HTTPException(
            400,
            f"Cannot request time off — blocked by: {blackout['LABEL']}"
        )

    # Check for closed dates (no need to request off on a closed day)
    closed = db.execute_one("""
        SELECT LABEL FROM CLOSED_DATES
        WHERE CLOSED_DATE BETWEEN %s AND %s
    """, [data.start_date, data.end_date])

    db.execute("""
        INSERT INTO TIME_OFF_REQUESTS (USER_ID, START_DATE, END_DATE, REASON, NOTES)
        VALUES (%s, %s, %s, %s, %s)
    """, [user.user_id, data.start_date, data.end_date, data.reason, data.notes])

    return {"message": "Time-off request submitted"}


@router.put("/{request_id}", response_model=dict)
async def review_time_off(
    request_id: int,
    data: TimeOffReview,
    user: AuthenticatedUser = Depends(require_manager),
    db: SnowflakeSession = Depends(get_db),
):
    """Approve or deny a time-off request. Manager only."""
    if data.status.upper() not in ("APPROVED", "DENIED"):
        raise HTTPException(400, "Status must be APPROVED or DENIED")

    db.execute("""
        UPDATE TIME_OFF_REQUESTS
        SET STATUS = %s, REVIEWED_BY = %s, REVIEWED_AT = CURRENT_TIMESTAMP(),
            UPDATED_AT = CURRENT_TIMESTAMP()
        WHERE REQUEST_ID = %s
    """, [data.status.upper(), user.user_id, request_id])

    return {"message": f"Request {data.status.lower()}"}
