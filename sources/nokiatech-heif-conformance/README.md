# nokiatech-heif-conformance

HEIF and MIAF conformance file candidates published by Nokia, generated with
the [Nokia HEIF writer](https://github.com/nokiatech/heif) and submitted to
MPEG as conformance bitstream candidates for ISO/IEC 23008-12.

| | |
|---|---|
| Upstream | https://github.com/nokiatech/heif_conformance |
| Pinned commit | `f17e517f7518984b4450349a88edc09519082c74` (2022-01-17, tip of master) |
| Files | 63 files from `conformance_files/` (C001 to C053, MIAF001 to MIAF007, multilayer001 to multilayer005), 21 MB |
| Descriptions | `conformance_file_descriptions.xlsx` in the upstream repository |
| Licence | None stated. Upstream issue [#3](https://github.com/nokiatech/heif_conformance/issues/3) asking for one has been open since 2019. |

Because no licence is stated, the files are not redistributed here. They are
downloaded from the pinned commit at build time, verified against
`manifest.txt` and used locally for the conformance testing the upstream
README invites.

The upstream repository has not been updated since January 2022 and defect
reports go unanswered, which is why corrections are maintained here.

## Corrections applied

Every correction is a module under `patches/` that pins the hash of the
upstream file and the hash of its output. The decoded pictures of a corrected
file are unchanged; only container metadata is fixed.

| File | Defect | Correction | Upstream report |
|---|---|---|---|
| C026, C029, C030, C031, C032 | Only sample 1 of each HEVC track is an IRAP picture (IDR_W_RADL), samples 2 to 8 are TRAIL_R, but there is no `stss`. Per ISO/IEC 14496-12 8.6.2.1 every sample is then a sync sample. | Classify each sample by its NAL unit types and append `stss` listing the IRAP samples to each track's `stbl` (C031 and C032 have two tracks each). | [#8](https://github.com/nokiatech/heif_conformance/issues/8) |
| C034 | The Exif item starts directly with the TIFF header; the `exif_tiff_header_offset` field required by ISO/IEC 23008-12 A.2.1 is missing. | Insert a zero offset field in front of the item data and grow the `iloc` extent from 176 to 180 bytes. | [#10](https://github.com/nokiatech/heif_conformance/issues/10) |
| C039 | Item 1004 (`iden` derived from `iden` 1003) shared the 1280x720 `ispe` of the coded root image. Its input is the 300x300 output of item 1003, so per ISO/IEC 23008-12 6.5.3 and 6.6.1 its `ispe` must be 300x300. | Add a separate `ispe` 300x300 and point item 1004 to it. | [#11](https://github.com/nokiatech/heif_conformance/issues/11) |
| C043, C044 | `rref` stores `reference_type_count` as a 32-bit field; ISO/IEC 23008-12 6.5.17.2 defines it as 8 bits (writer bug nokiatech/heif#117). The report names C044 only; C043 has the same defect. | Rewrite the `rref` box with an 8-bit count (three bytes shorter). | [#9](https://github.com/nokiatech/heif_conformance/issues/9) |

Verification performed on 2026-09-19 for the pinned outputs:

- `stss`: ffprobe flags only the first packet of every track as a key frame
  (all packets before), MP4Box reports "Only one sync sample" instead of "All
  samples are sync", and the decoded frame count is unchanged (8, or 13 for
  C029 with its edit list), which confirms the shifted chunk offsets.
- C034: exiftool no longer warns "Missing Exif header" and lists the IFD0 and
  ExifIFD tags; libheif reports the 180-byte Exif block; the decoded picture
  is byte-identical (y4m) to the upstream file.
- C039: libheif 1.23.0 and the current master decode all three images
  pixel-identically to libheif 1.23.0 decoding the upstream file.
- C043, C044: libheif parses the 8-bit form and reports the same "unsupported
  reference type pred" as for the upstream files, which shows the 'pred' entry
  is read from the corrected field.

## Reported upstream defects that are not corrected

| Files | Report | Assessment |
|---|---|---|
| C004, C007 | [#4](https://github.com/nokiatech/heif_conformance/issues/4) (2020): items after the first are trailing frames depending on the first item's IDR picture. | Not reproducible on the pinned commit. Every `hvc1` item in both files is a single IDR_N_LP access unit, libheif decodes C004 to ten distinct images with an independent decoder per item, and the files were last changed upstream in 2019, before the report. |

Files that use features a given decoder does not support (for example `pred`
item references in C043 and C044, or layered HEVC in the multilayer files)
are conformant and unmodified. Whether a decoder is expected to accept,
reject or partially decode them is a decision of the consuming project, not
of this corpus.
