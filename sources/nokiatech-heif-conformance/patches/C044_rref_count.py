"""C044.heic: store the 'rref' reference_type_count in 8 bits.

ISO/IEC 23008-12 6.5.17.2 defines RequiredReferenceTypesProperty as

    unsigned int(8)  reference_type_count;
    unsigned int(32) reference_type[reference_type_count];

The Nokia writer stored reference_type_count as a 32-bit field
(nokiatech/heif#117), so the property payload reads

    00 00 00 01 'pred'      instead of      01 'pred'

A conforming reader takes the first byte as the count (0) and finds no
required reference types, then sees three bytes of garbage. libheif works
around this by sniffing the payload length (Box_rref::parse in box.cc)
and notes that the workaround can go once the files are corrected.

Change: rewrite every 'rref' box in 'ipco' with an 8-bit count. Each box
shrinks by three bytes; enclosing sizes and 'iloc' offsets are updated.
"""

from corpuslib.corrections import rewrite_rref_count_as_uint8
from corpuslib.isobmff import BoxEditor

FILE = "C044.heic"
UPSTREAM_ISSUE = "https://github.com/nokiatech/heif_conformance/issues/9"
DESCRIPTION = __doc__

INPUT_SHA256 = "550443448520e724af11734f86d51e50a8e42e3f4b5ed47debc2c5d25fdb3190"
# Verified 2026-09-19, see the source README for the checks performed.
OUTPUT_SHA256 = "993e7959bb4dea53ae80f1c29efec3410f4eda1fbe75d78bcd85f806cde9bc90"


def apply(data: bytes) -> bytes:
    editor = BoxEditor(data)
    rewritten = rewrite_rref_count_as_uint8(editor)
    if rewritten != 1:
        raise ValueError(f"expected to rewrite 1 'rref' box(es), rewrote {rewritten}")
    return bytes(editor.data)
