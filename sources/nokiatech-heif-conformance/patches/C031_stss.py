"""C031.heic: add the missing 'stss' sync sample table.

Upstream description: "An image sequence and a video track, set as alternatives."

ISO/IEC 14496-12 8.6.2.1: "If the sync sample box is not present, every
sample is a sync sample." Both the 'pict' track 1 and the 'vide' track 2 have 8 samples. Only the first
sample of each track is an IRAP picture (IDR_W_RADL); samples 2 to 8 are
TRAIL_R pictures that reference earlier samples. Without 'stss' a reader
may start decoding at any sample and fails to find its references
(nokiatech/heif_conformance#8, which lists this file).

Change: for every HEVC track without 'stss', classify each sample by its
NAL unit types and append a 'stss' listing the IRAP samples (here: sample
1 of every track). Chunk offsets in 'stco' are updated for the inserted
bytes.
"""

from corpuslib.corrections import add_missing_stss
from corpuslib.isobmff import BoxEditor

FILE = "C031.heic"
UPSTREAM_ISSUE = "https://github.com/nokiatech/heif_conformance/issues/8"
DESCRIPTION = __doc__

INPUT_SHA256 = "cf9e46d7ed8e899d091db068ded7b5e02aa00d33848463484eaa736b3aeb6558"
# Verified 2026-09-19, see the source README for the checks performed.
OUTPUT_SHA256 = "9b6cde8fddd09a573e13ee278552b46344e5493258660a053fdc1fce83e0af07"

EXPECTED = {1: [1], 2: [1]}  # {track_id: sync sample numbers}


def apply(data: bytes) -> bytes:
    editor = BoxEditor(data)
    report = dict(add_missing_stss(editor))
    if report != EXPECTED:
        raise ValueError(f"unexpected sync sample layout {report}, expected {EXPECTED}")
    return bytes(editor.data)
