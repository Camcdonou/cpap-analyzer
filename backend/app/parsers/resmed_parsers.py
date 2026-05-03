"""
ResMed CPAP file parsers — one per EDF file type.

Each parser reads a specific EDF file type (BRP, PLD, EVE, SA2, STR)
and returns structured data matching OSCAR's extraction logic.
"""

from __future__ import annotations

import json
import struct
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

import sys
from pathlib import Path
# Add parent directory to path so edf_lib is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from edf_lib.edf_reader import EDFReader, EDFSignal, Annotation
from edf_lib.resmed import (
    ResMedFileType,
    SIGNAL_MAP,
    GAIN_OVERRIDES,
    UNIT_OVERRIDES,
    EVENT_TYPE_DISPLAY,
    ParsedEvent,
    ParsedSignal,
    apply_gain_override,
    classify_event,
    lookup_signal,
)


# ── BRP Parser (high-res breathing waveforms) ────────────────────────────
def parse_brp(filepath: Union[str, Path]) -> Dict[str, ParsedSignal]:
    """
    Parse a BRP (Breathing Pattern) EDF file.

    Contains high-resolution waveforms:
    - Flow Rate (at 25 Hz / 40ms intervals) → converted to L/min
    - Mask Pressure (at 25 Hz) → cmH₂O
    - Resp Events (at 25 Hz) → event markers

    Ported from OSCAR ResmedLoader::LoadBRP()
    """
    reader = EDFReader.from_file(filepath)
    reader.parse_header()
    reader.parse_signal_descriptors()
    signals = reader.parse_signals()

    duration = reader.header.duration_per_record * reader.header.num_data_records

    result = {}

    # Flow Rate — gain *= 60.0 (L/s → L/min)
    flow = lookup_signal(signals, "flow_rate")
    if flow is not None:
        sr = flow.descriptor.samples_per_record / reader.header.duration_per_record if reader.header.duration_per_record > 0 else 0.0
        data = apply_gain_override("flow_rate", flow.data)
        result["flow_rate"] = ParsedSignal(
            name="flow_rate",
            data=data,
            sampling_rate=sr,
            unit=UNIT_OVERRIDES.get("flow_rate", "L/min"),
        )

    # Mask Pressure (high-res)
    mask_p = lookup_signal(signals, "mask_pressure_hi")
    if mask_p is not None:
        sr = mask_p.descriptor.samples_per_record / reader.header.duration_per_record if reader.header.duration_per_record > 0 else 0.0
        result["mask_pressure_hi"] = ParsedSignal(
            name="mask_pressure_hi",
            data=mask_p.data,
            sampling_rate=sr,
            unit=UNIT_OVERRIDES.get("mask_pressure_hi", "cmH₂O"),
        )

    # Resp Events
    resp_evt = lookup_signal(signals, "resp_event")
    if resp_evt is not None:
        sr = resp_evt.descriptor.samples_per_record / reader.header.duration_per_record if reader.header.duration_per_record > 0 else 0.0
        result["resp_event"] = ParsedSignal(
            name="resp_event",
            data=resp_evt.data,
            sampling_rate=sr,
            unit="",
        )

    return result


# ── PLD Parser (low-res summary data) ────────────────────────────────────
def parse_pld(filepath: Union[str, Path]) -> Dict[str, ParsedSignal]:
    """
    Parse a PLD (Pressure/Leak Data) EDF file.

    Contains lower-resolution summary signals at 2-second intervals:
    - Pressure, EPAP, Leak (→ L/min), Resp Rate, Minute Ventilation,
      Tidal Volume (→ mL), Snore, Flow Limitation, I:E ratio, etc.

    Ported from OSCAR ResmedLoader::LoadPLD()
    """
    reader = EDFReader.from_file(filepath)
    reader.parse_header()
    reader.parse_signal_descriptors()
    signals = reader.parse_signals()

    result = {}

    # Channels to extract from PLD
    pld_channels = [
        "pressure", "epap", "ipap", "leak", "resp_rate",
        "minute_vent", "tidal_volume", "snore", "flow_limitation",
        "mask_pressure", "ie_ratio", "inspiratory_time", "expiratory_time",
        "target_mv",
    ]

    for ch_name in pld_channels:
        sig = lookup_signal(signals, ch_name)
        if sig is not None:
            sr = sig.descriptor.samples_per_record / reader.header.duration_per_record if reader.header.duration_per_record > 0 else 0.0
            data = apply_gain_override(ch_name, sig.data)
            result[ch_name] = ParsedSignal(
                name=ch_name,
                data=data,
                sampling_rate=sr,
                unit=UNIT_OVERRIDES.get(ch_name, sig.descriptor.physical_dimension),
            )

    return result


# ── EVE Parser (event annotations) ────────────────────────────────────────
def parse_eve(filepath: Union[str, Path]) -> List[ParsedEvent]:
    """
    Parse an EVE (Event) EDF file.

    Contains EDF+ annotations for scored events:
    - Obstructive Apnea, Central Apnea, Hypopnea, Arousal, etc.

    Ported from OSCAR ResmedLoader::LoadEVE()
    """
    reader = EDFReader.from_file(filepath)
    reader.parse_header()
    reader.parse_signal_descriptors()

    annotations = reader.parse_annotations()

    events = []
    for ann in annotations:
        event_type = classify_event(ann.text)
        if event_type == "UNK":
            continue  # Skip unknown/SpO2 desaturation events

        events.append(ParsedEvent(
            event_type=event_type,
            onset=ann.onset,
            duration=ann.duration if ann.duration >= 0 else 0.0,
            raw_text=ann.text,
        ))

    return events


# ── SA2 Parser (AirSense 11 summary) ─────────────────────────────────────
def parse_sa2(filepath: Union[str, Path]) -> Dict[str, ParsedSignal]:
    """
    Parse an SA2 (Summary) EDF file — AirSense 11 specific.

    Similar to PLD but contains summary-level data.
    """
    reader = EDFReader.from_file(filepath)
    reader.parse_header()
    reader.parse_signal_descriptors()
    signals = reader.parse_signals()

    result = {}

    # SA2 can contain the same signals as PLD plus some summary fields
    sa2_channels = [
        "pressure", "epap", "leak", "resp_rate",
        "minute_vent", "tidal_volume", "snore", "flow_limitation",
        "mask_pressure",
    ]

    for ch_name in sa2_channels:
        sig = lookup_signal(signals, ch_name)
        if sig is not None:
            sr = sig.descriptor.samples_per_record / reader.header.duration_per_record if reader.header.duration_per_record > 0 else 0.0
            data = apply_gain_override(ch_name, sig.data)
            result[ch_name] = ParsedSignal(
                name=ch_name,
                data=data,
                sampling_rate=sr,
                unit=UNIT_OVERRIDES.get(ch_name, sig.descriptor.physical_dimension),
            )

    # Also check for STR-style percentile signals
    str_channels = [
        "str_leak_50", "str_leak_95", "str_leak_max",
        "str_rr_50", "str_rr_95", "str_rr_max",
        "str_mv_50", "str_mv_95", "str_mv_max",
        "str_tv_50", "str_tv_95", "str_tv_max",
        "str_mp_50", "str_mp_95", "str_mp_max",
        "str_epap_50", "str_epap_95", "str_epap_max",
    ]

    for ch_name in str_channels:
        sig = lookup_signal(signals, ch_name)
        if sig is not None:
            sr = sig.descriptor.samples_per_record / reader.header.duration_per_record if reader.header.duration_per_record > 0 else 0.0
            data = apply_gain_override(ch_name, sig.data)
            result[ch_name] = ParsedSignal(
                name=ch_name,
                data=data,
                sampling_rate=sr,
                unit=UNIT_OVERRIDES.get(ch_name, sig.descriptor.physical_dimension),
            )

    return result


# ── CSL Parser (Cheyne-Stokes Respiration) ───────────────────────────────
def parse_csl(filepath: Union[str, Path]) -> Dict[str, ParsedSignal]:
    """
    Parse a CSL (Cheyne-Stokes) EDF file.

    Contains flags for Cheyne-Stokes Respiration periods.
    """
    reader = EDFReader.from_file(filepath)
    reader.parse_header()
    reader.parse_signal_descriptors()
    signals = reader.parse_signals()

    result = {}
    # CSL typically has a single signal
    for sig in signals:
        if sig.descriptor.label.lower().strip():
            dur = reader.header.duration_per_record
            sr = (sig.descriptor.samples_per_record / dur) if dur > 0 else 0.0
            name = sig.descriptor.label.lower().replace(" ", "_").replace(".", "_")
            result[name] = ParsedSignal(
                name=name,
                data=sig.data,
                sampling_rate=sr,
                unit=sig.descriptor.physical_dimension,
            )

    return result


# ── STR Parser (daily summary statistics) ─────────────────────────────────
@dataclass
class STRDaySummary:
    """Daily summary extracted from STR.edf — one record per day of use."""
    date: str                # YYYY-MM-DD
    mask_on_seconds: float = 0.0
    mask_off_seconds: float = 0.0
    mask_duration_seconds: float = 0.0

    # AHI breakdown
    ahi: float = 0.0
    oai: float = 0.0
    cai: float = 0.0
    uai: float = 0.0
    hi: float = 0.0

    # Leak statistics (L/min after *60 gain)
    leak_50: float = 0.0
    leak_95: float = 0.0
    leak_max: float = 0.0

    # Pressure statistics (cmH₂O)
    pressure_50: float = 0.0
    pressure_95: float = 0.0
    pressure_max: float = 0.0
    epap_50: float = 0.0
    epap_95: float = 0.0
    epap_max: float = 0.0

    # Respiratory statistics
    rr_50: float = 0.0
    rr_95: float = 0.0
    rr_max: float = 0.0
    mv_50: float = 0.0
    mv_95: float = 0.0
    mv_max: float = 0.0
    tv_50: float = 0.0
    tv_95: float = 0.0
    tv_max: float = 0.0

    # Settings
    set_pressure: float = 0.0
    min_pressure: float = 0.0
    max_pressure: float = 0.0
    epr_level: int = 0
    ramp_pressure: float = 0.0
    ramp_time: int = 0

    # CSR
    csr_percent: float = 0.0

    # Therapy mode
    therapy_mode: int = 0


# No-data sentinel values used by ResMed STR files
# These indicate no session data for that day
NODATA_FLOAT = -0.1    # AHI, HI, AI, OAI, CAI, UAI, RIN
NODATA_SMALL = -0.02   # Pressure, Leak, TidalVolume, EPAP, etc.
NODATA_INT = -1.0      # Duration, Mode, MaskEvents, settings enums


def _is_valid_str_value(val: float, nodata_threshold: float = -0.5) -> bool:
    """Check if a STR value represents real data vs no-data sentinel."""
    return val > nodata_threshold


def parse_str(filepath: Union[str, Path]) -> List[STRDaySummary]:
    """
    Parse a STR.edf file containing daily summary records.

    Each data record in the STR file represents one day of CPAP usage.
    The STR file uses a flat record-per-day structure with signals like:
    - Date (days since Unix epoch 1970-01-01)
    - MaskOn/MaskOff (minutes, up to 20 entries per record)
    - Duration (minutes)
    - AHI, OAI, CAI, HI, AI, UAI
    - Leak.50, Leak.95, Leak.Max (L/s → multiply by 60 for L/min)
    - MaskPress.50, MaskPress.95, MaskPress.Max (cmH₂O)
    - TgtEPAP.50, TgtEPAP.95, TgtEPAP.Max (cmH₂O)
    - RespRate.50/95/Max, MinVent.50/95/Max, TidVol.50/95/Max
    - Settings: S.A.StartPress, S.A.MinPress, S.A.MaxPress, S.EPR.Level, etc.

    Ported from OSCAR ResmedLoader::ProcessSTRfiles()
    """
    from datetime import datetime, timedelta

    reader = EDFReader.from_file(filepath)
    reader.parse_header()
    reader.parse_signal_descriptors()
    signals = reader.parse_signals()

    n_records = reader.header.num_data_records
    if n_records == 0:
        return []

    # Build a lookup: label → signal data array
    sig_by_label = {}
    for sig in signals:
        sig_by_label[sig.descriptor.label.strip()] = sig.data

    def get_val(label: str, rec_idx: int, default: float = 0.0) -> float:
        """Get a single value from a signal by exact label match."""
        if label in sig_by_label:
            data = sig_by_label[label]
            if rec_idx < len(data):
                v = float(data[rec_idx])
                if _is_valid_str_value(v):
                    return v
        return default

    def get_multi_val(label: str, rec_idx: int, samples_per_rec: int) -> List[float]:
        """Get multiple values (e.g., MaskOn has 20 entries per record)."""
        if label in sig_by_label:
            data = sig_by_label[label]
            start = rec_idx * samples_per_rec
            end = start + samples_per_rec
            if end <= len(data):
                return [float(v) for v in data[start:end] if v >= 0]
        return []

    summaries = []

    for rec_idx in range(n_records):
        # Check if this record has actual data (MaskEvents >= 0 means sessions exist)
        mask_events = get_val("MaskEvents", rec_idx, default=-1.0)
        if mask_events < 0:
            continue  # Skip no-data days

        # Determine date from Date signal (days since 1970-01-01)
        date_val = get_val("Date", rec_idx)
        if date_val > 0:
            session_date = datetime(1970, 1, 1) + timedelta(days=int(date_val))
            date_str = session_date.strftime("%Y-%m-%d")
        else:
            date_str = reader.header.datetime.strftime("%Y-%m-%d")

        day = STRDaySummary(date=date_str)

        # Duration (stored in minutes)
        duration_min = get_val("Duration", rec_idx)
        day.mask_duration_seconds = duration_min * 60.0

        # Mask on/off times (minutes since midnight, up to 20 per record)
        mask_on_vals = get_multi_val("MaskOn", rec_idx, 20)
        mask_off_vals = get_multi_val("MaskOff", rec_idx, 20)
        day.mask_on_seconds = mask_on_vals[0] * 60.0 if mask_on_vals else 0.0
        day.mask_off_seconds = mask_off_vals[-1] * 60.0 if mask_off_vals else 0.0

        # AHI indices
        day.ahi = get_val("AHI", rec_idx)
        day.oai = get_val("OAI", rec_idx)
        day.cai = get_val("CAI", rec_idx)
        day.hi = get_val("HI", rec_idx)
        day.uai = get_val("UAI", rec_idx)

        # Leak stats (L/s → L/min via *60 gain)
        day.leak_50 = get_val("Leak.50", rec_idx) * 60.0
        day.leak_95 = get_val("Leak.95", rec_idx) * 60.0
        day.leak_max = get_val("Leak.Max", rec_idx) * 60.0

        # Pressure stats (cmH₂O)
        day.pressure_50 = get_val("MaskPress.50", rec_idx)
        day.pressure_95 = get_val("MaskPress.95", rec_idx)
        day.pressure_max = get_val("MaskPress.Max", rec_idx)

        # EPAP stats (cmH₂O)
        day.epap_50 = get_val("TgtEPAP.50", rec_idx)
        day.epap_95 = get_val("TgtEPAP.95", rec_idx)
        day.epap_max = get_val("TgtEPAP.Max", rec_idx)

        # Respiratory stats
        day.rr_50 = get_val("RespRate.50", rec_idx)
        day.rr_95 = get_val("RespRate.95", rec_idx)
        day.rr_max = get_val("RespRate.Max", rec_idx)
        day.mv_50 = get_val("MinVent.50", rec_idx)
        day.mv_95 = get_val("MinVent.95", rec_idx)
        day.mv_max = get_val("MinVent.Max", rec_idx)
        day.tv_50 = get_val("TidVol.50", rec_idx) * 1000.0  # L → mL
        day.tv_95 = get_val("TidVol.95", rec_idx) * 1000.0
        day.tv_max = get_val("TidVol.Max", rec_idx) * 1000.0

        # Settings (use AutoSet profile since this is an AS11 AutoSet)
        day.set_pressure = get_val("S.C.Press", rec_idx)
        day.min_pressure = get_val("S.A.MinPress", rec_idx)
        day.max_pressure = get_val("S.A.MaxPress", rec_idx)
        day.epr_level = int(get_val("S.EPR.Level", rec_idx))
        day.ramp_pressure = get_val("S.A.StartPress", rec_idx)
        day.ramp_time = int(get_val("S.RampTime", rec_idx))
        day.csr_percent = get_val("CSR", rec_idx)
        day.therapy_mode = int(get_val("Mode", rec_idx))

        summaries.append(day)

    return summaries


# ── Identification.json parser ────────────────────────────────────────────
def parse_identification(filepath: Union[str, Path]) -> dict:
    """Parse the Identification.json file from the SD card root."""
    path = Path(filepath)
    if not path.exists():
        return {}
    with open(path, "r") as f:
        data = json.load(f)

    # Navigate the nested ResMed structure
    fg = data.get("FlowGenerator", {})
    profiles = fg.get("IdentificationProfiles", {})
    product = profiles.get("Product", {})
    software = profiles.get("Software", {})

    result = {
        "serial_number": product.get("SerialNumber", ""),
        "product_name": product.get("ProductName", ""),
        "model_number": product.get("ProductCode", ""),
        "product_geographic_id": product.get("ProductGeographicIdentifier", ""),
        "software_version": software.get("DataModelVersionIdentifier", ""),
        "application_id": software.get("ApplicationIdentifier", ""),
        "platform_id": software.get("PlatformIdentifier", ""),
        "data_version": software.get("DataVersionIdentifier", ""),
    }

    return result


# ── CurrentSettings.json parser ──────────────────────────────────────────
def parse_settings(filepath: Union[str, Path]) -> dict:
    """Parse the SETTINGS/CurrentSettings.json file."""
    path = Path(filepath)
    if not path.exists():
        return {}
    with open(path, "r") as f:
        data = json.load(f)

    result = {}

    # Navigate ResMed nested structure
    fg = data.get("FlowGenerator", {})
    settings = fg.get("SettingProfiles", {})
    active = settings.get("ActiveProfiles", {})
    therapy = settings.get("TherapyProfiles", {})

    result["active_therapy_profile"] = active.get("TherapyProfile", "")
    result["feature_profiles"] = active.get("FeatureProfiles", [])

    # Find the active therapy profile's settings
    for profile_name, profile_data in therapy.items():
        if isinstance(profile_data, dict):
            # Extract settings from the profile
            attrs = profile_data.get("Attributes", {})
            params = profile_data.get("Parameters", profile_data.get("Settings", {}))
            
            # Flatten common parameters
            if isinstance(params, dict):
                for key, val in params.items():
                    if isinstance(val, (int, float, str, bool)):
                        result[key] = val
                    elif isinstance(val, dict) and "Value" in val:
                        result[key] = val["Value"]

    return result
