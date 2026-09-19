"""C039.heic: give the second 'iden' item its own, correct 'ispe'.

Upstream structure:

    1002  hvc1                 ispe 1280x720
    1003  iden  dimg -> 1002   ispe 1280x720, clap 300x300, irot 90
    1004  iden  dimg -> 1003   ispe 1280x720, clap 150x150, irot 90   (primary)

All three items share the single 'ispe' property at ipco index 2.

ISO/IEC 23008-12, 6.6.1: the input to a derived image item is the output
image of the referenced item, transformative properties included. 6.5.3:
'ispe' documents the reconstructed image before the item's own
transformative properties. The input of item 1004 is therefore the
300x300 output of item 1003, and its 'ispe' must be 300x300, not the
1280x720 of the coded image at the root of the chain.

The output of item 1004 is 150x150 either way (the 'clap' is centred and
has a fixed size), so readers that do not validate 'ispe' produce the
expected picture. Readers that do validate it, such as libheif 1.23.2 and
later, reject item 1004.

Change: append 'ispe' 300x300 to 'ipco' (becoming index 6) and point item
1004's association from index 2 to index 6. Item 1003 keeps index 2,
which is correct for it. The 'iloc' file offsets move by the 20 inserted
bytes; the box editor takes care of that.
"""

import struct

from corpuslib.isobmff import BoxEditor, ipma_associations, ipma_replace_index, make_full_box

FILE = "C039.heic"
UPSTREAM_ISSUE = "https://github.com/nokiatech/heif_conformance/issues/11"
DESCRIPTION = __doc__

INPUT_SHA256 = "507e4fe241b73e098050ac12d6cefe84efbf2acf0d7f8b0b23f23480f6911658"
# Verified 2026-09-19: libheif 1.23.0 and master decode the corrected file to
# pixel-identical output (1280x720, 300x300, 150x150) compared with libheif
# 1.23.0 decoding the upstream file.
OUTPUT_SHA256 = "ea955a29e9701a7ff66afd06cca7a62fb4a759526feccb9359d6f3283208f6dd"

ITEM_ID = 1004
SHARED_ISPE_INDEX = 2
NEW_WIDTH, NEW_HEIGHT = 300, 300


def apply(data: bytes) -> bytes:
    editor = BoxEditor(data)

    # Preconditions, spelled out so the intent survives a future manifest update.
    ipco = editor.find("meta/iprp/ipco")
    shared_ispe = ipco.children[SHARED_ISPE_INDEX - 1]
    if shared_ispe.type != b"ispe":
        raise ValueError("ipco index 2 is not the shared 'ispe'")
    width, height = struct.unpack_from(">II", editor.data, shared_ispe.payload_start + 4)
    if (width, height) != (1280, 720):
        raise ValueError(f"shared 'ispe' is {width}x{height}, expected 1280x720")
    assocs = ipma_associations(editor)
    if (False, SHARED_ISPE_INDEX) not in assocs.get(ITEM_ID, []):
        raise ValueError(f"item {ITEM_ID} is not associated with ipco index {SHARED_ISPE_INDEX}")

    new_index = len(ipco.children) + 1
    editor.append_child("meta/iprp/ipco",
                        make_full_box(b"ispe", 0, 0, struct.pack(">II", NEW_WIDTH, NEW_HEIGHT)))
    ipma_replace_index(editor, ITEM_ID, SHARED_ISPE_INDEX, new_index)

    return bytes(editor.data)
