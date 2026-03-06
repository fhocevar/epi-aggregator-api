from datetime import datetime
from pydantic import BaseModel
from typing import Any, Optional

class PageResponse(BaseModel):
    page: int
    size: int
    total_items: int

class BulletinOut(BaseModel):
    id: str
    source_code: str
    external_id: str
    title: str
    published_at: datetime
    url: str | None = None
    summary: str | None = None

class AlertOut(BaseModel):
    id: str
    source_code: str
    disease: str
    geo_level: str
    geo_code: str
    year: int
    epiweek: int
    severity: str
    title: str
    message: str
    created_at: datetime
    evidence: dict | None = None

class CasesWeeklyOut(BaseModel):
    disease: str
    geo_code: str
    year: int
    epiweek: int
    cases: int | None = None

class IndicatorsWeeklyOut(BaseModel):
    disease: str
    geo_code: str
    year: int
    epiweek: int
    incidence: float | None = None
    rt: float | None = None
    alert_level: int | None = None

class IngestionTargetCreate(BaseModel):
    source_code: str = "INFODENGUE"
    geo_code: str
    disease: str
    ey_start: int = 2025
    ey_end: int = 2026
    ew_start: int = 1
    ew_end: int = 53
    enabled: bool = True

class IngestionTargetOut(IngestionTargetCreate):
    id: str

class NotificationTargetCreate(BaseModel):
    target_type: str
    target_url: str
    min_severity: str = "high"
    enabled: bool = True
    disease_filter: dict | None = None
    geo_filter: dict | None = None

class NotificationTargetOut(NotificationTargetCreate):
    id: str
