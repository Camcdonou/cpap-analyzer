"""Session API routes — browse and view CPAP session data."""

from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from ..models.database import NightSession, Event, SignalData, Upload
from ..models.schemas import (
    NightSessionSummary,
    NightSessionDetail,
    EventResponse,
    SignalDataResponse,
)

router = APIRouter()


def get_db(request: Request):
    factory = request.app.state.db_session_factory
    session = factory()
    try:
        yield session
    finally:
        session.close()


@router.get("/sessions", response_model=List[NightSessionSummary])
async def list_sessions(
    request: Request,
    upload_id: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    db: Session = Depends(get_db),
):
    """List all night sessions with optional filtering."""
    query = db.query(NightSession)

    if upload_id:
        query = query.filter(NightSession.upload_id == upload_id)
    if start_date:
        query = query.filter(NightSession.session_date >= start_date)
    if end_date:
        query = query.filter(NightSession.session_date <= end_date)

    sessions = query.order_by(NightSession.session_date.desc()).all()
    return sessions


@router.get("/sessions/{session_id}", response_model=NightSessionDetail)
async def get_session(
    session_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    """Get detailed session data."""
    session = db.query(NightSession).filter(NightSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Enrich with device info from upload
    upload = db.query(Upload).filter(Upload.id == session.upload_id).first()

    result = NightSessionDetail.model_validate(session)
    if upload:
        result.device_info = upload.device_info or {}
        result.settings_info = upload.settings_info or {}

    return result


@router.get("/sessions/{session_id}/events", response_model=List[EventResponse])
async def get_events(
    session_id: int,
    event_type: Optional[str] = None,
    request: Request = None,
    db: Session = Depends(get_db),
):
    """Get sleep events for a session."""
    query = db.query(Event).filter(Event.session_id == session_id)
    if event_type:
        query = query.filter(Event.event_type == event_type)
    return query.order_by(Event.onset_seconds).all()


@router.get("/sessions/{session_id}/signals", response_model=List[SignalDataResponse])
async def get_signals(
    session_id: int,
    signal_names: Optional[str] = None,  # comma-separated
    resolution: str = "auto",  # auto, raw, 1min, 5min
    request: Request = None,
    db: Session = Depends(get_db),
):
    """
    Get signal data for charting.

    resolution options:
    - raw: full resolution (may be large)
    - 1min: 1-minute averages
    - 5min: 5-minute averages
    - auto: picks best resolution based on signal
    """
    query = db.query(SignalData).filter(SignalData.session_id == session_id)

    if signal_names:
        names = [n.strip() for n in signal_names.split(",")]
        query = query.filter(SignalData.signal_name.in_(names))

    signal_records = query.all()

    result = []
    for sig in signal_records:
        data_resp = SignalDataResponse(
            signal_name=sig.signal_name,
            sampling_rate=sig.sampling_rate,
            unit=sig.unit,
            values=[],
        )

        if resolution == "raw" or (resolution == "auto" and sig.sampling_rate <= 0.5):
            data_resp.values = sig.data_json or []
        elif resolution == "1min" or (resolution == "auto" and sig.sampling_rate <= 1.0):
            data_resp.values = sig.data_1min if sig.data_1min else (sig.data_json or [])
        elif resolution == "5min" or resolution == "auto":
            data_resp.values = sig.data_5min if sig.data_5min else (sig.data_1min if sig.data_1min else (sig.data_json or []))

        if sig.data_1min:
            data_resp.values_1min = sig.data_1min
        if sig.data_5min:
            data_resp.values_5min = sig.data_5min

        result.append(data_resp)

    return result


@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    """Delete a session and all its data."""
    session = db.query(NightSession).filter(NightSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    db.delete(session)
    db.commit()
    return {"status": "deleted", "session_id": session_id}


@router.delete("/uploads/{upload_id}")
async def delete_upload(
    upload_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """Delete an entire upload and all its sessions."""
    upload = db.query(Upload).filter(Upload.id == upload_id).first()
    if not upload:
        raise HTTPException(status_code=404, detail="Upload not found")

    db.delete(upload)
    db.commit()
    return {"status": "deleted", "upload_id": upload_id}
