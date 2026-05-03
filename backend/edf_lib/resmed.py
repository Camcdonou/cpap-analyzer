"""
ResMed-specific signal processing and file type handling.

Ported from OSCAR's resmed_loader.cpp and resmed_EDFinfo.cpp.
Maps ResMed EDF signal labels to canonical channel names and applies
vendor-specific gain transformations.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Tuple

import numpy as np

from .edf_reader import EDFReader, EDFSignal, SignalDescriptor


# ── ResMed EDF file types ─────────────────────────────────────────────────
class ResMedFileType(Enum):
    BRP = "BRP"   # High-res breathing waveforms (Flow, Pressure, RespEvents)
    PLD = "PLD"   # Low-res summary data (Pressure, Leak, RR, MV, TV, Snore)
    EVE = "EVE"   # Event annotations (apneas, hypopneas)
    CSL = "CSL"   # Cheyne-Stokes Respiration
    SA2 = "SA2"   # AirSense 11 summary data
    STR = "STR"   # Daily summary statistics

    @classmethod
    def from_filename(cls, filename: str) -> Optional["ResMedFileType"]:
        """Extract file type from ResMed naming: YYYYMMDD_HHMMSS_{TYPE}.edf"""
        try:
            type_code = filename.rsplit("_", 1)[-1].split(".")[0].upper()
            return cls(type_code)
        except (ValueError, IndexError):
            return None


# ── Signal name mappings (from OSCAR resmed_loader.cpp setupResMedTranslationMap) ──
# Maps canonical channel names to possible EDF signal labels
# Multiple labels per channel account for language/locale variants

SIGNAL_MAP = {
    # ── BRP (high-res) signals ──
    "flow_rate": ["Flow", "Flow.40ms"],
    "mask_pressure_hi": ["Mask Pres", "MaskPress.40ms"],
    "resp_event": ["Resp Event", "TrigCycEvt.40ms"],

    # ── PLD (low-res) signals ──
    "snore": ["Snore", "Snore.2s"],
    "pressure": ["Therapy Pres", "Press.2s"],
    "ipap": ["Insp Pres", "IPAP", "S.BL.IPAP", "S.S.IPAP"],
    "epap": ["Exp Pres", "EprPress.2s", "EPAP", "S.BL.EPAP", "EPRPress.2s", "S.S.EPAP"],
    "minute_vent": ["MV", "VM", "MinVent.2s"],
    "resp_rate": ["RR", "AF", "FR", "RespRate.2s"],
    "tidal_volume": ["Vt", "VC", "TidVol.2s"],
    "leak": ["Leak", "Leck", "Fuites", "Leak.2s"],
    "flow_limitation": ["FFL Index", "FlowLim.2s"],
    "mask_pressure": ["Mask Pres", "MaskPress.2s"],
    "ie_ratio": ["I:E", "IERatio.2s"],
    "inspiratory_time": ["Ti", "B5ITime.2s"],
    "expiratory_time": ["Te", "B5ETime.2s"],
    "target_mv": ["TgMV", "TgtVent.2s"],

    # ── SAD/SA2 (oximetry) signals ──
    "pulse": ["Pulse", "Puls", "Pouls", "Pols", "Pulse.1s", "Nabiz"],
    "spo2": ["SpO2", "SpO2.1s"],

    # ── STR (daily summary) signals ──
    # These use different naming conventions (percentile-based)
    "str_leak_50": ["Leak Med", "Leak.50"],
    "str_leak_95": ["Leak 95", "Leak.95"],
    "str_leak_max": ["Leak Max", "Leak.Max"],
    "str_rr_50": ["RespRate.50", "RR Med"],
    "str_rr_95": ["RespRate.95", "RR 95"],
    "str_rr_max": ["RespRate.Max", "RR Max"],
    "str_mv_50": ["MinVent.50", "Min Vent Med"],
    "str_mv_95": ["MinVent.95", "Min Vent 95"],
    "str_mv_max": ["MinVent.Max", "Min Vent Max"],
    "str_tv_50": ["TidVol.50", "Tid Vol Med"],
    "str_tv_95": ["TidVol.95", "Tid Vol 95"],
    "str_tv_max": ["TidVol.Max", "Tid Vol Max"],
    "str_mp_50": ["MaskPress.50", "Mask Pres Med"],
    "str_mp_95": ["MaskPress.95", "Mask Pres 95"],
    "str_mp_max": ["MaskPress.Max", "Mask Pres Max"],
    "str_epap_50": ["TgtEPAP.50", "Exp Pres Med"],
    "str_epap_95": ["TgtEPAP.95", "Exp Pres 95"],
    "str_epap_max": ["TgtEPAP.Max", "Exp Pres Max"],
}


# ── Gain transformations (from OSCAR resmed_loader.cpp) ────────────────────
# Applied AFTER the standard EDF gain/offset conversion.
# key = canonical channel name, value = multiplier

GAIN_OVERRIDES = {
    "flow_rate": 60.0,     # L/s → L/min (OSCAR: es.gain *= 60.0)
    "leak": 60.0,          # L/s → L/min
    "tidal_volume": 1000.0,  # L → mL (OSCAR: gain * 1000.0)
    "ie_ratio": 1.0 / 100.0,  # encoded * 100 → ratio
    "str_leak_50": 60.0,
    "str_leak_95": 60.0,
    "str_leak_max": 60.0,
    "str_tv_50": 1000.0,
    "str_tv_95": 1000.0,
    "str_tv_max": 1000.0,
}

# Physical dimension overrides for display
UNIT_OVERRIDES = {
    "flow_rate": "L/min",
    "leak": "L/min",
    "tidal_volume": "mL",
    "ie_ratio": "",
    "pressure": "cmH₂O",
    "mask_pressure": "cmH₂O",
    "mask_pressure_hi": "cmH₂O",
    "epap": "cmH₂O",
    "ipap": "cmH₂O",
    "resp_rate": "breaths/min",
    "minute_vent": "L/min",
    "snore": "",
    "flow_limitation": "",
    "pulse": "bpm",
    "spo2": "%",
    "str_leak_50": "L/min",
    "str_leak_95": "L/min",
    "str_leak_max": "L/min",
}


# ── Event type mappings (from OSCAR LoadEVE) ─────────────────────────────
EVENT_TYPE_MAP = {
    "obstructive apnea": "OA",
    "hypopnea": "H",
    "apnea": "A",
    "central apnea": "CA",
    "arousal": "AR",
    "rera": "RERA",
    "spo2 desaturation": "SpO2Desat",
    "periodic breathing": "PB",
    "cheyne stokes": "CS",
}

# Reverse map for display
EVENT_TYPE_DISPLAY = {
    "OA": "Obstructive Apnea",
    "H": "Hypopnea",
    "A": "Apnea",
    "CA": "Central Apnea",
    "AR": "Arousal",
    "RERA": "RERA",
    "SpO2Desat": "SpO₂ Desaturation",
    "PB": "Periodic Breathing",
    "CS": "Cheyne-Stokes Respiration",
}


# ── Signal lookup ─────────────────────────────────────────────────────────
def lookup_signal(signals: List[EDFSignal], canonical_name: str) -> Optional[EDFSignal]:
    """
    Find a signal from parsed EDF data by canonical channel name.
    Checks all known ResMed label variants for that channel.
    """
    labels = SIGNAL_MAP.get(canonical_name, [])
    for label in labels:
        label_lower = label.lower()
        for sig in signals:
            if label_lower in sig.descriptor.label.lower():
                return sig
    return None


def apply_gain_override(canonical_name: str, data: np.ndarray) -> np.ndarray:
    """Apply ResMed-specific gain override to already-converted physical data."""
    multiplier = GAIN_OVERRIDES.get(canonical_name, 1.0)
    if multiplier != 1.0:
        return data * multiplier
    return data


def classify_event(text: str) -> str:
    """Classify an EVE annotation text into a canonical event type."""
    text_lower = text.lower().strip()
    for key, code in EVENT_TYPE_MAP.items():
        if key in text_lower:
            return code
    return "UNK"


# ── Parsed result types ──────────────────────────────────────────────────
@dataclass
class ParsedEvent:
    """A single sleep event (apnea, hypopnea, etc.)."""
    event_type: str       # OA, CA, H, AR, etc.
    onset: float          # seconds from session start
    duration: float       # seconds
    raw_text: str


@dataclass
class ParsedSignal:
    """A processed signal ready for storage/charting."""
    name: str             # canonical name (e.g., "flow_rate")
    data: np.ndarray      # physical values
    sampling_rate: float  # samples per second
    unit: str              # display unit

    def downsample(self, target_seconds: float) -> "ParsedSignal":
        """Downsample by averaging groups of samples."""
        if self.sampling_rate <= 1.0 / target_seconds:
            return self

        window = int(self.sampling_rate * target_seconds)
        n = len(self.data) // window * window
        if n == 0:
            return self

        trimmed = self.data[:n]
        reshaped = trimmed.reshape(-1, window)
        means = reshaped.mean(axis=1)

        return ParsedSignal(
            name=self.name,
            data=means,
            sampling_rate=1.0 / target_seconds,
            unit=self.unit,
        )

    def to_json(self) -> dict:
        """Serialize for API responses (float32 for size)."""
        return {
            "name": self.name,
            "values": self.data.astype(np.float32).tolist(),
            "sampling_rate": self.sampling_rate,
            "unit": self.unit,
        }
