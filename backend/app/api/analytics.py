"""Analytics API routes — trends and aggregate statistics."""

from datetime import date, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models.database import NightSession, Upload, Event
from ..models.schemas import TrendDataPoint, TrendResponse

router = APIRouter()


def get_db(request: Request):
    factory = request.app.state.db_session_factory
    session = factory()
    try:
        yield session
    finally:
        session.close()


@router.get("/trends", response_model=TrendResponse)
async def get_trends(
    request: Request,
    upload_id: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    db: Session = Depends(get_db),
):
    """Get trend data across all sessions."""
    query = db.query(NightSession)

    if upload_id:
        query = query.filter(NightSession.upload_id == upload_id)
    if start_date:
        query = query.filter(NightSession.session_date >= start_date)
    if end_date:
        query = query.filter(NightSession.session_date <= end_date)

    sessions = query.order_by(NightSession.session_date).all()

    data = []
    for s in sessions:
        data.append(TrendDataPoint(
            date=s.session_date,
            ahi=s.ahi,
            oai=s.oai,
            cai=s.cai,
            hi=s.hi,
            leak_95=s.leak_95,
            pressure_95=s.pressure_95,
            duration_hours=s.duration_hours,
            event_counts=s.event_counts or {},
        ))

    return TrendResponse(metric="all", data=data)


@router.get("/overview")
async def get_overview(
    request: Request,
    upload_id: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Get overview statistics across all sessions."""
    query = db.query(NightSession)
    if upload_id:
        query = query.filter(NightSession.upload_id == upload_id)

    sessions = query.all()
    if not sessions:
        return {"num_sessions": 0}

    ahi_values = [s.ahi for s in sessions if s.ahi > 0]
    leak_values = [s.leak_95 for s in sessions if s.leak_95 > 0]
    duration_values = [s.duration_hours for s in sessions if s.duration_hours > 0]

    # Calculate compliance (≥4 hours of use)
    compliant = sum(1 for d in duration_values if d >= 4.0)

    # AHI classification
    def classify_ahi(ahi: float) -> str:
        if ahi < 5:
            return "normal"
        elif ahi < 15:
            return "mild"
        elif ahi < 30:
            return "moderate"
        return "severe"

    ahi_classes = [classify_ahi(a) for a in ahi_values] if ahi_values else []

    # Aggregate event counts
    total_events = {}
    for s in sessions:
        if s.event_counts:
            for etype, count in s.event_counts.items():
                total_events[etype] = total_events.get(etype, 0) + count

    import numpy as np

    return {
        "num_sessions": len(sessions),
        "date_range": {
            "first": str(min(s.session_date for s in sessions)),
            "last": str(max(s.session_date for s in sessions)),
        },
        "avg_ahi": float(np.mean(ahi_values)) if ahi_values else 0.0,
        "median_ahi": float(np.median(ahi_values)) if ahi_values else 0.0,
        "ahi_classification": {
            "normal": ahi_classes.count("normal"),
            "mild": ahi_classes.count("mild"),
            "moderate": ahi_classes.count("moderate"),
            "severe": ahi_classes.count("severe"),
        },
        "avg_duration_hours": float(np.mean(duration_values)) if duration_values else 0.0,
        "compliance_rate": compliant / len(duration_values) if duration_values else 0.0,
        "avg_leak_95": float(np.mean(leak_values)) if leak_values else 0.0,
        "high_leak_nights": sum(1 for l in leak_values if l > 24.0),
        "total_events": total_events,
    }
