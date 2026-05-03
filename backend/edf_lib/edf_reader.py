"""
EDF/EDF+ file reader — Python port of OSCAR's edfparser.cpp

Reads European Data Format files used by ResMed CPAP machines.
Supports EDF+ with annotations.

Reference: http://edfplus.info/specs/edf.html
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import BinaryIO, List, Optional, Tuple

import numpy as np


# ── Constants ──────────────────────────────────────────────────────────────
EDF_HEADER_SIZE = 256
SIGNAL_DESCRIPTOR_SIZE = 96  # bytes per signal in header


# ── Data structures ───────────────────────────────────────────────────────
@dataclass
class EDFHeader:
    """Fixed 256-byte EDF/EDF+ header."""
    version: str
    patient_id: str
    recording_id: str
    start_date: str       # DD.MM.yy
    start_time: str       # HH.MM.SS
    num_bytes_header: int
    reserved: str
    num_data_records: int
    duration_per_record: float  # seconds
    num_signals: int

    @property
    def datetime(self) -> datetime:
        return datetime.strptime(
            f"{self.start_date}{self.start_time}",
            "%d.%m.%y%H.%M.%S",
        )


@dataclass
class SignalDescriptor:
    """96-byte signal descriptor from EDF header."""
    label: str
    transducer_type: str
    physical_dimension: str
    physical_min: float
    physical_max: float
    digital_min: int
    digital_max: int
    prefiltering: str
    samples_per_record: int
    reserved: str

    @property
    def gain(self) -> float:
        dig_range = self.digital_max - self.digital_min
        if dig_range == 0:
            return 1.0
        return (self.physical_max - self.physical_min) / dig_range

    @property
    def offset(self) -> float:
        return self.physical_min - self.digital_min * self.gain

    @property
    def is_annotation(self) -> bool:
        return "annotation" in self.label.lower() or self.label.strip() == "EDF Annotations"


@dataclass
class Annotation:
    """A single EDF+ annotation."""
    onset: float        # seconds from record start
    duration: float      # seconds (-1 if not specified)
    text: str


@dataclass
class EDFSignal:
    """Parsed signal with metadata and data array."""
    descriptor: SignalDescriptor
    data: np.ndarray  # physical values (float64)


# ── Reader ─────────────────────────────────────────────────────────────────
class EDFReader:
    """
    Read and parse EDF/EDF+ files.

    Usage:
        reader = EDFReader.from_file("20250926_231956_BRP.edf")
        header = reader.header
        signals = reader.parse_signals()
        annotations = reader.parse_annotations()
    """

    def __init__(self, data: bytes, filepath: Optional[str] = None):
        self._data = data
        self.filepath = filepath
        self._pos = 0
        self.header: Optional[EDFHeader] = None
        self.signals: List[SignalDescriptor] = []
        self._parsed = False

    # ── Factory ────────────────────────────────────────────────────────────
    @classmethod
    def from_file(cls, path: str | Path) -> "EDFReader":
        path = Path(path)
        data = path.read_bytes()
        return cls(data, filepath=str(path))

    @classmethod
    def from_bytes(cls, data: bytes, filepath: Optional[str] = None) -> "EDFReader":
        return cls(data, filepath=filepath)

    # ── Header parsing ────────────────────────────────────────────────────
    def parse_header(self) -> EDFHeader:
        """Parse the 256-byte fixed header."""
        d = self._data
        if len(d) < EDF_HEADER_SIZE:
            raise ValueError(f"File too small for EDF header: {len(d)} bytes")

        self.header = EDFHeader(
            version=d[0:8].decode("ascii", errors="replace").strip(),
            patient_id=d[8:88].decode("ascii", errors="replace").strip(),
            recording_id=d[88:168].decode("ascii", errors="replace").strip(),
            start_date=d[168:176].decode("ascii", errors="replace").strip(),
            start_time=d[176:184].decode("ascii", errors="replace").strip(),
            num_bytes_header=int(d[184:192].decode("ascii", errors="replace").strip() or "0"),
            reserved=d[192:236].decode("ascii", errors="replace"),
            num_data_records=int(d[236:244].decode("ascii", errors="replace").strip() or "0"),
            duration_per_record=float(d[244:252].decode("ascii", errors="replace").strip() or "0"),
            num_signals=int(d[252:256].decode("ascii", errors="replace").strip() or "0"),
        )
        return self.header

    def parse_signal_descriptors(self) -> List[SignalDescriptor]:
        """
        Parse signal descriptors after the fixed header.

        EDF stores signal descriptors in column-major order:
        all labels, then all transducer types, etc.
        """
        if self.header is None:
            self.parse_header()

        n = self.header.num_signals
        if n == 0:
            self.signals = []
            return self.signals

        offset = EDF_HEADER_SIZE
        d = self._data

        def read_field(field_size: int) -> List[str]:
            """Read n fields of field_size bytes each, packed column-major."""
            fields = []
            for i in range(n):
                start = offset + i * field_size
                raw = d[start:start + field_size].decode("ascii", errors="replace").strip()
                fields.append(raw)
            return fields

        # Column-major: all labels first, then all transducers, etc.
        labels = read_field(16);          offset += n * 16
        transducers = read_field(80);     offset += n * 80
        dimensions = read_field(8);       offset += n * 8
        phys_mins = read_field(8);       offset += n * 8
        phys_maxs = read_field(8);       offset += n * 8
        dig_mins = read_field(8);        offset += n * 8
        dig_maxs = read_field(8);        offset += n * 8
        prefilterings = read_field(80);  offset += n * 80
        sample_counts = read_field(8);   offset += n * 8
        reserveds = read_field(32)       # offset += n * 32  # last group

        self.signals = []
        for i in range(n):
            desc = SignalDescriptor(
                label=labels[i],
                transducer_type=transducers[i],
                physical_dimension=dimensions[i],
                physical_min=float(phys_mins[i] or "0"),
                physical_max=float(phys_maxs[i] or "0"),
                digital_min=int(dig_mins[i] or "0"),
                digital_max=int(dig_maxs[i] or "0"),
                prefiltering=prefilterings[i],
                samples_per_record=int(sample_counts[i] or "0"),
                reserved=reserveds[i],
            )
            self.signals.append(desc)

        return self.signals

    # ── Signal data parsing ───────────────────────────────────────────────
    def parse_signals(self) -> List[EDFSignal]:
        """
        Parse all signal data records, returning physical values.
        """
        if not self.signals:
            self.parse_signal_descriptors()

        n_records = self.header.num_data_records
        n_signals = self.header.num_signals

        # Data starts after header + signal descriptors
        data_offset = self.header.num_bytes_header

        # Calculate total samples per record (for seeking)
        total_samples_per_record = sum(s.samples_per_record for s in self.signals)
        record_bytes = total_samples_per_record * 2  # 16-bit per sample

        # Read all data at once
        data_start = data_offset
        data_end = data_start + n_records * record_bytes
        raw_bytes = self._data[data_start:data_end]

        if len(raw_bytes) < n_records * record_bytes:
            # Truncated file — parse what we can
            n_records = len(raw_bytes) // record_bytes

        # Parse as little-endian int16 (x86 native)
        raw_ints = np.frombuffer(raw_bytes, dtype="<i2")

        # Reshape: (n_records, total_samples_per_record)
        if total_samples_per_record > 0 and n_records > 0:
            raw_ints = raw_ints.reshape(n_records, total_samples_per_record)
        else:
            return []

        # Split into individual signals and apply gain/offset
        result = []
        col = 0
        for desc in self.signals:
            n_samples = desc.samples_per_record
            if n_samples == 0:
                result.append(EDFSignal(descriptor=desc, data=np.array([], dtype=np.float64)))
                continue

            signal_ints = raw_ints[:, col:col + n_samples].flatten()
            physical = signal_ints.astype(np.float64) * desc.gain + desc.offset
            result.append(EDFSignal(descriptor=desc, data=physical))
            col += n_samples

        self._parsed = True
        return result

    # ── Annotation parsing ────────────────────────────────────────────────
    def parse_annotations(self) -> List[Annotation]:
        """
        Parse EDF+ annotation signals.

        Annotation format:
        [onset]\x15[duration]\x14[text]\x14...

        onset:   +/-seconds (float)
        duration: seconds (float, optional)
        text:    UTF-8 string
        \x14 (20) separates fields
        \x15 (21) separates onset from duration
        """
        if not self.signals:
            self.parse_signal_descriptors()

        annotations = []
        n_records = self.header.num_data_records
        data_offset = self.header.num_bytes_header

        # Find annotation signals
        annotation_indices = [
            i for i, s in enumerate(self.signals) if s.is_annotation
        ]

        if not annotation_indices:
            return annotations

        # Calculate sample offsets for interleaved data
        total_samples_per_record = sum(s.samples_per_record for s in self.signals)
        record_bytes = total_samples_per_record * 2

        for rec_no in range(n_records):
            record_offset = data_offset + rec_no * record_bytes

            for sig_idx in annotation_indices:
                # Calculate byte offset for this signal in this record
                sample_offset = sum(
                    self.signals[i].samples_per_record
                    for i in range(sig_idx)
                )
                byte_offset = record_offset + sample_offset * 2
                n_bytes = self.signals[sig_idx].samples_per_record * 2

                if byte_offset + n_bytes > len(self._data):
                    break

                ann_bytes = self._data[byte_offset:byte_offset + n_bytes]
                parsed = self._parse_annotation_record(ann_bytes)
                annotations.extend(parsed)

        return annotations

    def _parse_annotation_record(self, data: bytes) -> List[Annotation]:
        """Parse a single annotation record from raw bytes."""
        annotations = []
        try:
            text = data.decode("latin-1")
        except Exception:
            return annotations

        pos = 0
        length = len(text)

        while pos < length:
            # Skip padding NULs and TAL start markers
            while pos < length and text[pos] in ("\x00", "\x14", "\x15"):
                pos += 1

            if pos >= length:
                break

            # Parse onset (optional +/- sign, then digits and decimal)
            onset_str = ""
            while pos < length and text[pos] not in ("\x14", "\x15", "\x00"):
                onset_str += text[pos]
                pos += 1

            if not onset_str.strip():
                continue

            try:
                onset = float(onset_str.strip())
            except ValueError:
                continue

            # Parse optional duration
            duration = -1.0
            if pos < length and text[pos] == "\x15":
                pos += 1  # skip \x15
                dur_str = ""
                while pos < length and text[pos] not in ("\x14", "\x00"):
                    dur_str += text[pos]
                    pos += 1
                try:
                    duration = float(dur_str.strip())
                except ValueError:
                    duration = -1.0

            # Parse text(s) — multiple texts can follow, separated by \x14
            while pos < length and text[pos] != "\x00":
                if text[pos] == "\x14":
                    pos += 1
                    continue

                ann_text = ""
                while pos < length and text[pos] not in ("\x14", "\x00"):
                    ann_text += text[pos]
                    pos += 1

                ann_text = ann_text.strip()
                if ann_text:
                    annotations.append(Annotation(
                        onset=onset,
                        duration=duration,
                        text=ann_text,
                    ))

            if pos < length and text[pos] == "\x00":
                pos += 1

        return annotations

    # ── Convenience ──────────────────────────────────────────────────────
    def get_signal_by_label(self, label: str, signals: Optional[List[EDFSignal]] = None) -> Optional[EDFSignal]:
        """Find a signal by its label (case-insensitive partial match)."""
        if signals is None:
            signals = self.parse_signals()

        label_lower = label.lower()
        for sig in signals:
            if label_lower in sig.descriptor.label.lower():
                return sig
        return None

    def get_signals_by_labels(self, labels: List[str], signals: Optional[List[EDFSignal]] = None) -> dict:
        """Find multiple signals by labels. Returns {label: EDFSignal}."""
        if signals is None:
            signals = self.parse_signals()

        result = {}
        for search_label in labels:
            sig = self.get_signal_by_label(search_label, signals)
            if sig is not None:
                result[search_label] = sig
        return result
