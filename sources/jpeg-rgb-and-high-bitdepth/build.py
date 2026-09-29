#!/usr/bin/env python3
"""Build step for the generated JPEG images that are coded as RGB or with
more than 8 bits per sample.

Generates a colour gradient test picture for every variant listed in
VARIANTS, codes it as JPEG and writes it as a HEIF file with one 'jpeg'
image item. Next to each image the decoded planes are written as a raw
reference file.

The DCT based variants code only the DC coefficient of every 8x8 block and
the other variants are lossless, so the decoded samples are known exactly.

The generator uses integer arithmetic only, so the output is bit-identical
on every machine. The sha256 of every generated file is pinned below.

Usually run through ../../build-corpus.py, but works standalone:

    ./build.py --out /path/to/corpus/jpeg-rgb-and-high-bitdepth
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))

from corpuslib import generatedsource, heifwrite, jpeg, testpicture  # noqa: E402

WIDTH = 256
HEIGHT = 128

# Code points of ISO/IEC 23091-2.
PRIMARIES_BT709 = 1
TRANSFER_SRGB = 13
MATRIX_IDENTITY = 0   # planes hold G, B, R
MATRIX_BT601 = 6

SAMPLING = {
    "400": [(1, 1)],
    "420": [(2, 2), (1, 1), (1, 1)],
    "422": [(2, 1), (1, 1), (1, 1)],
    "444": [(1, 1), (1, 1), (1, 1)],
}


@dataclass(frozen=True)
class Variant:
    name: str
    bit_depth: int
    lossless: bool
    chroma: str          # 400, 420, 422 or 444
    rgb: bool
    raw_format: str      # FFmpeg pixel format name of the raw reference file
    colr: bool = True    # write a 'colr' box


VARIANTS = [
    Variant("jpeg-8bit-444-rgb", 8, False, "444", True, "gbrp"),
    Variant("jpeg-8bit-444-rgb-nocolr", 8, False, "444", True, "gbrp", colr=False),
    Variant("jpeg-12bit-400", 12, False, "400", False, "gray12le"),
    Variant("jpeg-12bit-420", 12, False, "420", False, "yuv420p12le"),
    Variant("jpeg-12bit-422", 12, False, "422", False, "yuv422p12le"),
    Variant("jpeg-12bit-444", 12, False, "444", False, "yuv444p12le"),
    Variant("jpeg-12bit-444-rgb", 12, False, "444", True, "gbrp12le"),
    Variant("jpeg-16bit-lossless-400", 16, True, "400", False, "gray16le"),
    Variant("jpeg-16bit-lossless-444-rgb", 16, True, "444", True, "gbrp16le"),
]

# sha256 of every generated file. After an intended change of the generator,
# run with --print-hashes, verify the new files with an independent decoder
# and update the list.
EXPECTED_SHA256 = {
    "jpeg-8bit-444-rgb.heif":
        "95fda48db4a509b63abc1cf3c43806f20ef8cfdb394f50a738f53f7e35960689",
    "jpeg-8bit-444-rgb.gbrp.raw":
        "ef6ca163c701738810509a19ace4a867a762d4283c14ffbc0fe782ddd985cce4",
    "jpeg-8bit-444-rgb-nocolr.heif":
        "1611de58c6f4f9b36b300ecce65752009c8685349f9e263915c248f72656aa97",
    "jpeg-8bit-444-rgb-nocolr.gbrp.raw":
        "ef6ca163c701738810509a19ace4a867a762d4283c14ffbc0fe782ddd985cce4",
    "jpeg-12bit-400.heif":
        "01fff8b4141795f0320b1a586c48253478b70e4b3aefece37f525d275c71a324",
    "jpeg-12bit-400.gray12le.raw":
        "10ff363f24635729239561ed30c62a5ebf77396f6ce0a0449558ed56a54f8fc5",
    "jpeg-12bit-420.heif":
        "f27a05dd5d6d50d9f76b32d9474e2a3cd6a6adb1e6851ab54f7f42e64f904f5e",
    "jpeg-12bit-420.yuv420p12le.raw":
        "6b71603b193963a02d95b6bb20d1b0227ab5d8ec8f7c461efc4030c7bfff2537",
    "jpeg-12bit-422.heif":
        "67bf89116d7a91d08b190efdb51c5b96b829afedccd18eae991dcc4ece9428dd",
    "jpeg-12bit-422.yuv422p12le.raw":
        "6f22317f83ea538406dac384b7d08fe55cf84210ba075ef16b82a058f1e89a6f",
    "jpeg-12bit-444.heif":
        "08820019a5e7499cb45ea4c37354c69f992aefad64b374bc5bcbca175d752963",
    "jpeg-12bit-444.yuv444p12le.raw":
        "f1b88848eabcc98f60dd7a0f5a33f4b01cf69dabee0d444d29662b4faef023cf",
    "jpeg-12bit-444-rgb.heif":
        "8912e29ddee9dccb77a12fb65bbc4187219dfd0aa61282293db18e389ac8c03c",
    "jpeg-12bit-444-rgb.gbrp12le.raw":
        "e06c97fe3d084650bb38e01e78660e6c3a56a3b0ad5dabd8f98e38eac1f1238b",
    "jpeg-16bit-lossless-400.heif":
        "b2f1fd30e3c19cc1d6f4ff6c4329eef225bde54f26fd3390bc80f3dbec70734a",
    "jpeg-16bit-lossless-400.gray16le.raw":
        "aefe4e89672ca0065deb7f8d96d6f7e8f77841b7b90249637b2c3f565fb7ed6d",
    "jpeg-16bit-lossless-444-rgb.heif":
        "ddebb7085ee1e0407d2ba1206f00fe58541ab990103cee137a2026e7e6a9c9af",
    "jpeg-16bit-lossless-444-rgb.gbrp16le.raw":
        "9aa8b569af4cc9948a515a72466b5d673f6728686dd30d2d96641d93afd8fd32",
}


def expand_blocks(plane: testpicture.Plane) -> testpicture.Plane:
    """Samples of a plane that consists of flat 8x8 blocks."""
    return [[value for value in row for _ in range(8)] for row in plane for _ in range(8)]


def make_jpeg(variant: Variant) -> Tuple[bytes, List[testpicture.Plane]]:
    """Returns the JPEG and the decoded planes. For RGB the planes are in the
    order G, B, R of the planar GBR representation; the JPEG codes R, G, B."""
    # The DCT based variants hold one value per 8x8 block.
    scale = 1 if variant.lossless else 8
    planes = testpicture.make_planes(WIDTH // scale, HEIGHT // scale, variant.bit_depth, variant.chroma,
                                     identity_matrix=variant.rgb)

    if variant.rgb:
        green, blue, red = planes
        coded = [red, green, blue]
        component_ids = jpeg.IDS_RGB
        adobe_transform: Optional[int] = jpeg.ADOBE_TRANSFORM_NONE
    else:
        coded = planes
        component_ids = jpeg.IDS_GRAY if variant.chroma == "400" else jpeg.IDS_YCBCR
        adobe_transform = None

    if variant.lossless:
        data = jpeg.write_lossless(variant.bit_depth, component_ids, coded, adobe_transform)
        return data, planes

    data = jpeg.write_dct_flat_blocks(variant.bit_depth, WIDTH, HEIGHT, component_ids,
                                      SAMPLING[variant.chroma], coded, adobe_transform)
    return data, [expand_blocks(plane) for plane in planes]


def make_heif(variant: Variant, data: bytes) -> bytes:
    channels = 1 if variant.chroma == "400" else 3
    properties = [heifwrite.ispe(WIDTH, HEIGHT)]
    if variant.colr:
        properties.append(heifwrite.colr_nclx(PRIMARIES_BT709, TRANSFER_SRGB,
                                              MATRIX_IDENTITY if variant.rgb else MATRIX_BT601, True))
    properties.append(heifwrite.pixi([variant.bit_depth] * channels))

    return heifwrite.write_single_image(major_brand=b"mif1", compatible_brands=[b"mif1", b"jpeg"],
                                        item_type=b"jpeg", properties=properties, item_data=data)


def make_raw_reference(variant: Variant, planes: List[testpicture.Plane]) -> bytes:
    if variant.bit_depth > 8:
        return testpicture.planes_to_raw16(planes)
    return bytes(value for plane in planes for row in plane for value in row)


def generate() -> List[Tuple[str, bytes]]:
    files = []
    for variant in VARIANTS:
        data, planes = make_jpeg(variant)
        files.append((f"{variant.name}.heif", make_heif(variant, data)))
        files.append((f"{variant.name}.{variant.raw_format}.raw", make_raw_reference(variant, planes)))
    return files


if __name__ == "__main__":
    sys.exit(generatedsource.run(sys.argv[1:], source_dir=HERE, generate=generate,
                                 expected_sha256=EXPECTED_SHA256, description=__doc__))
