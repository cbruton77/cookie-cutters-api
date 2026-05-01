from fastapi import APIRouter, Depends, HTTPException
from app.db import get_db, SnowflakeSession
from app.auth import get_current_user, require_manager, AuthenticatedUser
from app.models.shifts import ShiftCreate, ShiftUpdate, ShiftMove, ShiftOut
from datetime import date, timedelta

router = APIRouter(prefix="/api/scheduling/shifts", tags=["Shifts"])


@router.get("", response_model=list[ShiftOut])
async def get_weekly_shifts(
    week_start: date,
    location_id: str | None = None,
    user: AuthenticatedUser = Depends(get_current_user),
    db: SnowflakeSession = Depends(get_db),
):
    """
    Get all shifts for a given week.
    Non-managers only see their own location.
    """
    week_end = week_start + timedelta(days=6)

    if not user.is_manager:
        location_id = user.location_id

    query = """
        SELECT s.SHIFT_ID, s.USER_ID, u.DISPLAY_NAME, u.AVATAR_INITIALS,
               CAST(s.LOCATION_ID AS VARCHAR) AS LOCATION_ID, l.LOCATION_NAME, s.SHIFT_DATE,
               TO_CHAR(s.START_TIME, 'HH12:MI AM') AS START_TIME,
               TO_CHAR(s.END_TIME, 'HH12:MI AM') AS END_TIME,
               TIMEDIFF(MINUTE, s.START_TIME, s.END_TIME) / 60.0 AS HOURS_SCHEDULED,
               p.POSITION_NAME, s.NOTES
        FROM SHIFTS s
        JOIN USERS u ON s.USER_ID = u.USER_ID
        JOIN LOCATIONS l ON s.LOCATION_ID = l.LOCATION_ID
        JOIN POSITIONS p ON s.POSITION_ID = p.POSITION_ID
        WHERE s.SHIFT_DATE BETWEEN %s AND %s
          AND u.IS_ACTIVE = TRUE
    """
    params = [week_start, week_end]

    if location_id:
        query += " AND s.LOCATION_ID = %s"
        params.append(location_id)

    query += " ORDER BY s.SHIFT_DATE, u.DISPLAY_NAME"

    rows = db.execute_all(query, params)
    return [
        ShiftOut(
            shift_id=r["SHIFT_ID"],
            user_id=r["USER_ID"],
            display_name=r["DISPLAY_NAME"],
            avatar_initials=r["AVATAR_INITIALS"],
            location_id=r["LOCATION_ID"],
            location_name=r["LOCATION_NAME"],
            shift_date=r["SHIFT_DATE"],
            start_time=r["START_TIME"],
            end_time=r["END_TIME"],
            hours_scheduled=round(float(r["HOURS_SCHEDULED"]), 2),
            position_name=r["POSITION_NAME"],
            notes=r.get("NOTES"),
        )
        for r in rows
    ]


@router.post("", response_model=dict)
async def create_shift(
    data: ShiftCreate,
    user: AuthenticatedUser = Depends(require_manager),
    db: SnowflakeSession = Depends(get_db),
):
    """Create a new shift. Manager only."""
    # Check for duplicate
    existing = db.execute_one(
        "SELECT SHIFT_ID FROM SHIFTS WHERE USER_ID = %s AND SHIFT_DATE = %s",
        [data.user_id, data.shift_date]
    )
    if existing:
        raise HTTPException(409, "This employee already has a shift on this date")

    # Check for closed date
    closed = db.execute_one(
        "SELECT CLOSED_DATE_ID FROM CLOSED_DATES WHERE CLOSED_DATE = %s",
        [data.shift_date]
    )
    if closed:
        raise HTTPException(400, "Cannot schedule a shift on a closed date")

    hours = (data.end_time.hour * 60 + data.end_time.minute -
             data.start_time.hour * 60 - data.start_time.minute) / 60.0

    db.execute("""
        INSERT INTO SHIFTS (USER_ID, LOCATION_ID, SHIFT_DATE, START_TIME, END_TIME,
                           POSITION_ID, HOURS_SCHEDULED, NOTES, CREATED_BY)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    """, [data.user_id, data.location_id, data.shift_date,
          data.start_time.isoformat(), data.end_time.isoformat(),
          data.position_id, round(hours, 2), data.notes, user.user_id])

    return {"message": "Shift created"}


@router.put("/{shift_id}", response_model=dict)
async def update_shift(
    shift_id: int,
    data: ShiftUpdate,
    user: AuthenticatedUser = Depends(require_manager),
    db: SnowflakeSession = Depends(get_db),
):
    """Update a shift's times or role. Manager only."""
    updates = []
    params = []

    if data.start_time is not None:
        updates.append("START_TIME = %s")
        params.append(data.start_time.isoformat())

    if data.end_time is not None:
        updates.append("END_TIME = %s")
        params.append(data.end_time.isoformat())

    if data.position_id is not None:
        updates.append("POSITION_ID = %s")
        params.append(data.position_id)

    if data.notes is not None:
        updates.append("NOTES = %s")
        params.append(data.notes)

    if updates:
        # Recalculate hours if times changed
        updates.append("UPDATED_AT = CURRENT_TIMESTAMP()")
        updates.append("HOURS_SCHEDULED = TIMEDIFF(MINUTE, START_TIME, END_TIME) / 60.0")
        params.append(shift_id)
        db.execute(
            f"UPDATE SHIFTS SET {', '.join(updates)} WHERE SHIFT_ID = %s",
            params
        )

    return {"message": "Shift updated"}


@router.put("/{shift_id}/move", response_model=dict)
async def move_shift(
    shift_id: int,
    data: ShiftMove,
    user: AuthenticatedUser = Depends(require_manager),
    db: SnowflakeSession = Depends(get_db),
):
    """Move a shift to a different date (drag-and-drop). Manager only."""
    # Get the shift's user to check for conflicts
    shift = db.execute_one("SELECT USER_ID FROM SHIFTS WHERE SHIFT_ID = %s", [shift_id])
    if not shift:
        raise HTTPException(404, "Shift not found")

    # Check for existing shift on target date
    existing = db.execute_one(
        "SELECT SHIFT_ID FROM SHIFTS WHERE USER_ID = %s AND SHIFT_DATE = %s",
        [shift["USER_ID"], data.new_date]
    )
    if existing:
        # Swap the dates
        db.execute(
            "UPDATE SHIFTS SET SHIFT_DATE = %s, UPDATED_AT = CURRENT_TIMESTAMP() WHERE SHIFT_ID = %s",
            [data.new_date, shift_id]
        )
        original = db.execute_one("SELECT SHIFT_DATE FROM SHIFTS WHERE SHIFT_ID = %s", [shift_id])
        db.execute(
            "UPDATE SHIFTS SET SHIFT_DATE = (SELECT SHIFT_DATE FROM SHIFTS WHERE SHIFT_ID = %s), UPDATED_AT = CURRENT_TIMESTAMP() WHERE SHIFT_ID = %s",
            [shift_id, existing["SHIFT_ID"]]
        )
    else:
        db.execute(
            "UPDATE SHIFTS SET SHIFT_DATE = %s, UPDATED_AT = CURRENT_TIMESTAMP() WHERE SHIFT_ID = %s",
            [data.new_date, shift_id]
        )

    return {"message": "Shift moved"}


@router.delete("/{shift_id}", response_model=dict)
async def delete_shift(
    shift_id: int,
    user: AuthenticatedUser = Depends(require_manager),
    db: SnowflakeSession = Depends(get_db),
):
    """Delete a shift. Manager only."""
    db.execute("DELETE FROM SHIFTS WHERE SHIFT_ID = %s", [shift_id])
    return {"message": "Shift deleted"}
