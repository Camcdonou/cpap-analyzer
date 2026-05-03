#!/usr/bin/env python3
"""
CLI script to load CPAP data directly into the database.

Usage:
    python load_data.py /path/to/sd_card_root
"""

import sys
import os

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.models.database import create_db_engine, init_db, get_session_factory, Upload, NightSession, Event, SignalData
from app.services.extractor import CPAPDataExtractor
from app.parsers.resmed_parsers import ParsedEvent, ParsedSignal
import uuid
import numpy as np
from datetime import datetime


def load_data(sd_card_dir: str):
    """Load CPAP data from SD card directory into the database."""
    print(f"Loading CPAP data from: {sd_card_dir}")

    # Init database — use DATABASE_URL env var if set (Docker), else local path
    import os
    db_url = os.environ.get("DATABASE_URL", "sqlite:///./cpap.db")
    engine = create_db_engine(db_url)
    init_db(engine)
    Session = get_session_factory(engine)
    db = Session()

    try:
        # Check if data already loaded
        existing = db.query(Upload).first()
        if existing:
            print(f"Data already loaded (upload_id={existing.id}, {existing.num_sessions} sessions)")
            print("Delete cpap.db to reload.")
            return

        # Extract data
        extractor = CPAPDataExtractor(sd_card_dir)
        sessions = extractor.extract_all()

        if not sessions:
            print("No sessions found!")
            return

        # Create upload record
        upload_id = str(uuid.uuid4())
        upload = Upload(
            id=upload_id,
            status="complete",
            file_path=sd_card_dir,
            device_info=extractor.device_info,
            settings_info=extractor.settings,
            num_sessions=len(sessions),
        )
        db.add(upload)
        db.flush()

        # Store each session
        for i, night in enumerate(sessions):
            # Skip sessions with no actual data
            if night.duration_hours < 0.1 and (not night.str_summary or night.str_summary.mask_duration_seconds <= 0):
                continue

            session_date = datetime.strptime(night.session_date, "%Y-%m-%d").date()

            str_s = night.str_summary
            db_session = NightSession(
                upload_id=upload_id,
                session_date=session_date,
                duration_hours=night.duration_hours,
                mask_on_seconds=str_s.mask_on_seconds if str_s else 0.0,
                mask_off_seconds=str_s.mask_off_seconds if str_s else 0.0,
                ahi=night.ahi,
                oai=str_s.oai if str_s else 0.0,
                cai=str_s.cai if str_s else 0.0,
                hi=str_s.hi if str_s else 0.0,
                leak_50=str_s.leak_50 if str_s else 0.0,
                leak_95=night.leak_95,
                leak_max=str_s.leak_max if str_s else 0.0,
                pressure_50=str_s.pressure_50 if str_s else 0.0,
                pressure_95=night.pressure_95,
                pressure_max=str_s.pressure_max if str_s else 0.0,
                epap_95=str_s.epap_95 if str_s else 0.0,
                rr_50=str_s.rr_50 if str_s else 0.0,
                mv_50=str_s.mv_50 if str_s else 0.0,
                tv_50=str_s.tv_50 if str_s else 0.0,
                set_pressure=str_s.set_pressure if str_s else 0.0,
                min_pressure=str_s.min_pressure if str_s else 0.0,
                max_pressure=str_s.max_pressure if str_s else 0.0,
                epr_level=str_s.epr_level if str_s else 0,
                csr_percent=str_s.csr_percent if str_s else 0.0,
                source_files=night.source_files,
                event_counts=night.event_counts,
            )
            db.add(db_session)
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

            # Store signal data (PLD + SA2)
            for signal_name, parsed_sig in {**night.pld_signals, **night.sa2_signals}.items():
                sig_data = SignalData(
                    session_id=db_session.id,
                    signal_name=signal_name,
                    sampling_rate=parsed_sig.sampling_rate,
                    unit=parsed_sig.unit,
                    data_json=parsed_sig.data.astype(np.float32).tolist(),
                )
                # Downsampled versions
                if parsed_sig.sampling_rate > 1.0 / 60.0:
                    ds1 = parsed_sig.downsample(60.0)
                    sig_data.data_1min = ds1.data.astype(np.float32).tolist()
                if parsed_sig.sampling_rate > 1.0 / 300.0:
                    ds5 = parsed_sig.downsample(300.0)
                    sig_data.data_5min = ds5.data.astype(np.float32).tolist()
                db.add(sig_data)

            # Store BRP signals (only downsampled to save space)
            for signal_name, parsed_sig in night.brp_signals.items():
                sig_data = SignalData(
                    session_id=db_session.id,
                    signal_name=signal_name,
                    sampling_rate=parsed_sig.sampling_rate,
                    unit=parsed_sig.unit,
                    data_json=[],  # Skip full-res BRP — too large
                )
                ds1 = parsed_sig.downsample(60.0)
                sig_data.data_1min = ds1.data.astype(np.float32).tolist()
                ds5 = parsed_sig.downsample(300.0)
                sig_data.data_5min = ds5.data.astype(np.float32).tolist()
                db.add(sig_data)

            if (i + 1) % 10 == 0:
                print(f"  Processed {i + 1}/{len(sessions)} sessions...")
                db.commit()

        db.commit()
        print(f"\nDone! Loaded {len(sessions)} sessions into cpap.db")
        print(f"Device: {extractor.device_info.get('product_name', 'Unknown')}")
        print(f"Date range: {sessions[0].session_date} to {sessions[-1].session_date}")

    except Exception as e:
        db.rollback()
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python load_data.py /path/to/sd_card_root")
        sys.exit(1)

    load_data(sys.argv[1])
