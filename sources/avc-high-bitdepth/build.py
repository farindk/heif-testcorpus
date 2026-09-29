#!/usr/bin/env python3
"""Build step for the generated AVC images with more than 8 bits per sample.

Generates a colour gradient test picture for every variant listed in
VARIANTS, codes it losslessly as an AVC intra picture of I_PCM macroblocks
and writes it as a HEIF file with one 'avc1' image item. Next to each image
the decoded planes are written as a raw reference file.

The generator uses integer arithmetic only, so the output is bit-identical
on every machine. The sha256 of every generated file is pinned below.

Usually run through ../../build-corpus.py, but works standalone:

    ./build.py --out /path/to/corpus/avc-high-bitdepth
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))

from corpuslib import avc, generatedsource, heifwrite, testpicture  # noqa: E402

WIDTH = 256
HEIGHT = 128

# Code points of ISO/IEC 23091-2.
PRIMARIES_BT709 = 1
TRANSFER_SRGB = 13
MATRIX_IDENTITY = 0   # planes hold G, B, R
MATRIX_BT601 = 6

CHROMA_NAMES = {avc.CHROMA_400: "400", avc.CHROMA_420: "420", avc.CHROMA_422: "422", avc.CHROMA_444: "444"}


@dataclass(frozen=True)
class Variant:
    name: str
    bit_depth: int
    chroma_format_idc: int
    matrix_coefficients: int
    raw_format: str  # FFmpeg pixel format name of the raw reference file


VARIANTS = [
    Variant("avc-9bit-400", 9, avc.CHROMA_400, MATRIX_BT601, "gray9le"),
    Variant("avc-9bit-420", 9, avc.CHROMA_420, MATRIX_BT601, "yuv420p9le"),
    Variant("avc-9bit-422", 9, avc.CHROMA_422, MATRIX_BT601, "yuv422p9le"),
    Variant("avc-9bit-444", 9, avc.CHROMA_444, MATRIX_BT601, "yuv444p9le"),
    Variant("avc-9bit-444-gbr", 9, avc.CHROMA_444, MATRIX_IDENTITY, "gbrp9le"),
    Variant("avc-14bit-444-gbr", 14, avc.CHROMA_444, MATRIX_IDENTITY, "gbrp14le"),
]

# sha256 of every generated file. After an intended change of the generator,
# run with --print-hashes, verify the new files with an independent decoder
# and update the list.
EXPECTED_SHA256 = {
    "avc-9bit-400.heif":
        "aab393291495d9a170992343cdb9c14345f897f0622286efa26ed8ea640d980a",
    "avc-9bit-400.gray9le.raw":
        "99f5519cc43545076176c7f54e42b40162a3df8ab2a596ae5361ae69513cc4bb",
    "avc-9bit-420.heif":
        "d4b279999a2100d814d97c57f3636257561ca2fd7ed0ccd88068d027b16a8394",
    "avc-9bit-420.yuv420p9le.raw":
        "efa557e654b2363a8bbdd0fabe53828697f20c6c8fdca84c3fb7107097c65832",
    "avc-9bit-422.heif":
        "e8d08d7eaef4897bebab58346411628f6f6b968235282e717baae8b3a50c4ac2",
    "avc-9bit-422.yuv422p9le.raw":
        "926120158f326b71188367fbfc93a6a659f04727d0b99452f516f9d8d814231b",
    "avc-9bit-444.heif":
        "2151ce0f67c1e4f18d3ae96d068404ae9042183f792abeee08e9fd76073abdfc",
    "avc-9bit-444.yuv444p9le.raw":
        "159147bfdad522abf3b4484ce98880fd3e1080c3a80b2f678372cbc4428eae93",
    "avc-9bit-444-gbr.heif":
        "c5501f20e8df563a585450f269fd04d8118f1e50a943d011fd2f88979a80a85c",
    "avc-9bit-444-gbr.gbrp9le.raw":
        "3f743a5f194b46eacc36f2333d708e2f029b9eb588adeb834cc86dcc0147e44d",
    "avc-14bit-444-gbr.heif":
        "b074a0e186a8a7a6baa1ac3e9dd3357be135c4ee931ec990ab4bb9dc7c83daf3",
    "avc-14bit-444-gbr.gbrp14le.raw":
        "5798b0b69d2eaa0c2e05eb35e8aa229d61cdc2f8df51f483849ac52fdd316dd0",
}


def make_picture(variant: Variant) -> avc.Picture:
    planes = testpicture.make_planes(WIDTH, HEIGHT, variant.bit_depth, CHROMA_NAMES[variant.chroma_format_idc],
                                     identity_matrix=variant.matrix_coefficients == MATRIX_IDENTITY)
    return avc.Picture(WIDTH, HEIGHT, variant.bit_depth, variant.chroma_format_idc, planes)


def make_heif(variant: Variant, pic: avc.Picture) -> bytes:
    colour = avc.ColourDescription(PRIMARIES_BT709, TRANSFER_SRGB, variant.matrix_coefficients, full_range=True)
    coded = avc.encode_ipcm_picture(pic, colour)

    properties = [
        heifwrite.Property(heifwrite.make_box(b"avcC", avc.make_avcC_payload(coded)), essential=True),
        heifwrite.ispe(pic.width, pic.height),
        heifwrite.colr_nclx(colour.colour_primaries, colour.transfer_characteristics,
                            colour.matrix_coefficients, colour.full_range),
        heifwrite.pixi([pic.bit_depth] * len(pic.planes)),
    ]
    # The 'avci' brand requires the Constrained High profile (ISO/IEC 23008-12
    # E.4.1.1), which these pictures exceed. They are plain 'mif1' files.
    return heifwrite.write_single_image(major_brand=b"mif1", compatible_brands=[b"mif1"],
                                        item_type=b"avc1", properties=properties,
                                        item_data=avc.make_sample(coded))


def generate() -> List[Tuple[str, bytes]]:
    files = []
    for variant in VARIANTS:
        pic = make_picture(variant)
        files.append((f"{variant.name}.heif", make_heif(variant, pic)))
        files.append((f"{variant.name}.{variant.raw_format}.raw", testpicture.planes_to_raw16(pic.planes)))
    return files


if __name__ == "__main__":
    sys.exit(generatedsource.run(sys.argv[1:], source_dir=HERE, generate=generate,
                                 expected_sha256=EXPECTED_SHA256, description=__doc__))
