# mpeggroup-fileformatconformance

HEIF files of the MPEG File Format Conformance repository that are not among
the Nokia candidates already covered by `nokiatech-heif-conformance`.

| | |
|---|---|
| Upstream | https://github.com/MPEGGroup/FileFormatConformance |
| Pinned commit | `767a5bcb9fa4841d1b3bb0ca112a6e7d4c6bf067` (2025-05-29, tip of main) |
| Files | 3 of the 48 files in `data/file_features/published/heif/`, 730 kB, stored in Git LFS |
| Descriptions | `<file>.json` and `<file>_gpac.json` next to each file upstream; their description, contributor and licence fields are empty |
| Licence | The repository is published under BSD-3-Clause-Clear (Copyright 2023 Apple Inc.). No separate licence is stated for the files. |

The files are fetched from GitHub's LFS media endpoint at the pinned commit
(the raw repository contents are only the LFS pointer files), verified
against `manifest.txt` and used locally. Because no licence is stated for the
files themselves, they are not redistributed here.

## Why only three files

The upstream directory holds 48 HEIF files. 45 of them were added in one
commit (`44f9288d`, 2023-08-05, "m64382 contribution") and are byte-identical
to the Nokia conformance candidates at the commit pinned by
`nokiatech-heif-conformance` (compared by the sha256 in the LFS pointer
files). They carry the same defects and are corrected there, so they are not
fetched a second time. The remaining three files, produced with GPAC, exist
only in this repository:

| File | Content |
|---|---|
| `iff_hevc_single_item.heic` | One `hvc1` item, 1280x720, HEVC Main, 8 bit. Brands `mif1`, `heic`. |
| `iff_hevc_single_item_main10.heic` | One `hvc1` item, 1920x1080, HEVC Main 10, 10 bit. Brands `mif1`, `heix`. |
| `iff_hevc_tile_multiple_items_tbas.heic` | One 3840x2160 picture (HEVC Main, 8 bit) coded as 2x2 uniformly spaced tiles. Each tile is an `hvt1` item (items 2 to 5, `ispe` 1920x1088) with a `tbas` reference to the `hvc1` base item 1, the primary item. Item 1 stores no data of its own: its `iloc` entry uses construction method 2 with four extents whose `extent_index` selects the `iloc`-type item references to the tile items. The five items share one `hvcC`. Brands `mif1`, `heic`. |

## Corrections applied

Every correction is a module under `patches/` that pins the hash of the
upstream file and the hash of its output. The decoded pictures of a corrected
file are unchanged.

| File | Defect | Correction | Upstream report |
|---|---|---|---|
| `iff_hevc_tile_multiple_items_tbas.heic` | The VPS and the SPS in the shared `hvcC` are not terminated as ISO/IEC 23008-2 7.3.2 requires. The VPS stops after `vps_timing_info_present_flag`; `vps_extension_flag` and `rbsp_trailing_bits()` are missing. The SPS continues after `vui_parameters_present_flag` with the bits `1 0 0 1 0000000`, which read as `sps_extension_present_flag = 1` and `sps_3d_extension_flag = 1` with neither the 3D extension nor `rbsp_trailing_bits()` following. libde265 tolerates both; FFmpeg rejects the VPS ("too many layer_id_included_flags") and then the SPS ("Overread SPS by 8 bits"). | Append `0x40` to the VPS (`vps_extension_flag = 0`, stop bit) and replace the last two SPS bytes `b4 80` with `b2` (`sps_extension_present_flag = 0`, stop bit). The `hvcC` keeps its size, so no offset moves. | not yet reported |

Verification performed on 2026-09-21 for the pinned output:

- FFmpeg's `trace_headers` filter parses the corrected VPS, SPS and PPS
  completely, each ending at `rbsp_stop_one_bit`, and then reads the four
  tile slice headers.
- FFmpeg decodes the corrected parameter sets plus the four tile items to a
  3840x2160 picture that is byte-identical (raw yuv420p) to libde265's decode
  of the upstream file; libde265 decodes the corrected file to the same
  picture.
- Every box except the `hvcC` payload is byte-identical to the upstream file
  and at the same position; the box tree, `iloc`, `iref` and `mdat` are
  unchanged.

## Known defects that are not corrected

| Files | Defect | Assessment |
|---|---|---|
| `iff_hevc_single_item.heic`, `iff_hevc_single_item_main10.heic` | The `bitstream_restriction()` part of the SPS VUI sets `max_bytes_per_pic_denom` to 26 and 66; ISO/IEC 23008-2 E.3.1 allows 0 to 16. | An advisory value that the decoding process never uses. FFmpeg's decoder ignores it (only its stricter `trace_headers` parser reports it); libde265 up to 1.1.1 rejects the whole SPS ("coded parameter out of range") and decodes nothing; libde265 1.1.2 and later clamp it with a warning. Left as is: the files are useful precisely because they exercise this tolerance, and re-encoding the exp-Golomb value would shift the rest of the SPS. |

## Decoder support notes

- libheif (up to 1.23.5) implements neither `hvt1` tile items with `tbas`
  references nor `iloc` construction method 2, so it cannot decode
  `iff_hevc_tile_multiple_items_tbas.heic` with any HEVC plugin. The two
  single-item files decode with libheif's FFmpeg plugin, and with its libde265
  plugin once libde265 1.1.2 or later is installed.
