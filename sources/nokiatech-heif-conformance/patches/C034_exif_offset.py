"""C034.heic: insert the missing exif_tiff_header_offset field.

ISO/IEC 23008-12 A.2.1 stores Exif metadata items as

    aligned(8) class ExifDataBlock() {{
        unsigned int(32) exif_tiff_header_offset;
        unsigned int(8)  exif_payload[];
    }}

The Exif item 1004 of C034 starts directly with the TIFF header
("MM\0*", big-endian) and has no offset field. A conforming reader takes
the first four bytes 4d 4d 00 2a as the offset (1,296,891,946) and finds
no TIFF header (nokiatech/heif_conformance#10).

Change: insert the four bytes 00 00 00 00 (offset 0, TIFF header is the
first byte of the payload) in front of the item data inside 'mdat', grow
the item's 'iloc' extent length from 176 to 180 and update 'mdat'. No
other item stores data behind the Exif block, so no other offset moves.
"""

from corpuslib.corrections import prepend_exif_tiff_header_offset
from corpuslib.isobmff import BoxEditor

FILE = "C034.heic"
UPSTREAM_ISSUE = "https://github.com/nokiatech/heif_conformance/issues/10"
DESCRIPTION = __doc__

INPUT_SHA256 = "d2d61c040eba858cff05d7804c0999fb8955bcfe3ec99e5fd9f0b90d2dd2fe97"
# Verified 2026-09-19, see the source README for the checks performed.
OUTPUT_SHA256 = "618cdfb15f78d15d4160f9c88044bbdfabfa21eb307bf7bf240d382083944012"

EXIF_ITEM_ID = 1004


def apply(data: bytes) -> bytes:
    editor = BoxEditor(data)
    new_length = prepend_exif_tiff_header_offset(editor, EXIF_ITEM_ID)
    if new_length != 180:
        raise ValueError(f"unexpected Exif item length {{new_length}}")
    return bytes(editor.data)
