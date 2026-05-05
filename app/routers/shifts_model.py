from pydantic import BaseModel
from datetime import date, time


class ShiftCreate(BaseModel):
    user_id: int
    location_id: str
    shift_date: date
    start_time: time
    end_time: time
    position_id: int
    template_id: int | None = None
    notes: str | None = None


class ShiftUpdate(BaseModel):
    start_time: time | None = None
    end_time: time | None = None
    position_id: int | None = None
    notes: str | None = None


class ShiftMove(BaseModel):
    new_date: date


class ShiftOut(BaseModel):
    shift_id: int
    user_id: int
    display_name: str
    avatar_initials: str
    location_id: str
    location_name: str
    shift_date: date
    start_time: str
    end_time: str
    hours_scheduled: float
    position_name: str
    notes: str | None = None
    status: str = "DRAFT"


class WeeklyScheduleRequest(BaseModel):
    week_start: date  # Monday of the week
    location_id: str | None = None  # None = all locations (manager)
