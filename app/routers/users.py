from fastapi import APIRouter, Depends, HTTPException
from app.db import get_db, SnowflakeSession
from app.auth import get_current_user, require_manager, AuthenticatedUser
from app.models.users import UserCreate, UserUpdate, UserOut

router = APIRouter(prefix="/api/scheduling/users", tags=["Users"])


@router.get("", response_model=list[UserOut])
async def list_users(
    location_id: str | None = None,
    user: AuthenticatedUser = Depends(get_current_user),
    db: SnowflakeSession = Depends(get_db),
):
    """List all active users. Non-managers only see their own location."""
    if not user.is_manager and location_id and not user.can_access_location(location_id):
        raise HTTPException(403, "You can only view your own location")

    effective_location = location_id if user.is_manager else user.location_id

    query = """
        SELECT u.USER_ID, u.FIRST_NAME, u.LAST_NAME, u.DISPLAY_NAME,
               u.EMAIL, u.AVATAR_INITIALS, CAST(u.LOCATION_ID AS VARCHAR) AS LOCATION_ID, l.LOCATION_NAME,
               u.IS_MANAGER, u.IS_ADMIN, u.IS_ACTIVE,
               LISTAGG(p.POSITION_NAME, ',') WITHIN GROUP (ORDER BY p.POSITION_NAME) AS POSITIONS
        FROM USERS u
        JOIN LOCATIONS l ON u.LOCATION_ID = l.LOCATION_ID
        LEFT JOIN USER_POSITIONS up ON u.USER_ID = up.USER_ID
        LEFT JOIN POSITIONS p ON up.POSITION_ID = p.POSITION_ID
        WHERE u.IS_ACTIVE = TRUE
    """
    params = []
    if effective_location:
        query += " AND u.LOCATION_ID = %s"
        params.append(effective_location)

    query += " GROUP BY u.USER_ID, u.FIRST_NAME, u.LAST_NAME, u.DISPLAY_NAME, u.EMAIL, u.AVATAR_INITIALS, u.LOCATION_ID, l.LOCATION_NAME, u.IS_MANAGER, u.IS_ADMIN, u.IS_ACTIVE"
    query += " ORDER BY u.DISPLAY_NAME"

    rows = db.execute_all(query, params)
    return [
        UserOut(
            user_id=r["USER_ID"],
            first_name=r["FIRST_NAME"],
            last_name=r["LAST_NAME"],
            display_name=r["DISPLAY_NAME"],
            email=r.get("EMAIL"),
            avatar_initials=r["AVATAR_INITIALS"],
            location_id=r["LOCATION_ID"],
            location_name=r["LOCATION_NAME"],
            is_manager=r["IS_MANAGER"],
            is_admin=r.get("IS_ADMIN") or False,
            positions=r["POSITIONS"].split(",") if r.get("POSITIONS") else [],
            is_active=r["IS_ACTIVE"],
        )
        for r in rows
    ]


@router.post("", response_model=dict)
async def create_user(
    data: UserCreate,
    user: AuthenticatedUser = Depends(require_manager),
    db: SnowflakeSession = Depends(get_db),
):
    """Create a new team member. Manager only."""
    display_name = f"{data.first_name} {data.last_name[0]}."
    avatar = f"{data.first_name[0]}{data.last_name[0]}".upper()

    db.execute("""
        INSERT INTO USERS (FIRST_NAME, LAST_NAME, DISPLAY_NAME, EMAIL, PHONE,
                          AVATAR_INITIALS, LOCATION_ID, IS_MANAGER)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """, [data.first_name, data.last_name, display_name, data.email,
          data.phone, avatar, data.location_id, data.is_manager])

    new_user = db.execute_one(
        "SELECT MAX(USER_ID) AS USER_ID FROM USERS WHERE DISPLAY_NAME = %s",
        [display_name]
    )
    new_id = new_user["USER_ID"]

    # Assign positions
    for pos_name in data.positions:
        pos = db.execute_one(
            "SELECT POSITION_ID FROM POSITIONS WHERE POSITION_NAME = %s",
            [pos_name]
        )
        if pos:
            db.execute(
                "INSERT INTO USER_POSITIONS (USER_ID, POSITION_ID) VALUES (%s, %s)",
                [new_id, pos["POSITION_ID"]]
            )

    return {"user_id": new_id, "display_name": display_name, "message": "User created"}


@router.put("/{user_id}", response_model=dict)
async def update_user(
    user_id: int,
    data: UserUpdate,
    user: AuthenticatedUser = Depends(require_manager),
    db: SnowflakeSession = Depends(get_db),
):
    """Update a team member. Manager only."""
    updates = []
    params = []

    if data.first_name and data.last_name:
        display_name = f"{data.first_name} {data.last_name[0]}."
        avatar = f"{data.first_name[0]}{data.last_name[0]}".upper()
        updates.extend(["FIRST_NAME = %s", "LAST_NAME = %s",
                        "DISPLAY_NAME = %s", "AVATAR_INITIALS = %s"])
        params.extend([data.first_name, data.last_name, display_name, avatar])

    if data.email is not None:
        updates.append("EMAIL = %s")
        params.append(data.email)

    if data.location_id is not None:
        updates.append("LOCATION_ID = %s")
        params.append(data.location_id)

    if updates:
        updates.append("UPDATED_AT = CURRENT_TIMESTAMP()")
        params.append(user_id)
        db.execute(
            f"UPDATE USERS SET {', '.join(updates)} WHERE USER_ID = %s",
            params
        )

    # Update positions if provided
    if data.positions is not None:
        db.execute("DELETE FROM USER_POSITIONS WHERE USER_ID = %s", [user_id])
        for pos_name in data.positions:
            pos = db.execute_one(
                "SELECT POSITION_ID FROM POSITIONS WHERE POSITION_NAME = %s",
                [pos_name]
            )
            if pos:
                db.execute(
                    "INSERT INTO USER_POSITIONS (USER_ID, POSITION_ID) VALUES (%s, %s)",
                    [user_id, pos["POSITION_ID"]]
                )

    return {"message": "User updated"}


@router.delete("/{user_id}", response_model=dict)
async def deactivate_user(
    user_id: int,
    user: AuthenticatedUser = Depends(require_manager),
    db: SnowflakeSession = Depends(get_db),
):
    """Soft-delete a team member (sets IS_ACTIVE = FALSE). Manager only."""
    db.execute(
        "UPDATE USERS SET IS_ACTIVE = FALSE, UPDATED_AT = CURRENT_TIMESTAMP() WHERE USER_ID = %s",
        [user_id]
    )
    return {"message": "User deactivated"}
