"""Just enough HEVC (ISO/IEC 23008-2) bitstream inspection for corrections
and for storing an encoded picture in a file.

Only NAL unit headers and the start of the SPS are read. Nothing here
decodes slice data.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple

NAL_VPS = 32
NAL_SPS = 33
NAL_PPS = 34

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


# --- storing the output of an encoder

def split_byte_stream(stream: bytes) -> List[bytes]:
    """NAL units of a byte stream (Annex B), without start codes."""
    nals = []
    p = stream.find(b"\x00\x00\x01")
    while p >= 0:
        start = p + 3
        p = stream.find(b"\x00\x00\x01", start)
        end = len(stream) if p < 0 else p
        nal = stream[start:end]
        # zero bytes in front of the next start code (zero_byte, trailing_zero_8bits)
        # are not part of the NAL unit, which always ends in a non-zero byte
        nals.append(nal.rstrip(b"\x00"))
    if not nals:
        raise ValueError("no start code found")
    return nals


def unescape_rbsp(payload: bytes) -> bytes:
    """Remove the emulation prevention bytes (7.4.2) from a NAL unit payload."""
    out = bytearray()
    zeros = 0
    for b in payload:
        if zeros >= 2 and b == 3:
            zeros = 0
            continue
        out.append(b)
        zeros = zeros + 1 if b == 0 else 0
    return bytes(out)


class _BitReader:
    def __init__(self, data: bytes, bit_position: int = 0) -> None:
        self.data = data
        self.pos = bit_position

    def u(self, nbits: int) -> int:
        value = 0
        for _ in range(nbits):
            if self.pos >= 8 * len(self.data):
                raise ValueError("read beyond the end of the NAL unit")
            value = (value << 1) | ((self.data[self.pos // 8] >> (7 - self.pos % 8)) & 1)
            self.pos += 1
        return value

    def ue(self) -> int:
        zeros = 0
        while self.u(1) == 0:
            zeros += 1
        return (1 << zeros) - 1 + self.u(zeros)


@dataclass(frozen=True)
class SpsInfo:
    profile_tier_level: bytes  # general_profile_space ... general_level_idc, 12 bytes
    num_temporal_layers: int
    temporal_id_nested: int
    chroma_format_idc: int
    width: int                 # coded size, before the conformance window is applied
    height: int
    bit_depth_luma: int
    bit_depth_chroma: int
    # conformance window offsets in luma samples: left, right, top, bottom
    conformance_window: Tuple[int, int, int, int] = (0, 0, 0, 0)

    @property
    def cropped_width(self) -> int:
        """Width of the output picture, after the conformance window is applied."""
        return self.width - self.conformance_window[0] - self.conformance_window[1]

    @property
    def cropped_height(self) -> int:
        return self.height - self.conformance_window[2] - self.conformance_window[3]


def parse_sps(sps_nal: bytes) -> SpsInfo:
    """Read an SPS up to the bit depths (7.3.2.2). Streams with temporal
    sub-layers are not supported."""
    if (sps_nal[0] >> 1) & 0x3F != NAL_SPS:
        raise ValueError("not an SPS")
    rbsp = unescape_rbsp(sps_nal[2:])

    max_sub_layers_minus1 = (rbsp[0] >> 1) & 7
    if max_sub_layers_minus1 != 0:
        raise ValueError("SPS with temporal sub-layers is not supported")

    r = _BitReader(rbsp, 8 * 13)  # behind profile_tier_level()
    r.ue()                        # sps_seq_parameter_set_id
    chroma_format_idc = r.ue()
    if chroma_format_idc == 3:
        r.u(1)                    # separate_colour_plane_flag
    width = r.ue()
    height = r.ue()
    window = (0, 0, 0, 0)
    if r.u(1):                    # conformance_window_flag
        # The offsets are coded in units of chroma samples (SubWidthC, SubHeightC).
        sub_width = 2 if chroma_format_idc in (1, 2) else 1
        sub_height = 2 if chroma_format_idc == 1 else 1
        left, right, top, bottom = r.ue(), r.ue(), r.ue(), r.ue()
        window = (left * sub_width, right * sub_width, top * sub_height, bottom * sub_height)
    bit_depth_luma = 8 + r.ue()
    bit_depth_chroma = 8 + r.ue()

    return SpsInfo(rbsp[1:13], max_sub_layers_minus1 + 1, rbsp[0] & 1,
                   chroma_format_idc, width, height, bit_depth_luma, bit_depth_chroma, window)


def make_hvcC_payload(vps: bytes, sps: bytes, pps: bytes) -> bytes:
    """HEVCDecoderConfigurationRecord (ISO/IEC 14496-15:2022, 8.3.2.1) with
    4 byte NAL unit length fields.

    bit_depth_luma_minus8 and bit_depth_chroma_minus8 are 3 bit fields, so
    the record can signal at most 15 bits. HEVC allows 16 bits, but there is
    no correct record for such a stream, and it is refused."""
    info = parse_sps(sps)
    if max(info.bit_depth_luma, info.bit_depth_chroma) > 15:
        raise ValueError("'hvcC' cannot signal a bit depth of more than 15 bits")

    out = bytearray([1])                                  # configurationVersion
    out += info.profile_tier_level
    out += (0xF000 | 0).to_bytes(2, "big")                # min_spatial_segmentation_idc
    out.append(0xFC | 0)                                  # parallelismType: unknown
    out.append(0xFC | info.chroma_format_idc)
    out.append(0xF8 | (info.bit_depth_luma - 8))
    out.append(0xF8 | (info.bit_depth_chroma - 8))
    out += (0).to_bytes(2, "big")                         # avgFrameRate: unspecified
    # constantFrameRate 0, numTemporalLayers, temporalIdNested, lengthSizeMinusOne 3
    out.append((info.num_temporal_layers << 3) | (info.temporal_id_nested << 2) | 3)

    out.append(3)                                         # numOfArrays
    for nal_type, nal in ((NAL_VPS, vps), (NAL_SPS, sps), (NAL_PPS, pps)):
        if (nal[0] >> 1) & 0x3F != nal_type:
            raise ValueError(f"expected NAL unit type {nal_type}")
        out.append(0x80 | nal_type)                       # array_completeness 1
        out += (1).to_bytes(2, "big")                     # numNalus
        out += len(nal).to_bytes(2, "big") + nal
    return bytes(out)


def split_parameter_sets(nals: List[bytes]) -> Tuple[bytes, bytes, bytes, bytes]:
    """Return (vps, sps, pps, sample) for the NAL units of one coded picture:
    the three parameter sets and everything else with 4 byte length fields,
    as stored in an 'hvc1' item."""
    sets = {}
    sample = bytearray()
    for nal in nals:
        nal_type = (nal[0] >> 1) & 0x3F
        if nal_type in (NAL_VPS, NAL_SPS, NAL_PPS):
            if nal_type in sets:
                raise ValueError(f"more than one {NAL_NAMES[nal_type]}")
            sets[nal_type] = nal
        else:
            sample += len(nal).to_bytes(4, "big") + nal
    if len(sets) != 3:
        raise ValueError("stream lacks a VPS, SPS or PPS")
    return sets[NAL_VPS], sets[NAL_SPS], sets[NAL_PPS], bytes(sample)
