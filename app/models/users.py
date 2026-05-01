from pydantic import BaseModel
from datetime import datetime


class UserBase(BaseModel):
    first_name: str
    last_name: str
    email: str | None = None
    phone: str | None = None
    location_id: str
    is_manager: bool = False


class UserCreate(UserBase):
    positions: list[str]  # ["Stylist", "Receptionist"]


class UserUpdate(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    email: str | None = None
    phone: str | None = None
    location_id: str | None = None
    positions: list[str] | None = None


class UserOut(BaseModel):
    user_id: int
    first_name: str
    last_name: str
    display_name: str
    email: str | None = None
    avatar_initials: str
    location_id: str
    location_name: str
    is_manager: bool
    positions: list[str]
    is_active: bool
