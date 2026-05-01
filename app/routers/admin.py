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
