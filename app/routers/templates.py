from fastapi import APIRouter, Depends, HTTPException
from app.db import get_db, SnowflakeSession
from app.auth import require_manager, AuthenticatedUser
from app.models.admin import TemplateCreate, TemplateUpdate, TemplateOut

router = APIRouter(prefix="/api/scheduling/templates", tags=["Shift Templates"])


@router.get("", response_model=list[TemplateOut])
async def list_templates(
    user: AuthenticatedUser = Depends(require_manager),
    db: SnowflakeSession = Depends(get_db),
):
    """List all active shift templates."""
    rows = db.execute_all("""
        SELECT TEMPLATE_ID, TEMPLATE_NAME,
               TO_CHAR(START_TIME, 'HH12:MI AM') AS START_TIME,
               TO_CHAR(END_TIME, 'HH12:MI AM') AS END_TIME,
               HOURS_SCHEDULED, IS_ACTIVE
        FROM SHIFT_TEMPLATES
        WHERE IS_ACTIVE = TRUE
        ORDER BY START_TIME
    """)
    return [
        TemplateOut(
            template_id=r["TEMPLATE_ID"], template_name=r["TEMPLATE_NAME"],
            start_time=r["START_TIME"], end_time=r["END_TIME"],
            hours_scheduled=float(r["HOURS_SCHEDULED"]), is_active=r["IS_ACTIVE"],
        ) for r in rows
    ]


@router.post("", response_model=dict)
async def create_template(
    data: TemplateCreate,
    user: AuthenticatedUser = Depends(require_manager),
    db: SnowflakeSession = Depends(get_db),
):
    """Create a new shift template."""
    hours = (data.end_time.hour * 60 + data.end_time.minute -
             data.start_time.hour * 60 - data.start_time.minute) / 60.0
    db.execute("""
        INSERT INTO SHIFT_TEMPLATES (TEMPLATE_NAME, START_TIME, END_TIME, HOURS_SCHEDULED, LOCATION_ID, CREATED_BY)
        VALUES (%s, %s, %s, %s, %s, %s)
    """, [data.template_name, data.start_time.isoformat(), data.end_time.isoformat(),
          round(hours, 2), data.location_id, user.user_id])
    return {"message": "Template created"}


@router.put("/{template_id}", response_model=dict)
async def update_template(
    template_id: int,
    data: TemplateUpdate,
    user: AuthenticatedUser = Depends(require_manager),
    db: SnowflakeSession = Depends(get_db),
):
    """Update a shift template."""
    updates, params = [], []
    if data.template_name: updates.append("TEMPLATE_NAME = %s"); params.append(data.template_name)
    if data.start_time: updates.append("START_TIME = %s"); params.append(data.start_time.isoformat())
    if data.end_time: updates.append("END_TIME = %s"); params.append(data.end_time.isoformat())
    if updates:
        updates.append("UPDATED_AT = CURRENT_TIMESTAMP()")
        params.append(template_id)
        db.execute(f"UPDATE SHIFT_TEMPLATES SET {', '.join(updates)} WHERE TEMPLATE_ID = %s", params)
    return {"message": "Template updated"}


@router.delete("/{template_id}", response_model=dict)
async def delete_template(
    template_id: int,
    user: AuthenticatedUser = Depends(require_manager),
    db: SnowflakeSession = Depends(get_db),
):
    """Soft-delete a shift template."""
    db.execute("UPDATE SHIFT_TEMPLATES SET IS_ACTIVE = FALSE WHERE TEMPLATE_ID = %s", [template_id])
    return {"message": "Template removed"}
