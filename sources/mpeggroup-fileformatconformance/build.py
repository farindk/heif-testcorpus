#!/usr/bin/env python3
"""Build step for the HEIF files of the MPEG File Format Conformance repository.

Downloads every file listed in manifest.txt from the pinned upstream
commit, verifies its sha256, applies the corrections in patches/ and
writes the result to the output directory together with a SHA256SUMS
file of the generated corpus.

Upstream stores the files in Git LFS, so they are fetched from GitHub's
LFS media endpoint; the raw repository contents would only yield the
pointer files.

Usually run through ../../build-corpus.py, but works standalone:

    ./build.py --out /path/to/corpus/mpeggroup-fileformatconformance
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))

from corpuslib import manifestsource  # noqa: E402

UPSTREAM_REPO = "https://github.com/MPEGGroup/FileFormatConformance"
UPSTREAM_COMMIT = "767a5bcb9fa4841d1b3bb0ca112a6e7d4c6bf067"
UPSTREAM_DIR = "data/file_features/published/heif"
LFS_URL = "https://media.githubusercontent.com/media/MPEGGroup/FileFormatConformance/{commit}/{dir}/{name}"


def upstream_url(name: str) -> str:
    return LFS_URL.format(commit=UPSTREAM_COMMIT, dir=UPSTREAM_DIR, name=name)


if __name__ == "__main__":
    sys.exit(manifestsource.run(sys.argv[1:], source_dir=HERE, url_for=upstream_url, description=__doc__))
