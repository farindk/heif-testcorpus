# hevc-high-bitdepth

HEVC images with 9, 11 and 15 bits per sample. x265 encodes 8, 10 and 12 bits
only, so these were encoded with the HEVC reference software HM. They are
committed because recreating them needs an HM build.

| | |
|---|---|
| Origin | Our own test picture, encoded with HM 16.20 (`generate.py`), no third-party material |
| Files | 6 images with one raw reference file each, 800 kB |
| Licence | MIT, as the scripts of this repository (see `LICENSE`) |

## Files

All pictures are 256x128, full range, with colour primaries 1 (BT.709) and
transfer characteristics 13 (sRGB).

| File | Bit depth | Chroma format | Matrix coefficients | HEVC profile |
|---|---|---|---|---|
| `hevc-9bit-400.heic` | 9 | 4:0:0 | 6 (BT.601) | Monochrome 12 |
| `hevc-9bit-420.heic` | 9 | 4:2:0 | 6 (BT.601) | Main 12 |
| `hevc-9bit-444.heic` | 9 | 4:4:4 | 6 (BT.601) | Main 4:4:4 12 |
| `hevc-9bit-444-gbr.heic` | 9 | 4:4:4 | 0 (identity, GBR) | Main 4:4:4 12 |
| `hevc-11bit-420.heic` | 11 | 4:2:0 | 6 (BT.601) | Main 12 |
| `hevc-15bit-420.heic` | 15 | 4:2:0 | 6 (BT.601) | Main 4:4:4 16 Intra |

There are no images with 16 bits, see [Container](#container).

## Picture content

The colour gradient of `corpuslib/testpicture.py`, the same as in
`avc-high-bitdepth`: hue runs from left to right, the top row is white, the
rows in the middle have full saturation, and the bottom row is black. The
files with matrix coefficients 0 store G, B and R in the planes that
otherwise hold Y, Cb and Cr.

## Coding

Each picture is a single intra picture, encoded with
`cfg/encoder_intra_main10.cfg` at QP 4. The coding is lossy. `generate.py`
holds the complete command line.

- HM has to be built with `RExt__HIGH_BIT_DEPTH_SUPPORT`
  (`make release_highbitdepth`). A default build is meant for 8 to 10 bits.
- The bitstream carries the decoded picture hash SEI (MD5).
- `extended_precision_processing_flag` is 0.
- The colour description is written to the VUI and, with the same values, to
  a `colr` box of type `nclx`.

## Container

One `hvc1` image item with the properties `hvcC` (essential), `ispe`, `colr`
and `pixi`. The major brand is `heix`, the brand of the Main 10 and the
format range extensions profiles (ISO/IEC 23008-12 B.4.1.1).

15 bits is the highest bit depth that `hvcC` can signal:
`bit_depth_luma_minus8` and `bit_depth_chroma_minus8` are fields of 3 bits
(ISO/IEC 14496-15:2022, 8.3.2.1.2). HEVC itself allows 16 bits, but there is
no correct `hvcC` for such a stream. Writers that store the low 3 bits of the
value, as GPAC 2.2.1 does, produce a box that states 8 bits. The corpus
therefore has no HEVC images with 16 bits.

## Reference files

`<name>.<pixel format>.raw` holds the reconstruction of the encoder: the
planes in coding order (Y, Cb, Cr or G, B, R), every plane in its own
resolution, as 16 bit little endian samples without any header. HEVC decoding
is specified exactly, so a decoder has to reproduce these files bit by bit.
The pixel format in the file name follows the names of FFmpeg, which itself
has no formats with 11 and 15 bits.

With libheif, decode with `heif_colorspace_undefined` and
`heif_chroma_undefined` and set `output_image_nclx_profile_passthrough` in
the decoding options, otherwise the identity matrix files are converted.

## Notes for decoders

- FFmpeg's HEVC decoder handles 8, 9, 10 and 12 bits (checked in 6.1.1 and
  7.1.1). It cannot decode the files with 11 and 15 bits.
- FFmpeg returns `hevc-9bit-444-gbr.heic` as `yuv444p9le` with colour space
  `gbr`. It maps identity matrix streams to planar GBR at 8, 10 and 12 bits
  only. The planes are the same either way.

## Verification

Performed on 2026-09-29:

- The HM decoder, run on the byte stream rebuilt from each file, confirms the
  picture hash and writes exactly the reference file.
- libheif with libde265 1.1.1 decodes all six files to exactly the reference
  planes, under AddressSanitizer and UndefinedBehaviorSanitizer, and reports
  their bit depth correctly. libheif with its FFmpeg decoder plugin decodes
  the four 9 bit files to the reference planes.
- `generate.py` produces identical files when run twice.
- MP4Box and `heif-info -d` parse the container without complaints.
