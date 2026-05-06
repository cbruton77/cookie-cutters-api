"""
Authentication middleware using Supabase JWT tokens.

In production, every request must include a valid JWT token in the
Authorization header. The middleware validates the token and injects
the authenticated user into the request.

In development mode, you can bypass auth for testing by setting
APP_ENV=development in your .env file.
"""

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from app.config import get_settings
from app.db.snowflake import get_db, SnowflakeSession
import logging

logger = logging.getLogger(__name__)
security = HTTPBearer(auto_error=False)


class AuthenticatedUser:
    """Represents the currently authenticated user."""

    def __init__(self, user_id: int, email: str, is_manager: bool,
                 is_admin: bool, location_id: str | None, location_name: str, display_name: str):
        self.user_id = user_id
        self.email = email
        self.is_manager = is_manager
        self.is_admin = is_admin
        self.location_id = location_id
        self.location_name = location_name
        self.display_name = display_name

    def can_access_location(self, location_id: str | None) -> bool:
        """Check if this user can access data for a given location."""
        if self.is_manager:
            return True  # Managers see everything
        return location_id is None or self.location_id == location_id


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: SnowflakeSession = Depends(get_db),
) -> AuthenticatedUser:
    """
    FastAPI dependency that validates the JWT and returns the authenticated user.

    Usage:
        @router.get("/shifts")
        async def get_shifts(user: AuthenticatedUser = Depends(get_current_user)):
            if not user.is_manager:
                raise HTTPException(403, "Managers only")
    """
    settings = get_settings()

    # In development, allow a dev bypass via header or query param
    if settings.is_dev:
        dev_user_id = request.headers.get("x-dev-user-id") or request.query_params.get("dev_user_id")
        if dev_user_id:
            user = db.execute_one("""
                SELECT u.USER_ID, u.EMAIL, u.IS_MANAGER, u.IS_ADMIN, CAST(u.LOCATION_ID AS VARCHAR) AS LOCATION_ID,
                       u.DISPLAY_NAME, l.LOCATION_NAME
                FROM USERS u
                JOIN LOCATIONS l ON u.LOCATION_ID = l.LOCATION_ID
                WHERE u.USER_ID = %s AND u.IS_ACTIVE = TRUE
            """, [int(dev_user_id)])
            if user:
                return AuthenticatedUser(
                    user_id=user["USER_ID"],
                    email=user.get("EMAIL", ""),
                    is_manager=user["IS_MANAGER"],
                    is_admin=user.get("IS_ADMIN") or False,
                    location_id=user["LOCATION_ID"],
                    location_name=user["LOCATION_NAME"],
                    display_name=user["DISPLAY_NAME"],
                )

    if not credentials:
        raise HTTPException(status_code=401, detail="Missing authentication token")

    try:
        # Decode and validate the Supabase JWT
        payload = jwt.decode(
            credentials.credentials,
            settings.supabase_jwt_secret,
            algorithms=["HS256"],
            audience="authenticated",
        )
        supabase_uid = payload.get("sub")
        email = payload.get("email", "")

        if not supabase_uid:
            raise HTTPException(status_code=401, detail="Invalid token payload")

        # Look up the user in our USERS table by email
        user = db.execute_one("""
            SELECT u.USER_ID, u.EMAIL, u.IS_MANAGER, u.IS_ADMIN, CAST(u.LOCATION_ID AS VARCHAR) AS LOCATION_ID,
                   u.DISPLAY_NAME, l.LOCATION_NAME
            FROM USERS u
            JOIN LOCATIONS l ON u.LOCATION_ID = l.LOCATION_ID
            WHERE u.EMAIL = %s AND u.IS_ACTIVE = TRUE
        """, [email])

        if not user:
            raise HTTPException(
                status_code=403,
                detail="Account not found. Contact your manager to be added."
            )

        return AuthenticatedUser(
            user_id=user["USER_ID"],
            email=user["EMAIL"],
            is_manager=user["IS_MANAGER"],
            is_admin=user.get("IS_ADMIN") or False,
            location_id=user["LOCATION_ID"],
            location_name=user["LOCATION_NAME"],
            display_name=user["DISPLAY_NAME"],
        )

    except JWTError as e:
        logger.warning("JWT validation failed: %s", str(e))
        raise HTTPException(status_code=401, detail="Invalid or expired token")


def require_manager(user: AuthenticatedUser = Depends(get_current_user)) -> AuthenticatedUser:
    """Dependency that ensures the user is a manager or admin."""
    if not user.is_manager and not user.is_admin:
        raise HTTPException(status_code=403, detail="Manager access required")
    return user
