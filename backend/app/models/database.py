"""Database models for CPAP Analyzer."""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Column, Integer, Float, String, DateTime, Date,
    ForeignKey, Text, JSON, create_engine, Index,
)
from sqlalchemy.orm import DeclarativeBase, relationship, sessionmaker


class Base(DeclarativeBase):
    pass


class Upload(Base):
    """A single data upload (one SD card zip)."""
    __tablename__ = "uploads"

    id = Column(String, primary_key=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    status = Column(String, default="processing")  # processing, complete, error
    file_path = Column(String)
    device_info = Column(JSON, default=dict)
    settings_info = Column(JSON, default=dict)
    error_message = Column(Text, nullable=True)
    num_sessions = Column(Integer, default=0)

    sessions = relationship("NightSession", back_populates="upload", cascade="all, delete-orphan")


class NightSession(Base):
    """One night of CPAP data."""
    __tablename__ = "night_sessions"
    __table_args__ = (
        Index("ix_night_sessions_date", "session_date"),
        Index("ix_night_sessions_upload", "upload_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    upload_id = Column(String, ForeignKey("uploads.id"))
    session_date = Column(Date, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Duration
    duration_hours = Column(Float, default=0.0)
    mask_on_seconds = Column(Float, default=0.0)
    mask_off_seconds = Column(Float, default=0.0)

    # AHI breakdown
    ahi = Column(Float, default=0.0)
    oai = Column(Float, default=0.0)
    cai = Column(Float, default=0.0)
    hi = Column(Float, default=0.0)

    # Leak (L/min)
    leak_50 = Column(Float, default=0.0)
    leak_95 = Column(Float, default=0.0)
    leak_max = Column(Float, default=0.0)

    # Pressure (cmH₂O)
    pressure_50 = Column(Float, default=0.0)
    pressure_95 = Column(Float, default=0.0)
    pressure_max = Column(Float, default=0.0)
    epap_95 = Column(Float, default=0.0)

    # Respiratory
    rr_50 = Column(Float, default=0.0)
    mv_50 = Column(Float, default=0.0)
    tv_50 = Column(Float, default=0.0)

    # Settings
    set_pressure = Column(Float, default=0.0)
    min_pressure = Column(Float, default=0.0)
    max_pressure = Column(Float, default=0.0)
    epr_level = Column(Integer, default=0)

    # CSR
    csr_percent = Column(Float, default=0.0)

    # Raw data references (paths to extracted files)
    source_files = Column(JSON, default=dict)

    # Event counts
    event_counts = Column(JSON, default=dict)

    upload = relationship("Upload", back_populates="sessions")
    events = relationship("Event", back_populates="session", cascade="all, delete-orphan")
    signals = relationship("SignalData", back_populates="session", cascade="all, delete-orphan")


class Event(Base):
    """A single sleep event (apnea, hypopnea, etc.)."""
    __tablename__ = "events"
    __table_args__ = (
        Index("ix_events_session", "session_id"),
        Index("ix_events_type", "event_type"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(Integer, ForeignKey("night_sessions.id"))
    event_type = Column(String(10), nullable=False)  # OA, CA, H, AR, etc.
    onset_seconds = Column(Float, default=0.0)
    duration_seconds = Column(Float, default=0.0)
    raw_text = Column(Text, default="")

    session = relationship("NightSession", back_populates="events")


class SignalData(Base):
    """Pre-processed signal data for charting."""
    __tablename__ = "signal_data"
    __table_args__ = (
        Index("ix_signal_data_session", "session_id"),
        Index("ix_signal_data_name", "signal_name"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(Integer, ForeignKey("night_sessions.id"))
    signal_name = Column(String(50), nullable=False)
    sampling_rate = Column(Float, default=0.0)
    unit = Column(String(20), default="")
    # Store as compressed JSON for now; could move to binary later
    data_json = Column(JSON, default=list)
    # Downsampled versions
    data_1min = Column(JSON, nullable=True)
    data_5min = Column(JSON, nullable=True)

    session = relationship("NightSession", back_populates="signals")


class AIReport(Base):
    """Generated AI analysis report."""
    __tablename__ = "ai_reports"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(Integer, ForeignKey("night_sessions.id"), nullable=True)
    upload_id = Column(String, ForeignKey("uploads.id"), nullable=True)
    report_type = Column(String(20), default="nightly")  # nightly, trend, custom
    summary_text = Column(Text, default="")
    key_findings = Column(JSON, default=list)
    recommendations = Column(JSON, default=list)
    tokens_used = Column(Integer, default=0)
    model_version = Column(String(50), default="")
    created_at = Column(DateTime, default=datetime.utcnow)


# ── Database setup ────────────────────────────────────────────────────────
def create_db_engine(db_url: str = "sqlite:///./cpap.db"):
    # For absolute paths (Docker: sqlite:////data/cpap.db),
    # SQLAlchemy expects 4 slashes. For relative: 3 slashes.
    return create_engine(db_url, echo=False, connect_args={"check_same_thread": False})


def init_db(engine):
    Base.metadata.create_all(engine)


def get_session_factory(engine):
    return sessionmaker(bind=engine)
