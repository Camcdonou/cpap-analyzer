"""Pydantic schemas for API request/response models."""

from datetime import date, datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


# ── Upload ────────────────────────────────────────────────────────────────
class UploadResponse(BaseModel):
    upload_id: str
    status: str
    num_sessions: int = 0
    device_info: dict = {}
    error_message: Optional[str] = None


class UploadStatus(BaseModel):
    upload_id: str
    status: str
    num_sessions: int = 0
    errors: List[str] = []
    warnings: List[str] = []


# ── Night Session ─────────────────────────────────────────────────────────
class NightSessionSummary(BaseModel):
    """Summary for the session list view."""
    id: int
    session_date: date
    duration_hours: float
    ahi: float
    oai: float
    cai: float
    hi: float
    leak_95: float
    pressure_95: float
    event_counts: Dict[str, int] = {}

    class Config:
        from_attributes = True


class NightSessionDetail(BaseModel):
    """Full session detail."""
    id: int
    session_date: date
    duration_hours: float
    mask_on_seconds: float = 0.0
    mask_off_seconds: float = 0.0
    ahi: float
    oai: float
    cai: float
    hi: float
    leak_50: float = 0.0
    leak_95: float = 0.0
    leak_max: float = 0.0
    pressure_50: float = 0.0
    pressure_95: float = 0.0
    pressure_max: float = 0.0
    epap_95: float = 0.0
    rr_50: float = 0.0
    mv_50: float = 0.0
    tv_50: float = 0.0
    set_pressure: float = 0.0
    min_pressure: float = 0.0
    max_pressure: float = 0.0
    epr_level: int = 0
    csr_percent: float = 0.0
    event_counts: Dict[str, int] = {}
    source_files: Dict[str, str] = {}
    device_info: dict = {}
    settings_info: dict = {}

    class Config:
        from_attributes = True


# ── Events ────────────────────────────────────────────────────────────────
class EventResponse(BaseModel):
    id: int
    session_id: int
    event_type: str
    onset_seconds: float
    duration_seconds: float
    raw_text: str = ""

    class Config:
        from_attributes = True


# ── Signal Data ───────────────────────────────────────────────────────────
class SignalDataResponse(BaseModel):
    signal_name: str
    sampling_rate: float
    unit: str
    values: List[float] = []
    # Optional downsampled versions
    values_1min: Optional[List[float]] = None
    values_5min: Optional[List[float]] = None


# ── Trends ────────────────────────────────────────────────────────────────
class TrendDataPoint(BaseModel):
    date: date
    ahi: float
    oai: float = 0.0
    cai: float = 0.0
    hi: float = 0.0
    leak_95: float = 0.0
    pressure_95: float = 0.0
    duration_hours: float = 0.0
    event_counts: Dict[str, int] = {}


class TrendResponse(BaseModel):
    metric: str
    data: List[TrendDataPoint]


# ── AI ────────────────────────────────────────────────────────────────────
class ReportRequest(BaseModel):
    session_id: Optional[int] = None
    upload_id: Optional[str] = None
    report_type: str = "nightly"  # nightly, trend, custom
    focus_areas: List[str] = Field(default_factory=lambda: ["events", "leak", "pressure"])


class ReportResponse(BaseModel):
    id: int
    session_id: Optional[int] = None
    report_type: str
    summary_text: str
    key_findings: List[str] = []
    recommendations: List[str] = []
    model_version: str = ""


class QuestionRequest(BaseModel):
    question: str
    context_session_ids: List[int] = []


class QuestionResponse(BaseModel):
    answer: str
    sources: List[str] = []
