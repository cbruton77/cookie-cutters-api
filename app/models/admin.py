from pydantic import BaseModel
from datetime import date, time


# Shift Templates
class TemplateCreate(BaseModel):
    template_name: str
    start_time: time
    end_time: time
    location_id: str | None = None  # None = all locations


class TemplateUpdate(BaseModel):
    template_name: str | None = None
    start_time: time | None = None
    end_time: time | None = None


class TemplateOut(BaseModel):
    template_id: int
    template_name: str
    start_time: str
    end_time: str
    hours_scheduled: float
    is_active: bool


# Closed Dates
class ClosedDateCreate(BaseModel):
    closed_date: date
    label: str
    location_id: str | None = None  # None = all locations


class ClosedDateOut(BaseModel):
    closed_date_id: int
    closed_date: date
    label: str
    location_name: str | None = None


# Blackout Periods
class BlackoutCreate(BaseModel):
    start_date: date
    end_date: date
    label: str
    location_id: str | None = None


class BlackoutOut(BaseModel):
    blackout_id: int
    start_date: date
    end_date: date
    label: str
    location_name: str | None = None
