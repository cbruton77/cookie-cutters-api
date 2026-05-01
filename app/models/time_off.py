from pydantic import BaseModel
from datetime import date


class TimeOffCreate(BaseModel):
    start_date: date
    end_date: date
    reason: str
    notes: str | None = None


class TimeOffReview(BaseModel):
    status: str  # "APPROVED" or "DENIED"


class TimeOffOut(BaseModel):
    request_id: int
    user_id: int
    display_name: str
    location_name: str
    start_date: date
    end_date: date
    reason: str
    notes: str | None = None
    status: str
    reviewed_by: str | None = None
    created_at: str
