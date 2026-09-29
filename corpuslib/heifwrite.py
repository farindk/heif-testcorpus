"""Minimal HEIF (ISO/IEC 23008-12) writer for generated images.

Writes a file with a single coded image item, which is the primary item,
and its item properties. The coded data is passed in as it is stored in the
file; nothing here interprets it.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import List, Sequence

from .isobmff import make_box, make_full_box

ITEM_ID = 1


@dataclass(frozen=True)
class Property:
    box: bytes  # complete box, header included
    essential: bool = False


def ispe(width: int, height: int) -> Property:
    return Property(make_full_box(b"ispe", 0, 0, struct.pack(">II", width, height)))


def pixi(bits_per_channel: Sequence[int]) -> Property:
    return Property(make_full_box(b"pixi", 0, 0, bytes([len(bits_per_channel), *bits_per_channel])))


def colr_nclx(colour_primaries: int, transfer_characteristics: int, matrix_coefficients: int,
              full_range: bool) -> Property:
    payload = b"nclx" + struct.pack(">HHHB", colour_primaries, transfer_characteristics,
                                    matrix_coefficients, 0x80 if full_range else 0)
    return Property(make_box(b"colr", payload))


def _meta(item_type: bytes, properties: Sequence[Property], data_offset: int, data_length: int) -> bytes:
    hdlr = make_full_box(b"hdlr", 0, 0, struct.pack(">I4s12x", 0, b"pict") + b"\x00")
    pitm = make_full_box(b"pitm", 0, 0, struct.pack(">H", ITEM_ID))

    iloc = make_full_box(b"iloc", 0, 0,
                         bytes([0x44, 0x00])          # offset_size 4, length_size 4, base_offset_size 0
                         + struct.pack(">H", 1)       # item_count
                         + struct.pack(">HHH", ITEM_ID, 0, 1)  # item_ID, data_reference_index, extent_count
                         + struct.pack(">II", data_offset, data_length))

    infe = make_full_box(b"infe", 2, 0, struct.pack(">HH4s", ITEM_ID, 0, item_type) + b"\x00")
    iinf = make_full_box(b"iinf", 0, 0, struct.pack(">H", 1) + infe)

    if len(properties) > 127:
        raise ValueError("too many properties for 7 bit property indices")
    associations = bytes((0x80 if p.essential else 0) | index
                         for index, p in enumerate(properties, 1))
    ipma = make_full_box(b"ipma", 0, 0,
                         struct.pack(">I", 1)         # entry_count
                         + struct.pack(">HB", ITEM_ID, len(properties))
                         + associations)
    ipco = make_box(b"ipco", b"".join(p.box for p in properties))
    iprp = make_box(b"iprp", ipco + ipma)

    return make_full_box(b"meta", 0, 0, hdlr + pitm + iloc + iinf + iprp)


def write_single_image(*, major_brand: bytes, compatible_brands: List[bytes], item_type: bytes,
                       properties: Sequence[Property], item_data: bytes) -> bytes:
    ftyp = make_box(b"ftyp", major_brand + struct.pack(">I", 0) + b"".join(compatible_brands))

    # The size of 'meta' does not depend on the offset it stores, so lay it
    # out once to learn where the item data will start.
    meta_size = len(_meta(item_type, properties, 0, len(item_data)))
    data_offset = len(ftyp) + meta_size + 8  # 8: 'mdat' box header
    meta = _meta(item_type, properties, data_offset, len(item_data))

    return ftyp + meta + make_box(b"mdat", item_data)
