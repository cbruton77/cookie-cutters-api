from fastapi import APIRouter, Depends
from app.db import get_db, SnowflakeSession
from app.config import get_settings

router = APIRouter(tags=["Health"])


@router.get("/api/health")
async def health_check():
    return {"status": "ok", "service": "cookie-cutters-api"}


@router.get("/api/health/db")
async def db_health(db: SnowflakeSession = Depends(get_db)):
    """Verify Snowflake connectivity."""
    try:
        result = db.execute_scalar("SELECT CURRENT_TIMESTAMP()")
        return {"status": "ok", "snowflake_time": str(result)}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


@router.get("/api/health/env")
async def env_check():
    """Check environment settings (dev only)."""
    settings = get_settings()
    return {
        "app_env": settings.app_env,
        "is_dev": settings.is_dev,
        "debug": settings.app_debug,
    }


@router.get("/api/health/users")
async def test_users(db: SnowflakeSession = Depends(get_db)):
    """Test endpoint — list all users without auth (for debugging only)."""
    rows = db.execute_all("""
        SELECT u.USER_ID, u.DISPLAY_NAME, u.IS_MANAGER, l.LOCATION_NAME
        FROM USERS u
        JOIN LOCATIONS l ON u.LOCATION_ID = l.LOCATION_ID
        WHERE u.IS_ACTIVE = TRUE
        ORDER BY l.LOCATION_NAME, u.DISPLAY_NAME
    """)
    return rows
