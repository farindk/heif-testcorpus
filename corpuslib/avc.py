"""Minimal AVC (ISO/IEC 14496-10) intra picture writer.

Writes a picture as one IDR slice that consists of I_PCM macroblocks only.
An I_PCM macroblock carries its samples uncompressed at the coded bit depth,
so no prediction, transform or entropy coding of residuals is needed, the
picture is lossless, and every decoded sample is known in advance. This
makes it possible to produce bit depths and chroma formats that the common
encoders do not offer (x264 encodes 8 and 10 bits only).

The output is the three NAL units (SPS, PPS, IDR slice) without start codes
or length fields. Emulation prevention bytes are inserted.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Sequence

NAL_SLICE_IDR = 5
NAL_SPS = 7
NAL_PPS = 8

CHROMA_400 = 0
CHROMA_420 = 1
CHROMA_422 = 2
CHROMA_444 = 3

PROFILE_HIGH = 100
PROFILE_HIGH_10 = 110
PROFILE_HIGH_422 = 122
PROFILE_HIGH_444_PREDICTIVE = 244

# An I_PCM picture is larger than the uncompressed 8 bit 4:2:0 picture that
# the level limits on the access unit size are derived from (A.3.3, MinCR).
# The limit grows with the macroblock rate of the level, so a small picture
# only fits at a high level. Level 5.1 holds up to 36864 macroblocks.
LEVEL_IDC = 51
MAX_FRAME_SIZE_IN_MBS = 36864

MB_TYPE_I_PCM = 25  # Table 7-11, mb_type of I_PCM in I slices
SLICE_TYPE_I_ALL = 7  # I slice, and all other slices of the picture are I slices too


class BitWriter:
    def __init__(self) -> None:
        self._data = bytearray()
        self._acc = 0
        self._nbits = 0

    def u(self, nbits: int, value: int) -> None:
        if value < 0 or value >> nbits:
            raise ValueError(f"{value} does not fit into {nbits} bits")
        self._acc = (self._acc << nbits) | value
        self._nbits += nbits
        while self._nbits >= 8:
            self._nbits -= 8
            self._data.append((self._acc >> self._nbits) & 0xFF)
        self._acc &= (1 << self._nbits) - 1

    def ue(self, value: int) -> None:
        """Unsigned Exp-Golomb code (9.1)."""
        if value < 0:
            raise ValueError("ue(v) cannot code a negative value")
        nbits = (value + 1).bit_length()
        self.u(2 * nbits - 1, value + 1)

    def se(self, value: int) -> None:
        """Signed Exp-Golomb code (9.1.1)."""
        self.ue(2 * value - 1 if value > 0 else -2 * value)

    @property
    def byte_aligned(self) -> bool:
        return self._nbits == 0

    def align_with_zero_bits(self) -> None:
        if self._nbits:
            self.u(8 - self._nbits, 0)

    def write_bytes(self, data: bytes) -> None:
        if not self.byte_aligned:
            raise ValueError("write_bytes() needs a byte aligned position")
        self._data += data

    def rbsp_trailing_bits(self) -> None:
        self.u(1, 1)
        self.align_with_zero_bits()

    def getvalue(self) -> bytes:
        if not self.byte_aligned:
            raise ValueError("bitstream does not end on a byte boundary")
        return bytes(self._data)


def escape_rbsp(rbsp: bytes) -> bytes:
    """Insert emulation prevention bytes (7.4.1): within a NAL unit, two zero
    bytes must not be followed by a byte of value 0 to 3."""
    out = bytearray()
    zeros = 0
    for b in rbsp:
        if zeros >= 2 and b <= 3:
            out.append(3)
            zeros = 0
        out.append(b)
        zeros = zeros + 1 if b == 0 else 0
    return bytes(out)


def make_nal(nal_ref_idc: int, nal_unit_type: int, rbsp: bytes) -> bytes:
    return bytes([(nal_ref_idc << 5) | nal_unit_type]) + escape_rbsp(rbsp)


@dataclass(frozen=True)
class Picture:
    """Planes in coding order: Y, or Y Cb Cr. Every plane is a list of rows.
    With matrix_coefficients 0 (identity) the planes hold G, B and R."""
    width: int
    height: int
    bit_depth: int
    chroma_format_idc: int
    planes: Sequence[Sequence[Sequence[int]]]

    @property
    def chroma_width(self) -> int:
        return self.width // (1 if self.chroma_format_idc == CHROMA_444 else 2)

    @property
    def chroma_height(self) -> int:
        return self.height // (2 if self.chroma_format_idc == CHROMA_420 else 1)

    def validate(self) -> None:
        if not 8 <= self.bit_depth <= 14:
            raise ValueError("AVC codes 8 to 14 bits per sample")
        if self.chroma_format_idc not in (CHROMA_400, CHROMA_420, CHROMA_422, CHROMA_444):
            raise ValueError("invalid chroma_format_idc")
        if self.width <= 0 or self.height <= 0 or self.width % 16 or self.height % 16:
            raise ValueError("picture size must be a multiple of the macroblock size 16 (no cropping support)")
        if (self.width // 16) * (self.height // 16) > MAX_FRAME_SIZE_IN_MBS:
            raise ValueError("picture exceeds the frame size of level 5.1")

        sizes = [(self.width, self.height)]
        if self.chroma_format_idc != CHROMA_400:
            sizes += [(self.chroma_width, self.chroma_height)] * 2
        if len(self.planes) != len(sizes):
            raise ValueError(f"expected {len(sizes)} planes, got {len(self.planes)}")
        limit = 1 << self.bit_depth
        for plane, (w, h) in zip(self.planes, sizes):
            if len(plane) != h or any(len(row) != w for row in plane):
                raise ValueError(f"plane is not {w}x{h}")
            if any(not 0 <= v < limit for row in plane for v in row):
                raise ValueError(f"sample outside of the {self.bit_depth} bit range")


@dataclass(frozen=True)
class ColourDescription:
    """Code points of ISO/IEC 23091-2 as written to the VUI."""
    colour_primaries: int
    transfer_characteristics: int
    matrix_coefficients: int
    full_range: bool


@dataclass(frozen=True)
class CodedPicture:
    profile_idc: int
    constraint_flags: int
    level_idc: int
    chroma_format_idc: int
    bit_depth: int
    sps: bytes
    pps: bytes
    slice: bytes

    def annexb(self) -> bytes:
        """Byte stream format (Annex B), as read by stand-alone decoders."""
        return b"".join(b"\x00\x00\x00\x01" + nal for nal in (self.sps, self.pps, self.slice))


def profile_for(chroma_format_idc: int, bit_depth: int) -> int:
    """The lowest profile that codes this chroma format and bit depth."""
    if chroma_format_idc == CHROMA_444 or bit_depth > 10:
        return PROFILE_HIGH_444_PREDICTIVE
    if chroma_format_idc == CHROMA_422:
        return PROFILE_HIGH_422
    return PROFILE_HIGH_10 if bit_depth > 8 else PROFILE_HIGH


def _write_sps(pic: Picture, profile_idc: int, colour: ColourDescription) -> bytes:
    w = BitWriter()
    w.u(8, profile_idc)
    w.u(8, 0)                     # constraint_set0..5_flag, reserved_zero_2bits
    w.u(8, LEVEL_IDC)
    w.ue(0)                       # seq_parameter_set_id
    w.ue(pic.chroma_format_idc)
    if pic.chroma_format_idc == CHROMA_444:
        w.u(1, 0)                 # separate_colour_plane_flag
    w.ue(pic.bit_depth - 8)       # bit_depth_luma_minus8
    w.ue(pic.bit_depth - 8)       # bit_depth_chroma_minus8
    w.u(1, 0)                     # qpprime_y_zero_transform_bypass_flag
    w.u(1, 0)                     # seq_scaling_matrix_present_flag
    w.ue(0)                       # log2_max_frame_num_minus4
    w.ue(2)                       # pic_order_cnt_type: output order is decoding order
    w.ue(0)                       # max_num_ref_frames
    w.u(1, 0)                     # gaps_in_frame_num_value_allowed_flag
    w.ue(pic.width // 16 - 1)     # pic_width_in_mbs_minus1
    w.ue(pic.height // 16 - 1)    # pic_height_in_map_units_minus1
    w.u(1, 1)                     # frame_mbs_only_flag
    w.u(1, 1)                     # direct_8x8_inference_flag
    w.u(1, 0)                     # frame_cropping_flag
    w.u(1, 1)                     # vui_parameters_present_flag

    # --- vui_parameters() (E.1.1)
    w.u(1, 0)                     # aspect_ratio_info_present_flag
    w.u(1, 0)                     # overscan_info_present_flag
    w.u(1, 1)                     # video_signal_type_present_flag
    w.u(3, 5)                     # video_format: unspecified
    w.u(1, 1 if colour.full_range else 0)  # video_full_range_flag
    w.u(1, 1)                     # colour_description_present_flag
    w.u(8, colour.colour_primaries)
    w.u(8, colour.transfer_characteristics)
    w.u(8, colour.matrix_coefficients)
    w.u(1, 0)                     # chroma_loc_info_present_flag
    w.u(1, 0)                     # timing_info_present_flag
    w.u(1, 0)                     # nal_hrd_parameters_present_flag
    w.u(1, 0)                     # vcl_hrd_parameters_present_flag
    w.u(1, 0)                     # pic_struct_present_flag
    w.u(1, 1)                     # bitstream_restriction_flag
    w.u(1, 1)                     # motion_vectors_over_pic_boundaries_flag
    w.ue(0)                       # max_bytes_per_pic_denom: no limit
    w.ue(0)                       # max_bits_per_mb_denom: no limit
    w.ue(16)                      # log2_max_mv_length_horizontal
    w.ue(16)                      # log2_max_mv_length_vertical
    w.ue(0)                       # max_num_reorder_frames
    w.ue(0)                       # max_dec_frame_buffering

    w.rbsp_trailing_bits()
    return make_nal(3, NAL_SPS, w.getvalue())


def _write_pps() -> bytes:
    w = BitWriter()
    w.ue(0)                       # pic_parameter_set_id
    w.ue(0)                       # seq_parameter_set_id
    w.u(1, 0)                     # entropy_coding_mode_flag: CAVLC
    w.u(1, 0)                     # bottom_field_pic_order_in_frame_present_flag
    w.ue(0)                       # num_slice_groups_minus1
    w.ue(0)                       # num_ref_idx_l0_default_active_minus1
    w.ue(0)                       # num_ref_idx_l1_default_active_minus1
    w.u(1, 0)                     # weighted_pred_flag
    w.u(2, 0)                     # weighted_bipred_idc
    w.se(0)                       # pic_init_qp_minus26
    w.se(0)                       # pic_init_qs_minus26
    w.se(0)                       # chroma_qp_index_offset
    w.u(1, 1)                     # deblocking_filter_control_present_flag
    w.u(1, 0)                     # constrained_intra_pred_flag
    w.u(1, 0)                     # redundant_pic_cnt_present_flag
    w.rbsp_trailing_bits()
    return make_nal(3, NAL_PPS, w.getvalue())


def _pack_samples(samples: List[int], bit_depth: int) -> bytes:
    acc = 0
    for v in samples:
        acc = (acc << bit_depth) | v
    nbits = len(samples) * bit_depth
    if nbits % 8:
        raise ValueError("PCM samples of a macroblock do not end on a byte boundary")
    return acc.to_bytes(nbits // 8, "big")


def _write_idr_slice(pic: Picture) -> bytes:
    w = BitWriter()

    # --- slice_header() (7.3.3)
    w.ue(0)                       # first_mb_in_slice
    w.ue(SLICE_TYPE_I_ALL)        # slice_type
    w.ue(0)                       # pic_parameter_set_id
    w.u(4, 0)                     # frame_num, log2_max_frame_num bits
    w.ue(0)                       # idr_pic_id
    w.u(1, 0)                     # no_output_of_prior_pics_flag
    w.u(1, 0)                     # long_term_reference_flag
    w.se(0)                       # slice_qp_delta
    w.ue(1)                       # disable_deblocking_filter_idc: off

    # --- slice_data() (7.3.4) with macroblock_layer() (7.3.5)
    has_chroma = pic.chroma_format_idc != CHROMA_400
    mb_width_c = 16 * pic.chroma_width // pic.width if has_chroma else 0
    mb_height_c = 16 * pic.chroma_height // pic.height if has_chroma else 0

    for mb_y in range(pic.height // 16):
        for mb_x in range(pic.width // 16):
            w.ue(MB_TYPE_I_PCM)
            w.align_with_zero_bits()  # pcm_alignment_zero_bit

            samples: List[int] = []
            for row in pic.planes[0][16 * mb_y:16 * (mb_y + 1)]:
                samples += row[16 * mb_x:16 * (mb_x + 1)]
            for plane in pic.planes[1:]:
                for row in plane[mb_height_c * mb_y:mb_height_c * (mb_y + 1)]:
                    samples += row[mb_width_c * mb_x:mb_width_c * (mb_x + 1)]
            w.write_bytes(_pack_samples(samples, pic.bit_depth))

    w.rbsp_trailing_bits()
    return make_nal(3, NAL_SLICE_IDR, w.getvalue())


def encode_ipcm_picture(pic: Picture, colour: ColourDescription) -> CodedPicture:
    pic.validate()
    profile_idc = profile_for(pic.chroma_format_idc, pic.bit_depth)
    return CodedPicture(
        profile_idc=profile_idc,
        constraint_flags=0,
        level_idc=LEVEL_IDC,
        chroma_format_idc=pic.chroma_format_idc,
        bit_depth=pic.bit_depth,
        sps=_write_sps(pic, profile_idc, colour),
        pps=_write_pps(),
        slice=_write_idr_slice(pic))


def make_avcC_payload(coded: CodedPicture) -> bytes:
    """AVCDecoderConfigurationRecord (ISO/IEC 14496-15, 5.3.3.1) with 4 byte
    NAL unit length fields."""
    out = bytearray()
    out += bytes([1, coded.profile_idc, coded.constraint_flags, coded.level_idc])
    out.append(0xFC | 3)          # reserved, lengthSizeMinusOne
    out.append(0xE0 | 1)          # reserved, numOfSequenceParameterSets
    out += len(coded.sps).to_bytes(2, "big") + coded.sps
    out.append(1)                 # numOfPictureParameterSets
    out += len(coded.pps).to_bytes(2, "big") + coded.pps
    if coded.profile_idc not in (66, 77, 88):
        out.append(0xFC | coded.chroma_format_idc)
        out.append(0xF8 | (coded.bit_depth - 8))  # bit_depth_luma_minus8
        out.append(0xF8 | (coded.bit_depth - 8))  # bit_depth_chroma_minus8
        out.append(0)             # numOfSequenceParameterSetExt
    return bytes(out)


def make_sample(coded: CodedPicture) -> bytes:
    """The coded picture as stored in an 'avc1' item or sample: the slice NAL
    unit with a 4 byte length field. The parameter sets go into 'avcC'."""
    return len(coded.slice).to_bytes(4, "big") + coded.slice
