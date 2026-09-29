"""Shared helpers for the source build scripts.

- isobmff:         minimal ISO base media file format box editing for corrections
- hevc:            HEVC NAL unit header inspection, 'hvcC' for an encoded picture
- sampletable:     reading and writing ISOBMFF sample tables
- corrections:     reusable correction operations shared by patch modules
- fetch:           verified downloads with a local cache
- patching:        loading and applying per-file correction modules
- output:          produced corpus folders and their self-ignoring marker
- manifestsource:  build step shared by the sources that mirror third-party files
- generatedsource: build step shared by the sources that generate their images
- avc:             AVC intra picture writer (I_PCM macroblocks) for generated images
- jpeg:            JPEG writers (flat DCT blocks, lossless) for generated images
- heifwrite:       writer for HEIF files with a single coded image item
- testpicture:     the colour gradient test picture of the generated images
"""
