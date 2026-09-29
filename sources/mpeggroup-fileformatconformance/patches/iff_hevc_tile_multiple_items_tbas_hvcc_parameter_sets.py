"""iff_hevc_tile_multiple_items_tbas.heic: terminate the VPS and SPS in 'hvcC'.

The 'hvcC' property shared by the tile base item 1 and the four 'hvt1'
tile items carries a VPS and an SPS that do not end the way ISO/IEC
23008-2 7.3.2 requires:

- The 24-byte VPS stops right after vps_timing_info_present_flag (= 0).
  vps_extension_flag and rbsp_trailing_bits() are missing, the RBSP is
  one byte short.
- The 49-byte SPS continues after vui_parameters_present_flag (= 0) with
  the bits 1 0 0 1 0000000. Read as sps_extension_present_flag = 1,
  sps_range_extension_flag = 0, sps_multilayer_extension_flag = 0 and
  sps_3d_extension_flag = 1, the sps_3d_extension() that must follow is
  not there, and no rbsp_trailing_bits() can be found either. (Under the
  2013 edition's syntax the same bits read as sps_extension_flag = 1 with
  two sps_extension_data_flag bits, which is equally meaningless.)

libde265 tolerates both, it stops at the end of the RBSP and ignores the
unknown extension flags. FFmpeg rejects the VPS ("too many
layer_id_included_flags") and, once that is fixed, the SPS ("Overread
SPS by 8 bits"), so the file decodes with one decoder and not with the
other.

Change: append 0x40 to the VPS (vps_extension_flag = 0, stop bit, six
alignment zero bits) and replace the last two SPS bytes b4 80 with b2
(sps_extension_present_flag = 0, stop bit, one alignment zero bit). The
VPS grows and the SPS shrinks by one byte, so the 'hvcC' box keeps its
size and no file offset moves. No parameter used by the decoding process
changes: FFmpeg decodes the corrected tile streams to exactly the pixels
that libde265 produces from the original file.
"""

from corpuslib.isobmff import BoxEditor, make_box

FILE = "iff_hevc_tile_multiple_items_tbas.heic"
UPSTREAM_ISSUE = None  # not reported yet
DESCRIPTION = __doc__

INPUT_SHA256 = "4902df52c32216cbcac1fdd048c591ea660be89180a0cea66378941bdf86c4cb"
# Verified 2026-09-21, see the source README for the checks performed.
OUTPUT_SHA256 = "e1b34fcd4f6c3403499b9518e0176794b6cd2b32907f394bb043e90e76b579a6"

VPS_OLD = bytes.fromhex("40010c01ffff016000000300000300000300000300969702")
VPS_NEW = VPS_OLD + bytes([0x40])
SPS_OLD = bytes.fromhex("42010101600000030000030000030000030096a001e020021c7f965e491b61e5e4924fe79fcf2ffffffcfe7f3f3f9db480")
SPS_NEW = SPS_OLD[:-2] + bytes([0xb2])


def rewrite_hvcc(payload: bytes) -> bytes:
    """Return the HEVCDecoderConfigurationRecord with the VPS and the SPS
    replaced and their nalUnitLength fields updated."""
    if len(payload) < 23:
        raise ValueError("'hvcC' payload too short")
    out = bytearray(payload[:23])
    p = 23
    replaced = []
    for _ in range(payload[22]):
        out += payload[p:p + 3]
        num_nalus = int.from_bytes(payload[p + 1:p + 3], "big")
        p += 3
        for _ in range(num_nalus):
            length = int.from_bytes(payload[p:p + 2], "big")
            p += 2
            nal = payload[p:p + length]
            p += length
            if nal == VPS_OLD:
                nal = VPS_NEW
                replaced.append("VPS")
            elif nal == SPS_OLD:
                nal = SPS_NEW
                replaced.append("SPS")
            out += len(nal).to_bytes(2, "big") + nal
    if p != len(payload):
        raise ValueError(f"{len(payload) - p} trailing bytes after the 'hvcC' arrays")
    if replaced != ["VPS", "SPS"]:
        raise ValueError(f"expected to replace the VPS and the SPS, replaced {replaced}")
    return bytes(out)


def apply(data: bytes) -> bytes:
    editor = BoxEditor(data)
    boxes = editor.find_all("hvcC")
    if len(boxes) != 1:
        raise ValueError(f"expected one 'hvcC' box, found {len(boxes)}")
    box = boxes[0]
    payload = bytes(editor.data[box.payload_start:box.end])
    editor.replace_box(box, make_box(b"hvcC", rewrite_hvcc(payload)))
    return bytes(editor.data)
