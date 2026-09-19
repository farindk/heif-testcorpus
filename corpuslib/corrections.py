"""Reusable correction operations shared by the per-file patch modules.

Each function edits a BoxEditor in place and returns a short report of
what it changed. The per-file modules add the pinned hashes and the
reasoning for one specific file.
"""

from __future__ import annotations

from typing import List, Tuple

from .hevc import is_irap_sample
from .isobmff import BoxEditor, iloc_locations, iloc_set_extent_length, make_full_box
from .sampletable import child, make_stss, read_track, sample_bytes

TIFF_HEADERS = (b"II*\x00", b"MM\x00*")


def rewrite_rref_count_as_uint8(editor: BoxEditor) -> int:
    """Rewrite every 'rref' property whose reference_type_count was written
    as a 32-bit field into the 8-bit form of ISO/IEC 23008-12 6.5.17.2.
    Returns the number of boxes rewritten."""
    rewritten = 0
    index = 0
    while True:
        boxes = editor.find_all("rref")
        if index >= len(boxes):
            return rewritten
        box = boxes[index]
        index += 1
        version = editor.data[box.payload_start]
        flags = editor.read_uint(box.payload_start + 1, 3)
        body = bytes(editor.data[box.payload_start + 4:box.end])
        if len(body) >= 1 and len(body) == 1 + 4 * body[0]:
            continue  # already the correct 8-bit form
        if len(body) < 4:
            raise ValueError("'rref' payload too short")
        count32 = int.from_bytes(body[:4], "big")
        if len(body) != 4 + 4 * count32 or count32 > 255:
            raise ValueError("'rref' payload matches neither the 8-bit nor the 32-bit count form")
        blob = make_full_box(b"rref", version, flags, bytes([count32]) + body[4:])
        editor.replace_box(box, blob)
        rewritten += 1


def add_missing_stss(editor: BoxEditor) -> List[Tuple[int, List[int]]]:
    """Add a 'stss' box to every track that has non-IRAP HEVC samples but no
    sync sample table. Returns [(track_id, sync sample numbers)]."""
    report = []
    index = 0
    while True:
        traks = editor.find_all("trak")
        if index >= len(traks):
            return report
        track = read_track(editor, traks[index])
        index += 1
        if track.length_size is None:
            continue  # not HEVC, cannot classify samples
        if child(track.stbl, "stss") is not None:
            continue  # already has a sync sample table
        sync = [i + 1 for i in range(track.count)
                if is_irap_sample(sample_bytes(editor, track, i), track.length_size)]
        if len(sync) == track.count:
            continue  # every sample is a sync sample, absence of 'stss' is correct
        if not sync or sync[0] != 1:
            raise ValueError(f"track {track.track_id}: first sample is not an IRAP picture")
        editor.append_child_to(track.stbl, make_stss(sync))
        report.append((track.track_id, sync))


def prepend_exif_tiff_header_offset(editor: BoxEditor, item_id: int) -> int:
    """Insert the exif_tiff_header_offset field (ISO/IEC 23008-12 A.2.1) in
    front of an Exif item whose data starts directly with the TIFF header.
    Returns the new item length."""
    location = iloc_locations(editor)[item_id]
    if location.construction_method != 0 or location.data_reference_index != 0:
        raise ValueError("only items stored in this file with construction method 0 are supported")
    if len(location.extents) != 1:
        raise ValueError("expected a single extent")
    offset, length = location.absolute_extents()[0]
    payload = bytes(editor.data[offset:offset + length])
    if payload[:4] not in TIFF_HEADERS:
        raise ValueError("item data does not start with a TIFF header; it may already carry the offset field")
    editor.insert_payload_bytes(offset, (0).to_bytes(4, "big"))
    iloc_set_extent_length(editor, item_id, 0, length + 4)
    return length + 4
