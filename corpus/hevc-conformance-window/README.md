# hevc-conformance-window

HEVC images with a conformance window that crops the coded picture on the
left and at the top. x265 and the other common encoders use the conformance
window only to remove the padding at the right and at the bottom, so that
offsets on the other two sides are rarely tested. These images were encoded
with the HEVC reference software HM. They are committed because recreating
them needs an HM build.

| | |
|---|---|
| Origin | Our own test picture, encoded with HM 18.0 (`generate.py`), no third-party material |
| Files | 7 images with one raw reference file each, 520 kB |
| Licence | MIT, as the scripts of this repository (see `LICENSE`) |

## Files

All pictures have the coded size 256x128 and are full range, with colour
primaries 1 (BT.709), transfer characteristics 13 (sRGB) and matrix
coefficients 6 (BT.601). The window offsets are given in luma samples.

| File | Bit depth | Chroma format | Left | Right | Top | Bottom | Output size | HEVC profile | Brand |
|---|---|---|---|---|---|---|---|---|---|
| `hevc-confwin-420-8bit-left.heic` | 8 | 4:2:0 | 6 | 0 | 0 | 0 | 250x128 | Main | `heic` |
| `hevc-confwin-420-8bit-top.heic` | 8 | 4:2:0 | 0 | 0 | 6 | 0 | 256x122 | Main | `heic` |
| `hevc-confwin-420-8bit-all.heic` | 8 | 4:2:0 | 70 | 10 | 18 | 6 | 176x104 | Main | `heic` |
| `hevc-confwin-420-10bit-all.heic` | 10 | 4:2:0 | 6 | 2 | 4 | 2 | 248x122 | Main 10 | `heix` |
| `hevc-confwin-422-10bit-all.heic` | 10 | 4:2:2 | 6 | 2 | 3 | 0 | 248x125 | Main 4:2:2 10 | `heix` |
| `hevc-confwin-444-8bit-all.heic` | 8 | 4:4:4 | 5 | 2 | 1 | 6 | 249x121 | Main 4:4:4 | `heix` |
| `hevc-confwin-400-10bit-all.heic` | 10 | 4:0:0 | 7 | 0 | 3 | 0 | 249x125 | Monochrome 12 | `heix` |

The SPS codes the offsets in units of chroma samples. With 4:2:0 all offsets
are even, with 4:2:2 the horizontal ones. 4:4:4 and 4:0:0 allow odd offsets
and output pictures of odd size.

## Picture content

The colour gradient of `corpuslib/testpicture.py` in the coded size, the same
as in `hevc-high-bitdepth`: hue runs from left to right, the top row is
white, the rows in the middle have full saturation, and the bottom row is
black. The output picture is the part of it inside the conformance window. A
decoder that ignores an offset shows a picture that is shifted and too large.

## Coding

Each picture is a single intra picture, encoded with
`cfg/encoder_intra_main10.cfg` at QP 4. The coding is lossy. `generate.py`
holds the complete command line.

- The window is set with `ConformanceWindowMode=3`. The source picture has
  the coded size, nothing is padded.
- The bitstream carries the decoded picture hash SEI (MD5). The hash covers
  the whole coded picture, not only the conformance window.
- The colour description is written to the VUI and, with the same values, to
  a `colr` box of type `nclx`.

## Container

One `hvc1` image item with the properties `hvcC` (essential), `ispe`, `colr`
and `pixi`. The major brand is `heic` for the Main profile and `heix` for the
Main 10 and the format range extensions profiles (ISO/IEC 23008-12 B.4.1.1).

`ispe` holds the output size, not the coded size. The reconstructed image of
a coded image item is the output of the decoding process (ISO/IEC
23008-12:2025, 6.3), which for HEVC is the picture cropped to the conformance
window, and `ispe` documents the size of that image (6.5.3). No `clap`
property is involved.

## Reference files

`<name>.<pixel format>.raw` holds the reconstruction of the encoder, cropped
to the conformance window: the planes in coding order (Y, Cb, Cr), every
plane in its own resolution, without any header. The samples of the images
with 8 bits are single bytes, those of the images with 10 bits are 16 bit
little endian. HEVC decoding is specified exactly, so a decoder has to
reproduce these files bit by bit. The pixel format in the file name follows
the names of FFmpeg.

With libheif, decode with `heif_colorspace_undefined` and
`heif_chroma_undefined` and set `output_image_nclx_profile_passthrough` in
the decoding options.

## Notes for decoders

- libavcodec applies the left offset exactly only when the codec context has
  the flag `AV_CODEC_FLAG_UNALIGNED`. Without it, the offset is rounded down
  to keep the plane pointers aligned, the frame is wider than the output
  size, and the crop fields of the frame are cleared. With 4:2:0, every left
  offset below 64 is dropped completely. For `hevc-confwin-400-10bit-all.heic`
  and its odd offset, decoding fails with an internal error instead. Checked
  in FFmpeg 6.1.1. The offsets at the other three sides are not affected.
- The command line tool of FFmpeg 6.1.1 needs `-flags unaligned` for the same
  reason.
- libheif with its FFmpeg decoder plugin fails on the six files with a left
  offset up to version 1.23.5. Five are refused because the decoded image
  does not have the size signaled in the file, the monochrome one fails in
  the decoder. Pull request 1922 of libheif sets the flag.
- libde265 up to version 1.1.3 decodes the three files with 10 bits to a
  wrong picture of the right size. It adds the window offsets to the plane
  pointers in samples instead of bytes, so that half the offset is applied.
  The files with 8 bits are decoded correctly. The versions after 1.1.3
  scale the offsets and decode all seven files correctly.

## Verification

Performed on 2026-09-30:

- The HM 18.0 decoder, run on the byte stream rebuilt from each file,
  confirms the picture hash and writes exactly the reference file.
- The command line decoder of FFmpeg 6.1.1 with `-flags unaligned` writes
  exactly the reference file for all seven streams.
- libheif with its FFmpeg decoder plugin and pull request 1922 applied
  decodes all seven files to exactly the reference planes.
- libheif with libde265 1.1.3 does so for the four files with 8 bits. With
  the corrected window offsets in libde265, it does so for all seven files.
- `generate.py` produces identical files when run twice.
- MP4Box and `heif-info -d` parse the container without complaints.
