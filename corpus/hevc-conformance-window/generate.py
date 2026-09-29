#!/usr/bin/env python3
"""Recipe that produced the images in this folder.

This is not a build step: the images are committed, because producing them
needs the HEVC reference software HM. The script documents how they were made
and recreates them if needed.

    git clone https://vcgit.hhi.fraunhofer.de/jvet/HM.git
    cd HM && git checkout HM-18.0
    cmake -S . -B build -DCMAKE_BUILD_TYPE=Release && cmake --build build --target TAppEncoder
    ./generate.py --encoder HM/bin/TAppEncoderStatic \\
                  --config HM/cfg/encoder_intra_main10.cfg

HM 18.0 does not compile with GCC 13 as it is, because it turns warnings into
errors. Remove "-Werror" in cmake/CMakeBuild/cmake/modules/BBuildEnv.cmake.

For every variant the script writes the test picture in the coded size as
raw video, encodes it with HM as a single intra picture with the conformance
window of the variant, stores the bitstream as an 'hvc1' image item and
writes the reconstruction of the encoder, cropped to the conformance window,
as reference file.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import List, Sequence, Tuple

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))

from corpuslib import fetch, heifwrite, hevc, testpicture  # noqa: E402

# Coded size of every picture. The output size is smaller by the conformance window.
WIDTH = 256
HEIGHT = 128
QP = 4

# Code points of ISO/IEC 23091-2.
PRIMARIES_BT709 = 1
TRANSFER_SRGB = 13
MATRIX_BT601 = 6


@dataclass(frozen=True)
class Variant:
    name: str
    bit_depth: int
    chroma: str                         # 400, 420, 422 or 444
    window: Tuple[int, int, int, int]   # left, right, top, bottom in luma samples
    profile: str                        # HM name of the profile
    brand: bytes                        # 'heic': Main profile, 'heix': Main 10 and range extensions
    raw_format: str                     # layout of the raw reference file, named like the FFmpeg pixel formats

    @property
    def output_width(self) -> int:
        return WIDTH - self.window[0] - self.window[1]

    @property
    def output_height(self) -> int:
        return HEIGHT - self.window[2] - self.window[3]


VARIANTS = [
    Variant("hevc-confwin-420-8bit-left", 8, "420", (6, 0, 0, 0), "main", b"heic", "yuv420p"),
    Variant("hevc-confwin-420-8bit-top", 8, "420", (0, 0, 6, 0), "main", b"heic", "yuv420p"),
    Variant("hevc-confwin-420-8bit-all", 8, "420", (70, 10, 18, 6), "main", b"heic", "yuv420p"),
    Variant("hevc-confwin-420-10bit-all", 10, "420", (6, 2, 4, 2), "main10", b"heix", "yuv420p10le"),
    Variant("hevc-confwin-422-10bit-all", 10, "422", (6, 2, 3, 0), "main_422_10", b"heix", "yuv422p10le"),
    Variant("hevc-confwin-444-8bit-all", 8, "444", (5, 2, 1, 6), "main_444", b"heix", "yuv444p"),
    Variant("hevc-confwin-400-10bit-all", 10, "400", (7, 0, 3, 0), "monochrome12", b"heix", "gray10le"),
]


def planes_to_raw(planes: Sequence[testpicture.Plane], bit_depth: int) -> bytes:
    """Raw video as HM reads it: one byte per sample for 8 bits, otherwise
    16 bit little endian samples."""
    if bit_depth > 8:
        return testpicture.planes_to_raw16(planes)
    return bytes(v for plane in planes for row in plane for v in row)


def encode(variant: Variant, encoder: Path, config: Path, workdir: Path) -> List[bytes]:
    """Returns [bitstream, reconstruction]."""
    source = workdir / "source.yuv"
    bitstream = workdir / "stream.h265"
    reconstruction = workdir / "reconstruction.yuv"

    planes = testpicture.make_planes(WIDTH, HEIGHT, variant.bit_depth, variant.chroma, identity_matrix=False)
    source.write_bytes(planes_to_raw(planes, variant.bit_depth))

    left, right, top, bottom = variant.window
    cmd = [str(encoder), "-c", str(config),
           "-i", str(source), "-b", str(bitstream), "-o", str(reconstruction),
           "-wdt", str(WIDTH), "-hgt", str(HEIGHT), "-fr", "1", "-f", "1",
           f"--InputBitDepth={variant.bit_depth}",
           f"--InternalBitDepth={variant.bit_depth}",
           f"--OutputBitDepth={variant.bit_depth}",
           f"--InputChromaFormat={variant.chroma}",
           f"--ChromaFormatIDC={variant.chroma}",
           f"--Profile={variant.profile}", "--Level=5.1", f"--QP={QP}",
           # mode 3: the source has the coded size and the window is given explicitly
           "--ConformanceWindowMode=3",
           f"--ConfWinLeft={left}", f"--ConfWinRight={right}",
           f"--ConfWinTop={top}", f"--ConfWinBottom={bottom}",
           "--SEIDecodedPictureHash=1",
           "--VuiParametersPresent=1", "--VideoSignalTypePresent=1", "--VideoFullRange=1",
           "--ColourDescriptionPresent=1", f"--ColourPrimaries={PRIMARIES_BT709}",
           f"--TransferCharacteristics={TRANSFER_SRGB}",
           f"--MatrixCoefficients={MATRIX_BT601}",
           # HM 18.0 refuses to write a VUI without a target bit rate. Rate
           # control stays off, the value is not used.
           "--TargetBitrate=1000000"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise SystemExit(f"{variant.name}: encoder failed\n{result.stdout}\n{result.stderr}")
    return [bitstream.read_bytes(), reconstruction.read_bytes()]


def reference_size(variant: Variant) -> int:
    """Size in bytes of the reconstruction, cropped to the conformance window."""
    w, h = variant.output_width, variant.output_height
    samples = w * h
    if variant.chroma != "400":
        cw = (w + 1) // 2 if variant.chroma in ("420", "422") else w
        ch = (h + 1) // 2 if variant.chroma == "420" else h
        samples += 2 * cw * ch
    return samples * (2 if variant.bit_depth > 8 else 1)


def make_heif(variant: Variant, bitstream: bytes) -> bytes:
    vps, sps, pps, sample = hevc.split_parameter_sets(hevc.split_byte_stream(bitstream))
    info = hevc.parse_sps(sps)
    if (info.width, info.height, info.bit_depth_luma, info.conformance_window) != \
            (WIDTH, HEIGHT, variant.bit_depth, variant.window):
        raise SystemExit(f"{variant.name}: unexpected SPS {info}")

    channels = 1 if variant.chroma == "400" else 3
    properties = [
        heifwrite.Property(heifwrite.make_box(b"hvcC", hevc.make_hvcC_payload(vps, sps, pps)), essential=True),
        # 'ispe' holds the size of the output picture, not the coded size
        heifwrite.ispe(info.cropped_width, info.cropped_height),
        heifwrite.colr_nclx(PRIMARIES_BT709, TRANSFER_SRGB, MATRIX_BT601, True),
        heifwrite.pixi([variant.bit_depth] * channels),
    ]
    return heifwrite.write_single_image(major_brand=variant.brand, compatible_brands=[b"mif1", variant.brand],
                                        item_type=b"hvc1", properties=properties, item_data=sample)


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--encoder", type=Path, required=True, help="HM encoder (TAppEncoderStatic)")
    ap.add_argument("--config", type=Path, required=True, help="HM cfg/encoder_intra_main10.cfg")
    ap.add_argument("--out", type=Path, default=HERE, help="output directory (default: this folder)")
    args = ap.parse_args(argv)

    args.out.mkdir(parents=True, exist_ok=True)
    sums = []
    for variant in VARIANTS:
        with tempfile.TemporaryDirectory() as workdir:
            bitstream, reconstruction = encode(variant, args.encoder, args.config, Path(workdir))
        if len(reconstruction) != reference_size(variant):
            raise SystemExit(f"{variant.name}: the reconstruction has {len(reconstruction)} bytes, "
                             f"expected {reference_size(variant)}")
        for name, data in ((f"{variant.name}.heic", make_heif(variant, bitstream)),
                           (f"{variant.name}.{variant.raw_format}.raw", reconstruction)):
            fetch.write_atomic(args.out / name, data)
            sums.append(f"{fetch.sha256_bytes(data)}  {name}")
            print(f"{name} ({len(data)} bytes)")
    (args.out / "SHA256SUMS").write_text("\n".join(sums) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
