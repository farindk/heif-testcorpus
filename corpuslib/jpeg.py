"""Minimal JPEG (ISO/IEC 10918-1) writers for generated images.

Both writers produce pictures whose decoded samples are known exactly, so
they need no reference decoder:

- write_dct_flat_blocks()  extended sequential DCT (SOF1), 8 or 12 bits.
                           Every 8x8 block is coded with its DC coefficient
                           only. The quantizer is 1 and the DC coefficient of
                           a flat block with value v is 8 * (v - 2^(P-1)), so
                           the block decodes to v in every decoder.
- write_lossless()         lossless (SOF3), 2 to 16 bits, predictor 1.

The Huffman tables are as simple as possible. They are not chosen for
compression.
"""

from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

Plane = List[List[int]]

# Component identifiers
IDS_YCBCR = (1, 2, 3)
IDS_GRAY = (1,)
IDS_RGB = (ord("R"), ord("G"), ord("B"))

# Adobe APP14 colour transform
ADOBE_TRANSFORM_NONE = 0   # components are RGB (or CMYK)
ADOBE_TRANSFORM_YCBCR = 1


class _BitWriter:
    """Entropy coded segment: most significant bit first, a zero byte is
    stuffed after every 0xFF, the last byte is padded with 1 bits."""

    def __init__(self) -> None:
        self._data = bytearray()
        self._acc = 0
        self._nbits = 0

    def put(self, nbits: int, value: int) -> None:
        if nbits == 0:
            return
        if value < 0 or value >> nbits:
            raise ValueError(f"{value} does not fit into {nbits} bits")
        self._acc = (self._acc << nbits) | value
        self._nbits += nbits
        while self._nbits >= 8:
            self._nbits -= 8
            byte = (self._acc >> self._nbits) & 0xFF
            self._data.append(byte)
            if byte == 0xFF:
                self._data.append(0)
        self._acc &= (1 << self._nbits) - 1

    def finish(self) -> bytes:
        if self._nbits:
            pad = 8 - self._nbits
            self.put(pad, (1 << pad) - 1)
        return bytes(self._data)


def _segment(marker: int, payload: bytes) -> bytes:
    return bytes([0xFF, marker]) + (len(payload) + 2).to_bytes(2, "big") + payload


def _adobe_app14(transform: int) -> bytes:
    # version 100, flags0 0, flags1 0
    return _segment(0xEE, b"Adobe" + (100).to_bytes(2, "big") + bytes(4) + bytes([transform]))


def _category_table(nsymbols: int) -> bytes:
    """DHT for table 0 of class 0 (DC, lossless): the categories 0 to
    nsymbols-1, each with a code of 5 bits that is the category itself. The
    code of all 1 bits stays unused, as B.2.4.2 requires."""
    if nsymbols > 31:
        raise ValueError("too many symbols for 5 bit codes")
    bits = [0] * 16
    bits[4] = nsymbols
    return _segment(0xC4, bytes([0x00]) + bytes(bits) + bytes(range(nsymbols)))


def _end_of_block_table() -> bytes:
    """DHT for table 0 of class 1 (AC): '0' is EOB and '10' is ZRL. ZRL is
    never used; it keeps the table from consisting of a single code."""
    return _segment(0xC4, bytes([0x10]) + bytes([1, 1] + [0] * 14) + bytes([0x00, 0xF0]))


def _put_difference(w: _BitWriter, diff: int, lossless: bool) -> None:
    """Category and additional bits of a DC difference (F.1.2.1) or of a
    lossless prediction difference (H.1.2.2)."""
    ssss = abs(diff).bit_length()
    w.put(5, ssss)
    if lossless and ssss == 16:
        return  # the difference 32768 has no additional bits
    w.put(ssss, diff if diff >= 0 else diff + (1 << ssss) - 1)


def _frame_header(marker: int, precision: int, width: int, height: int,
                  component_ids: Sequence[int], sampling: Sequence[Tuple[int, int]]) -> bytes:
    payload = bytes([precision]) + height.to_bytes(2, "big") + width.to_bytes(2, "big")
    payload += bytes([len(component_ids)])
    for ident, (h, v) in zip(component_ids, sampling):
        payload += bytes([ident, (h << 4) | v, 0])  # quantization table 0
    return _segment(marker, payload)


def _scan_header(component_ids: Sequence[int], ss: int, se: int) -> bytes:
    payload = bytes([len(component_ids)])
    for ident in component_ids:
        payload += bytes([ident, 0x00])  # DC table 0, AC table 0
    return _segment(0xDA, payload + bytes([ss, se, 0x00]))


def write_dct_flat_blocks(precision: int, width: int, height: int, component_ids: Sequence[int],
                          sampling: Sequence[Tuple[int, int]], blocks: Sequence[Plane],
                          adobe_transform: Optional[int] = None) -> bytes:
    """blocks[c][by][bx] is the value of the 8x8 block (bx, by) of component
    c. sampling holds the horizontal and vertical sampling factor of every
    component."""
    if precision not in (8, 12):
        raise ValueError("DCT based coding has 8 or 12 bits")
    hmax = max(h for h, v in sampling)
    vmax = max(v for h, v in sampling)
    if width % (8 * hmax) or height % (8 * vmax):
        raise ValueError("picture size must be a multiple of the MCU size")
    mcus_x = width // (8 * hmax)
    mcus_y = height // (8 * vmax)
    for plane, (h, v) in zip(blocks, sampling):
        if len(plane) != mcus_y * v or any(len(row) != mcus_x * h for row in plane):
            raise ValueError("block plane does not match the picture size")
        if any(not 0 <= value < (1 << precision) for row in plane for value in row):
            raise ValueError(f"block value outside of the {precision} bit range")

    out = bytearray(b"\xFF\xD8")  # SOI
    if adobe_transform is not None:
        out += _adobe_app14(adobe_transform)
    out += _segment(0xDB, bytes([0x00]) + bytes([1] * 64))  # DQT: table 0, 8 bit entries, all 1
    out += _frame_header(0xC1, precision, width, height, component_ids, sampling)
    out += _category_table(16)
    out += _end_of_block_table()
    out += _scan_header(component_ids, 0, 63)

    w = _BitWriter()
    prediction = [0] * len(component_ids)
    level_shift = 1 << (precision - 1)
    for my in range(mcus_y):
        for mx in range(mcus_x):
            for c, (h, v) in enumerate(sampling):
                for by in range(v):
                    for bx in range(h):
                        dc = 8 * (blocks[c][my * v + by][mx * h + bx] - level_shift)
                        _put_difference(w, dc - prediction[c], lossless=False)
                        prediction[c] = dc
                        w.put(1, 0)  # EOB
    out += w.finish() + b"\xFF\xD9"  # EOI
    return bytes(out)


def write_lossless(precision: int, component_ids: Sequence[int], planes: Sequence[Plane],
                   adobe_transform: Optional[int] = None) -> bytes:
    """All components have the size of the picture (sampling factors 1)."""
    if not 2 <= precision <= 16:
        raise ValueError("lossless coding has 2 to 16 bits")
    height = len(planes[0])
    width = len(planes[0][0])
    for plane in planes:
        if len(plane) != height or any(len(row) != width for row in plane):
            raise ValueError("planes differ in size")
        if any(not 0 <= value < (1 << precision) for row in plane for value in row):
            raise ValueError(f"sample outside of the {precision} bit range")

    out = bytearray(b"\xFF\xD8")
    if adobe_transform is not None:
        out += _adobe_app14(adobe_transform)
    out += _frame_header(0xC3, precision, width, height, component_ids, [(1, 1)] * len(component_ids))
    out += _category_table(17)
    out += _scan_header(component_ids, 1, 0)  # Ss: predictor 1, the sample to the left

    # H.1.2.1: the differences are computed modulo 2^16
    w = _BitWriter()
    for y in range(height):
        for x in range(width):
            for plane in planes:
                if x > 0:
                    prediction = plane[y][x - 1]
                elif y > 0:
                    prediction = plane[y - 1][0]
                else:
                    prediction = 1 << (precision - 1)
                diff = (plane[y][x] - prediction) & 0xFFFF
                if diff > 32768:
                    diff -= 65536
                _put_difference(w, diff, lossless=True)
    out += w.finish() + b"\xFF\xD9"
    return bytes(out)
