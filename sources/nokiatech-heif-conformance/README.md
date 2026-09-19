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

| File | Correction | Upstream report |
|---|---|---|
| C039.heic | Item 1004 (`iden` derived from `iden` 1003) shared the 1280x720 `ispe` of the coded root image. Its input is the 300x300 output of item 1003, so per ISO/IEC 23008-12 6.5.3 and 6.6.1 its `ispe` must be 300x300. A separate `ispe` 300x300 is added and item 1004 is pointed to it. Decoded output is unchanged. | [#11](https://github.com/nokiatech/heif_conformance/issues/11) |

Details, including the spec reasoning and the pinned input and output hashes,
are in the corresponding module under `patches/`.

## Known upstream defects that are not corrected

| Files | Defect | Upstream report |
|---|---|---|
| C004, C007 | Image items after the first are coded as trailing frames depending on the first item's IDR frame, without any dependency signalled in the container. Only fixable by re-encoding. | [#4](https://github.com/nokiatech/heif_conformance/issues/4) |
| C026, C029, C030, C031, C032 | Sequence tracks contain predicted frames but no `stss` box, which marks every sample as a sync sample. | [#8](https://github.com/nokiatech/heif_conformance/issues/8) |
| C034 | The Exif item lacks the mandatory `exif_tiff_header_offset` field in front of the payload. | [#10](https://github.com/nokiatech/heif_conformance/issues/10) |
| C044 | The `rref` property is not conformant (see nokiatech/heif#117). | [#9](https://github.com/nokiatech/heif_conformance/issues/9) |

These files are still part of the generated corpus, unmodified, so that a
decoder's behaviour on them can be tracked. Whether a decoder is expected to
accept, reject or partially decode them is a decision of the consuming
project, not of this corpus.
