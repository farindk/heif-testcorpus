"""C043.heic: store the 'rref' reference_type_count in 8 bits.

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

C043 has one 'rref' property shared by the two predictively coded items
1004 and 1006. The upstream report names C044 only; C043 has the same defect.
"""

from corpuslib.corrections import rewrite_rref_count_as_uint8
from corpuslib.isobmff import BoxEditor

FILE = "C043.heic"
UPSTREAM_ISSUE = "https://github.com/nokiatech/heif_conformance/issues/9"
DESCRIPTION = __doc__

INPUT_SHA256 = "4d9e131a9e896625348b374605d4b65d62b64178d31c938b5302fb704c2a2042"
# Verified 2026-09-19, see the source README for the checks performed.
OUTPUT_SHA256 = "48f8a54687c60249b0f7895a41598b58eeb50de2a73b52bd7d9a7c20e571db17"


def apply(data: bytes) -> bytes:
    editor = BoxEditor(data)
    rewritten = rewrite_rref_count_as_uint8(editor)
    if rewritten != 1:
        raise ValueError(f"expected to rewrite 1 'rref' box(es), rewrote {rewritten}")
    return bytes(editor.data)
