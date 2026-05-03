"""
Data extraction service — orchestrates parsing an entire ResMed SD card upload.

Given an extracted SD card directory, this service:
1. Identifies the directory structure
2. Groups EDF files by date
3. Parses each file type (BRP, PLD, EVE, SA2, STR)
4. Builds nightly session objects with all extracted data
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from app.parsers.resmed_parsers import (
    STRDaySummary,
    parse_brp,
    parse_csl,
    parse_eve,
    parse_identification,
    parse_pld,
    parse_sa2,
    parse_settings,
    parse_str,
    ParsedEvent,
    ParsedSignal,
)
from edf_lib.resmed import ResMedFileType

logger = logging.getLogger(__name__)


# ── Data structures ───────────────────────────────────────────────────────
class NightSession:
    """All data for a single night of CPAP usage."""

    def __init__(self, session_date: str):
        self.session_date = session_date
        self.device_info: dict = {}
        self.settings: dict = {}
        self.str_summary: Optional[STRDaySummary] = None

        # Waveform signals by type
        self.brp_signals: Dict[str, ParsedSignal] = {}
        self.pld_signals: Dict[str, ParsedSignal] = {}
        self.sa2_signals: Dict[str, ParsedSignal] = {}
        self.csl_signals: Dict[str, ParsedSignal] = {}

        # Events
        self.events: List[ParsedEvent] = []

        # Raw file references
        self.source_files: Dict[str, str] = {}

    @property
    def ahi(self) -> float:
        if self.str_summary:
            return self.str_summary.ahi
        # Calculate from events
        if self.events and self.duration_hours > 0:
            return len(self.events) / self.duration_hours
        return 0.0

    @property
    def duration_hours(self) -> float:
        if self.str_summary and self.str_summary.mask_duration_seconds > 0:
            return self.str_summary.mask_duration_seconds / 3600.0
        # Estimate from signal data
        if self.pld_signals:
            for sig in self.pld_signals.values():
                if len(sig.data) > 0:
                    return len(sig.data) / sig.sampling_rate / 3600.0
        return 0.0

    @property
    def event_counts(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for e in self.events:
            counts[e.event_type] = counts.get(e.event_type, 0) + 1
        return counts

    @property
    def leak_95(self) -> float:
        if self.str_summary:
            return self.str_summary.leak_95
        if "leak" in self.pld_signals:
            leak = self.pld_signals["leak"].data
            if len(leak) > 0:
                return float(np.percentile(leak, 95))
        return 0.0

    @property
    def pressure_95(self) -> float:
        if self.str_summary:
            return self.str_summary.pressure_95
        if "pressure" in self.pld_signals:
            p = self.pld_signals["pressure"].data
            if len(p) > 0:
                return float(np.percentile(p, 95))
        return 0.0

    def to_dict(self) -> dict:
        """Serialize for API responses and storage."""
        result = {
            "session_date": self.session_date,
            "duration_hours": round(self.duration_hours, 2),
            "ahi": round(self.ahi, 1),
            "event_counts": self.event_counts,
            "leak_95": round(self.leak_95, 1),
            "pressure_95": round(self.pressure_95, 1),
            "source_files": self.source_files,
        }

        if self.str_summary:
            s = self.str_summary
            result["str_summary"] = {
                "mask_on_seconds": s.mask_on_seconds,
                "mask_off_seconds": s.mask_off_seconds,
                "mask_duration_seconds": s.mask_duration_seconds,
                "ahi": s.ahi,
                "oai": s.oai,
                "cai": s.cai,
                "hi": s.hi,
                "leak_50": round(s.leak_50, 1),
                "leak_95": round(s.leak_95, 1),
                "leak_max": round(s.leak_max, 1),
                "pressure_50": round(s.pressure_50, 1),
                "pressure_95": round(s.pressure_95, 1),
                "pressure_max": round(s.pressure_max, 1),
                "epap_50": round(s.epap_50, 1),
                "epap_95": round(s.epap_95, 1),
                "epap_max": round(s.epap_max, 1),
                "rr_50": round(s.rr_50, 1),
                "rr_95": round(s.rr_95, 1),
                "rr_max": round(s.rr_max, 1),
                "mv_50": round(s.mv_50, 1),
                "mv_95": round(s.mv_95, 1),
                "mv_max": round(s.mv_max, 1),
                "tv_50": round(s.tv_50, 1),
                "tv_95": round(s.tv_95, 1),
                "tv_max": round(s.tv_max, 1),
                "set_pressure": s.set_pressure,
                "min_pressure": s.min_pressure,
                "max_pressure": s.max_pressure,
                "epr_level": s.epr_level,
                "ramp_pressure": s.ramp_pressure,
                "ramp_time": s.ramp_time,
                "csr_percent": s.csr_percent,
            }

        return result


# ── Need numpy for percentile calculation ──
import numpy as np


# ── Extractor ─────────────────────────────────────────────────────────────
class CPAPDataExtractor:
    """
    Orchestrate extraction of CPAP data from an SD card directory.

    Usage:
        extractor = CPAPDataExtractor("/path/to/sd_card_root")
        sessions = extractor.extract_all()
    """

    def __init__(self, sd_card_dir: Union[str, Path]):
        self.sd_card_dir = Path(sd_card_dir)
        self.datalog_dir = self.sd_card_dir / "DATALOG"
        self.sessions: Dict[str, NightSession] = {}  # date_str → NightSession
        self.device_info: dict = {}
        self.settings: dict = {}
        self.str_summaries: Dict[str, STRDaySummary] = {}

        self._errors: List[str] = []
        self._warnings: List[str] = []

    @property
    def errors(self) -> List[str]:
        return self._errors

    @property
    def warnings(self) -> List[str]:
        return self._warnings

    def extract_all(self) -> List[NightSession]:
        """
        Main extraction pipeline. Returns list of NightSession objects.
        """
        logger.info(f"Starting CPAP data extraction from {self.sd_card_dir}")

        # 1. Parse device identification and settings
        self._parse_device_info()

        # 2. Parse STR.edf for daily summaries
        self._parse_str_file()

        # 3. Scan DATALOG directory and group files by date
        files_by_date = self._scan_datalog()

        # 4. Parse each day's files
        for date_str, files in files_by_date.items():
            session = self.sessions.get(date_str, NightSession(date_str))
            session.device_info = self.device_info
            session.settings = self.settings

            if date_str in self.str_summaries:
                session.str_summary = self.str_summaries[date_str]

            for file_type, filepath in files.items():
                try:
                    self._parse_day_file(session, file_type, filepath)
                    session.source_files[file_type.value] = str(filepath)
                except Exception as e:
                    self._errors.append(
                        f"Error parsing {filepath}: {e}"
                    )
                    logger.warning(f"Failed to parse {filepath}: {e}", exc_info=True)

            self.sessions[date_str] = session

        # 5. Return sessions sorted by date
        sorted_sessions = sorted(
            self.sessions.values(),
            key=lambda s: s.session_date,
        )

        logger.info(
            f"Extraction complete: {len(sorted_sessions)} sessions, "
            f"{len(self._errors)} errors"
        )
        return sorted_sessions

    def _parse_device_info(self):
        """Parse Identification.json and CurrentSettings.json."""
        id_file = self.sd_card_dir / "Identification.json"
        if id_file.exists():
            self.device_info = parse_identification(id_file)

        settings_file = self.sd_card_dir / "SETTINGS" / "CurrentSettings.json"
        if not settings_file.exists():
            settings_file = self.sd_card_dir / "CurrentSettings.json"
        if settings_file.exists():
            self.settings = parse_settings(settings_file)

    def _parse_str_file(self):
        """Parse the STR.edf file for daily summaries."""
        str_file = self.sd_card_dir / "STR.edf"
        if not str_file.exists():
            # Try DATALOG for STR files
            for f in self.sd_card_dir.rglob("STR.edf"):
                str_file = f
                break

        if not str_file.exists():
            self._warnings.append("No STR.edf file found — daily summaries will be limited")
            return

        try:
            summaries = parse_str(str_file)
            for summary in summaries:
                self.str_summaries[summary.date] = summary
                # Pre-create sessions
                if summary.date not in self.sessions:
                    self.sessions[summary.date] = NightSession(summary.date)
        except Exception as e:
            self._errors.append(f"Error parsing STR.edf: {e}")
            logger.warning(f"Failed to parse STR.edf: {e}", exc_info=True)

    def _scan_datalog(self) -> Dict[str, Dict[ResMedFileType, Path]]:
        """
        Scan the DATALOG directory and group files by date.

        Returns: {date_str: {file_type: filepath}}
        """
        if not self.datalog_dir.exists():
            self._errors.append(f"DATALOG directory not found: {self.datalog_dir}")
            return {}

        files_by_date: Dict[str, Dict[ResMedFileType, Path]] = {}

        for edf_file in sorted(self.datalog_dir.rglob("*.edf")):
            filename = edf_file.name
            file_type = ResMedFileType.from_filename(filename)

            if file_type is None:
                continue  # Skip unknown file types (including STR in DATALOG)

            # Extract date from directory name (YYYYMMDD)
            date_dir = edf_file.parent.name
            if len(date_dir) == 8 and date_dir.isdigit():
                date_str = f"{date_dir[:4]}-{date_dir[4:6]}-{date_dir[6:8]}"
            else:
                # Try to extract from filename
                date_str = filename[:8]
                if len(date_str) == 8 and date_str.isdigit():
                    date_str = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
                else:
                    continue

            if date_str not in files_by_date:
                files_by_date[date_str] = {}

            # For same type on same date, keep the later one (or merge)
            if file_type in files_by_date[date_str]:
                # Multiple files of same type on same day — likely multiple sessions
                # Use the one with later timestamp for now
                existing = files_by_date[date_str][file_type]
                if edf_file.name > existing.name:
                    files_by_date[date_str][file_type] = edf_file
            else:
                files_by_date[date_str][file_type] = edf_file

        logger.info(f"Found {sum(len(v) for v in files_by_date.values())} EDF files across {len(files_by_date)} days")
        return files_by_date

    def _parse_day_file(
        self,
        session: NightSession,
        file_type: ResMedFileType,
        filepath: Path,
    ):
        """Parse a single EDF file and merge into the session."""
        if file_type == ResMedFileType.BRP:
            session.brp_signals = parse_brp(filepath)

        elif file_type == ResMedFileType.PLD:
            session.pld_signals = parse_pld(filepath)

        elif file_type == ResMedFileType.EVE:
            session.events = parse_eve(filepath)

        elif file_type == ResMedFileType.SA2:
            session.sa2_signals = parse_sa2(filepath)

        elif file_type == ResMedFileType.CSL:
            session.csl_signals = parse_csl(filepath)

        # STR type is handled separately via _parse_str_file

    def get_summary(self) -> dict:
        """Get a high-level summary of the extracted data."""
        return {
            "device_info": self.device_info,
            "settings": self.settings,
            "num_sessions": len(self.sessions),
            "date_range": {
                "first": min(s.session_date for s in self.sessions.values()) if self.sessions else None,
                "last": max(s.session_date for s in self.sessions.values()) if self.sessions else None,
            },
            "errors": self._errors,
            "warnings": self._warnings,
        }
