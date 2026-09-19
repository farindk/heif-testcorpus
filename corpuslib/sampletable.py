"""Read the sample table of a track: sample sizes and absolute file offsets.

Supports the boxes the conformance files use: 'stsz' (not 'stz2'), 'stsc'
and 'stco'/'co64'. Movie fragments are not handled.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from .hevc import hvcc_length_size
from .isobmff import Box, BoxEditor, make_full_box, parse_boxes

VISUAL_SAMPLE_ENTRY_FIELDS = 78  # bytes between the sample entry header and its child boxes


@dataclass
class TrackSamples:
    track_id: int
    handler: str
    sample_entry: str
    length_size: Optional[int]  # NAL unit length size for 'hvc1'/'hev1', else None
    sizes: List[int]
    offsets: List[int]          # absolute file offsets
    trak: Box
    stbl: Box

    @property
    def count(self) -> int:
        return len(self.sizes)


def child(box: Box, fourcc: str) -> Optional[Box]:
    wanted = fourcc.encode("latin-1")
    return next((c for c in box.children if c.type == wanted), None)


def require_child(box: Box, fourcc: str) -> Box:
    found = child(box, fourcc)
    if found is None:
        raise ValueError(f"'{box.fourcc}' has no '{fourcc}' child")
    return found


def read_track(editor: BoxEditor, trak: Box) -> TrackSamples:
    data = editor.data
    tkhd = require_child(trak, "tkhd")
    tkhd_version = data[tkhd.payload_start]
    track_id = editor.read_uint(tkhd.payload_start + 4 + (8 if tkhd_version == 0 else 16), 4)

    mdia = require_child(trak, "mdia")
    hdlr = require_child(mdia, "hdlr")
    handler = bytes(data[hdlr.payload_start + 8:hdlr.payload_start + 12]).decode("latin-1")
    stbl = require_child(require_child(mdia, "minf"), "stbl")

    stsd = require_child(stbl, "stsd")
    if not stsd.children:
        raise ValueError("'stsd' has no sample entry")
    entry = stsd.children[0]
    length_size = None
    if entry.type in (b"hvc1", b"hev1"):
        entry_children = parse_boxes(data, entry.payload_start + VISUAL_SAMPLE_ENTRY_FIELDS, entry.end)
        hvcc = next((c for c in entry_children if c.type == b"hvcC"), None)
        if hvcc is None:
            raise ValueError(f"'{entry.fourcc}' sample entry has no 'hvcC'")
        length_size = hvcc_length_size(bytes(data[hvcc.payload_start:hvcc.end]))

    if child(stbl, "stz2") is not None:
        raise ValueError("'stz2' sample sizes are not supported")
    stsz = require_child(stbl, "stsz")
    p = stsz.payload_start + 4
    default_size = editor.read_uint(p, 4)
    sample_count = editor.read_uint(p + 4, 4)
    if default_size:
        sizes = [default_size] * sample_count
    else:
        sizes = [editor.read_uint(p + 8 + 4 * i, 4) for i in range(sample_count)]

    stsc = require_child(stbl, "stsc")
    p = stsc.payload_start + 4
    entry_count = editor.read_uint(p, 4)
    p += 4
    stsc_entries = [(editor.read_uint(p + 12 * i, 4), editor.read_uint(p + 12 * i + 4, 4))
                    for i in range(entry_count)]  # (first_chunk, samples_per_chunk)

    co = child(stbl, "stco") or child(stbl, "co64")
    if co is None:
        raise ValueError("'stbl' has neither 'stco' nor 'co64'")
    width = 4 if co.type == b"stco" else 8
    p = co.payload_start + 4
    chunk_count = editor.read_uint(p, 4)
    chunk_offsets = [editor.read_uint(p + 4 + width * i, width) for i in range(chunk_count)]

    offsets: List[int] = []
    sample = 0
    for chunk_index in range(1, chunk_count + 1):
        samples_per_chunk = next((spc for first, spc in reversed(stsc_entries) if first <= chunk_index), 0)
        offset = chunk_offsets[chunk_index - 1]
        for _ in range(samples_per_chunk):
            if sample >= sample_count:
                break
            offsets.append(offset)
            offset += sizes[sample]
            sample += 1
    if len(offsets) != sample_count:
        raise ValueError(f"chunk table covers {len(offsets)} of {sample_count} samples")

    return TrackSamples(track_id, handler, entry.fourcc, length_size, sizes, offsets, trak, stbl)


def sample_bytes(editor: BoxEditor, track: TrackSamples, index: int) -> bytes:
    offset = track.offsets[index]
    return bytes(editor.data[offset:offset + track.sizes[index]])


def make_stss(sample_numbers: List[int]) -> bytes:
    payload = len(sample_numbers).to_bytes(4, "big") + b"".join(n.to_bytes(4, "big") for n in sample_numbers)
    return make_full_box(b"stss", 0, 0, payload)
