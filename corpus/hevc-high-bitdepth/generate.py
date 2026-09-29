#!/usr/bin/env python3
"""Recipe that produced the images in this folder.

This is not a build step: the images are committed, because producing them
needs the HEVC reference software HM built with support for high bit depths.
The script documents how they were made and recreates them if needed.

    git clone https://vcgit.hhi.fraunhofer.de/jvet/HM.git
    cd HM/build/linux && make release_highbitdepth      (HM 16.20)
    ./generate.py --encoder HM/bin/TAppEncoderHighBitDepthStatic \\
                  --config HM/cfg/encoder_intra_main10.cfg

For every variant the script writes the test picture as raw video, encodes
it with HM as a single intra picture, stores the bitstream as an 'hvc1'
image item and writes the reconstruction of the encoder as reference file.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import List

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))

from corpuslib import fetch, heifwrite, hevc, testpicture  # noqa: E402

WIDTH = 256
HEIGHT = 128
QP = 4

# Code points of ISO/IEC 23091-2.
PRIMARIES_BT709 = 1
TRANSFER_SRGB = 13
MATRIX_IDENTITY = 0   # planes hold G, B, R
MATRIX_BT601 = 6


@dataclass(frozen=True)
class Variant:
    name: str
    bit_depth: int
    chroma: str          # 400, 420 or 444
    matrix_coefficients: int
    profile: str         # HM name of the profile
    raw_format: str      # layout of the raw reference file, named like the FFmpeg pixel formats


VARIANTS = [
    Variant("hevc-9bit-400", 9, "400", MATRIX_BT601, "monochrome12", "gray9le"),
    Variant("hevc-9bit-420", 9, "420", MATRIX_BT601, "main12", "yuv420p9le"),
    Variant("hevc-9bit-444", 9, "444", MATRIX_BT601, "main_444_12", "yuv444p9le"),
    Variant("hevc-9bit-444-gbr", 9, "444", MATRIX_IDENTITY, "main_444_12", "gbrp9le"),
    Variant("hevc-11bit-420", 11, "420", MATRIX_BT601, "main12", "yuv420p11le"),
    Variant("hevc-15bit-420", 15, "420", MATRIX_BT601, "main_444_16_intra", "yuv420p15le"),
    Variant("hevc-16bit-400", 16, "400", MATRIX_BT601, "main_444_16_intra", "gray16le"),
    Variant("hevc-16bit-420", 16, "420", MATRIX_BT601, "main_444_16_intra", "yuv420p16le"),
    Variant("hevc-16bit-444", 16, "444", MATRIX_BT601, "main_444_16_intra", "yuv444p16le"),
    Variant("hevc-16bit-444-gbr", 16, "444", MATRIX_IDENTITY, "main_444_16_intra", "gbrp16le"),
]


def encode(variant: Variant, encoder: Path, config: Path, workdir: Path) -> List[bytes]:
    """Returns [bitstream, reconstruction]."""
    source = workdir / "source.yuv"
    bitstream = workdir / "stream.h265"
    reconstruction = workdir / "reconstruction.yuv"

    planes = testpicture.make_planes(WIDTH, HEIGHT, variant.bit_depth, variant.chroma,
                                     identity_matrix=variant.matrix_coefficients == MATRIX_IDENTITY)
    source.write_bytes(testpicture.planes_to_raw16(planes))

    cmd = [str(encoder), "-c", str(config),
           "-i", str(source), "-b", str(bitstream), "-o", str(reconstruction),
           "-wdt", str(WIDTH), "-hgt", str(HEIGHT), "-fr", "1", "-f", "1",
           f"--InputBitDepth={variant.bit_depth}",
           f"--InternalBitDepth={variant.bit_depth}",
           f"--OutputBitDepth={variant.bit_depth}",
           f"--InputChromaFormat={variant.chroma}",
           f"--ChromaFormatIDC={variant.chroma}",
           f"--Profile={variant.profile}", "--Level=5.1", f"--QP={QP}",
           "--SEIDecodedPictureHash=1",
           "--VuiParametersPresent=1", "--VideoSignalTypePresent=1", "--VideoFullRange=1",
           "--ColourDescriptionPresent=1", f"--ColourPrimaries={PRIMARIES_BT709}",
           f"--TransferCharacteristics={TRANSFER_SRGB}",
           f"--MatrixCoefficients={variant.matrix_coefficients}",
           # HM 16.20 refuses to write a VUI without a target bit rate. Rate
           # control stays off, the value is not used.
           "--TargetBitrate=1000000"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise SystemExit(f"{variant.name}: encoder failed\n{result.stdout}\n{result.stderr}")
    return [bitstream.read_bytes(), reconstruction.read_bytes()]


def make_heif(variant: Variant, bitstream: bytes) -> bytes:
    vps, sps, pps, sample = hevc.split_parameter_sets(hevc.split_byte_stream(bitstream))
    info = hevc.parse_sps(sps)
    if (info.width, info.height, info.bit_depth_luma) != (WIDTH, HEIGHT, variant.bit_depth):
        raise SystemExit(f"{variant.name}: unexpected SPS {info}")

    channels = 1 if variant.chroma == "400" else 3
    properties = [
        heifwrite.Property(heifwrite.make_box(b"hvcC", hevc.make_hvcC_payload(vps, sps, pps)), essential=True),
        heifwrite.ispe(WIDTH, HEIGHT),
        heifwrite.colr_nclx(PRIMARIES_BT709, TRANSFER_SRGB, variant.matrix_coefficients, True),
        heifwrite.pixi([variant.bit_depth] * channels),
    ]
    # 'heix' is the brand of the Main 10 and the format range extensions
    # profiles (ISO/IEC 23008-12 B.4.1.1).
    return heifwrite.write_single_image(major_brand=b"heix", compatible_brands=[b"mif1", b"heix"],
                                        item_type=b"hvc1", properties=properties, item_data=sample)


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--encoder", type=Path, required=True, help="HM encoder built with high bit depth support")
    ap.add_argument("--config", type=Path, required=True, help="HM cfg/encoder_intra_main10.cfg")
    ap.add_argument("--out", type=Path, default=HERE, help="output directory (default: this folder)")
    args = ap.parse_args(argv)

    args.out.mkdir(parents=True, exist_ok=True)
    sums = []
    for variant in VARIANTS:
        with tempfile.TemporaryDirectory() as workdir:
            bitstream, reconstruction = encode(variant, args.encoder, args.config, Path(workdir))
        for name, data in ((f"{variant.name}.heic", make_heif(variant, bitstream)),
                           (f"{variant.name}.{variant.raw_format}.raw", reconstruction)):
            fetch.write_atomic(args.out / name, data)
            sums.append(f"{fetch.sha256_bytes(data)}  {name}")
            print(f"{name} ({len(data)} bytes)")
    (args.out / "SHA256SUMS").write_text("\n".join(sums) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
