"""Upload API routes."""

import shutil
import uuid
import zipfile
from pathlib import Path
from typing import Union, Optional, List

from fastapi import APIRouter, HTTPException, UploadFile, File, Request
from sqlalchemy.orm import Session

from ..models.database import (
    Upload, NightSession, Event, SignalData,
    init_db,
)
from ..models.schemas import UploadResponse, UploadStatus
from ..services.extractor import CPAPDataExtractor

router = APIRouter()


def get_db(request: Request) -> Session:
    factory = request.app.state.db_session_factory
    session = factory()
    try:
        yield session
    finally:
        session.close()


@router.post("/upload", response_model=UploadResponse)
async def upload_cpap_data(
    request: Request,
    file: UploadFile = File(...),
):
    """
    Upload a zip file containing ResMed SD card data.

    The zip should contain the SD card directory structure:
    - DATALOG/ (EDF files)
    - Identification.json
    - SETTINGS/CurrentSettings.json
    - STR.edf
    """
    settings = request.app.state.settings
    upload_id = str(uuid.uuid4())

    # Save uploaded file
    upload_dir = Path(settings.upload_dir) / upload_id
    upload_dir.mkdir(parents=True, exist_ok=True)

    zip_path = upload_dir / "upload.zip"
    try:
        with open(zip_path, "wb") as f:
            content = await file.read()
            f.write(content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save upload: {e}")

    # Extract zip
    extract_dir = upload_dir / "sd_card"
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(extract_dir)
    except zipfile.BadZipFile:
        raise HTTPException(status_code=400, detail="Invalid zip file")

    # Find the SD card root (might be nested in a directory)
    sd_root = _find_sd_root(extract_dir)
    if sd_root is None:
        raise HTTPException(
            status_code=400,
            detail="Could not find ResMed SD card structure. "
                   "Ensure the zip contains DATALOG/ and Identification.json",
        )

    # Create upload record
    db_factory = request.app.state.db_session_factory
    db = db_factory()

    try:
        upload_record = Upload(
            id=upload_id,
            status="processing",
            file_path=str(sd_root),
        )
        db.add(upload_record)
        db.commit()

        # Extract data
        extractor = CPAPDataExtractor(sd_root)
        night_sessions = extractor.extract_all()

        # Update device info
        upload_record.device_info = extractor.device_info
        upload_record.settings_info = extractor.settings
        upload_record.num_sessions = len(night_sessions)

        # Store each night session
        for night in night_sessions:
            db_session = _store_night_session(db, upload_id, night)
            db.flush()

            # Store events
            for evt in night.events:
                db_event = Event(
                    session_id=db_session.id,
                    event_type=evt.event_type,
                    onset_seconds=evt.onset,
                    duration_seconds=evt.duration,
                    raw_text=evt.raw_text,
                )
                db.add(db_event)

            # Store signal data
            for signal_name, parsed_sig in {**night.pld_signals, **night.sa2_signals}.items():
                sig_data = SignalData(
                    session_id=db_session.id,
                    signal_name=signal_name,
                    sampling_rate=parsed_sig.sampling_rate,
                    unit=parsed_sig.unit,
                    data_json=parsed_sig.data.astype(np.float32).tolist(),
                )
                # Create downsampled versions
                if parsed_sig.sampling_rate > 1.0 / 60.0:
                    ds1 = parsed_sig.downsample(60.0)
                    sig_data.data_1min = ds1.data.astype(np.float32).tolist()
                if parsed_sig.sampling_rate > 1.0 / 300.0:
                    ds5 = parsed_sig.downsample(300.0)
                    sig_data.data_5min = ds5.data.astype(np.float32).tolist()

                db.add(sig_data)

            # Also store BRP signals (high-res, but only downsampled)
            for signal_name, parsed_sig in night.brp_signals.items():
                sig_data = SignalData(
                    session_id=db_session.id,
                    signal_name=signal_name,
                    sampling_rate=parsed_sig.sampling_rate,
                    unit=parsed_sig.unit,
                    data_json=[],  # Don't store full res in DB — too large
                )
                # Only store downsampled versions for BRP
                ds1 = parsed_sig.downsample(60.0)
                sig_data.data_1min = ds1.data.astype(np.float32).tolist()
                ds5 = parsed_sig.downsample(300.0)
                sig_data.data_5min = ds5.data.astype(np.float32).tolist()
                db.add(sig_data)

        upload_record.status = "complete" if not extractor.errors else "complete_with_errors"
        db.commit()

        return UploadResponse(
            upload_id=upload_id,
            status=upload_record.status,
            num_sessions=len(night_sessions),
            device_info=extractor.device_info,
        )

    except Exception as e:
        db.rollback()
        upload_record.status = "error"
        upload_record.error_message = str(e)
        db.commit()
        raise HTTPException(status_code=500, detail=f"Processing failed: {e}")
    finally:
        db.close()

    # Cleanup zip after extraction
    if zip_path.exists():
        zip_path.unlink()


def _find_sd_root(extract_dir: Path) -> Optional[Path]:
    """Find the SD card root directory (contains DATALOG/ or Identification.json)."""
    # Check if extract_dir itself is the root
    if (extract_dir / "DATALOG").exists() or (extract_dir / "Identification.json").exists():
        return extract_dir

    # Check one level deep (common when zipping a folder)
    for child in extract_dir.iterdir():
        if child.is_dir():
            if (child / "DATALOG").exists() or (child / "Identification.json").exists():
                return child

    # Check two levels deep
    for child in extract_dir.rglob("DATALOG"):
        return child.parent

    for child in extract_dir.rglob("Identification.json"):
        return child.parent

    return None


def _store_night_session(db, upload_id: str, night) -> NightSession:
    """Store a NightSession in the database."""
    from datetime import datetime

    session_date = datetime.strptime(night.session_date, "%Y-%m-%d").date()

    db_session = NightSession(
        upload_id=upload_id,
        session_date=session_date,
        duration_hours=night.duration_hours,
        mask_on_seconds=night.str_summary.mask_on_seconds if night.str_summary else 0.0,
        mask_off_seconds=night.str_summary.mask_off_seconds if night.str_summary else 0.0,
        ahi=night.ahi,
        oai=night.str_summary.oai if night.str_summary else 0.0,
        cai=night.str_summary.cai if night.str_summary else 0.0,
        hi=night.str_summary.hi if night.str_summary else 0.0,
        leak_50=night.str_summary.leak_50 if night.str_summary else 0.0,
        leak_95=night.leak_95,
        leak_max=night.str_summary.leak_max if night.str_summary else 0.0,
        pressure_50=night.str_summary.pressure_50 if night.str_summary else 0.0,
        pressure_95=night.pressure_95,
        pressure_max=night.str_summary.pressure_max if night.str_summary else 0.0,
        epap_95=night.str_summary.epap_95 if night.str_summary else 0.0,
        rr_50=night.str_summary.rr_50 if night.str_summary else 0.0,
        mv_50=night.str_summary.mv_50 if night.str_summary else 0.0,
        tv_50=night.str_summary.tv_50 if night.str_summary else 0.0,
        set_pressure=night.str_summary.set_pressure if night.str_summary else 0.0,
        min_pressure=night.str_summary.min_pressure if night.str_summary else 0.0,
        max_pressure=night.str_summary.max_pressure if night.str_summary else 0.0,
        epr_level=night.str_summary.epr_level if night.str_summary else 0,
        csr_percent=night.str_summary.csr_percent if night.str_summary else 0.0,
        source_files=night.source_files,
        event_counts=night.event_counts,
    )
    db.add(db_session)
    db.flush()  # Get the ID
    return db_session


# Need numpy for float32 conversion
import numpy as np
