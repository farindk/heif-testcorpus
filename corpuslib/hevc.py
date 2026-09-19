"""Just enough HEVC (ISO/IEC 23008-2) bitstream inspection for corrections.

Only NAL unit headers are read. Nothing here decodes slice data.
"""

from __future__ import annotations

from typing import List

NAL_NAMES = {
    0: "TRAIL_N", 1: "TRAIL_R", 2: "TSA_N", 3: "TSA_R", 4: "STSA_N", 5: "STSA_R",
    6: "RADL_N", 7: "RADL_R", 8: "RASL_N", 9: "RASL_R",
    16: "BLA_W_LP", 17: "BLA_W_RADL", 18: "BLA_N_LP", 19: "IDR_W_RADL", 20: "IDR_N_LP",
    21: "CRA_NUT", 32: "VPS_NUT", 33: "SPS_NUT", 34: "PPS_NUT", 35: "AUD_NUT",
    39: "PREFIX_SEI_NUT", 40: "SUFFIX_SEI_NUT",
}

# nal_unit_type values of intra random access point pictures (BLA, IDR, CRA
# and the reserved IRAP range 22..23).
IRAP_TYPES = set(range(16, 24))


def nal_unit_types(sample: bytes, length_size: int) -> List[int]:
    """NAL unit types of a length-prefixed sample ('hvc1'/'hev1' storage)."""
    types = []
    p = 0
    while p + length_size <= len(sample):
        n = int.from_bytes(sample[p:p + length_size], "big")
        p += length_size
        if n == 0 or p + n > len(sample):
            raise ValueError(f"invalid NAL unit length {n} at byte {p - length_size}")
        types.append((sample[p] >> 1) & 0x3F)
        p += n
    if p != len(sample):
        raise ValueError(f"{len(sample) - p} trailing bytes after the last NAL unit")
    return types


def is_irap_sample(sample: bytes, length_size: int) -> bool:
    """True when the sample contains a VCL NAL unit of an IRAP picture."""
    return any(t in IRAP_TYPES for t in nal_unit_types(sample, length_size))


def hvcc_length_size(hvcc_payload: bytes) -> int:
    """NAL unit length field size from an HEVCDecoderConfigurationRecord."""
    if len(hvcc_payload) < 22:
        raise ValueError("truncated 'hvcC'")
    return (hvcc_payload[21] & 0x3) + 1
