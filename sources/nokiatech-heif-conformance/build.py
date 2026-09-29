#!/usr/bin/env python3
"""Build step for the Nokia HEIF conformance file candidates.

Downloads every file listed in manifest.txt from the pinned upstream
commit, verifies its sha256, applies the corrections in patches/ and
writes the result to the output directory together with a SHA256SUMS
file of the generated corpus.

Usually run through ../../build-corpus.py, but works standalone:

    ./build.py --out /path/to/corpus/nokiatech-heif-conformance
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))

from corpuslib import manifestsource  # noqa: E402

UPSTREAM_REPO = "https://github.com/nokiatech/heif_conformance"
UPSTREAM_COMMIT = "f17e517f7518984b4450349a88edc09519082c74"
UPSTREAM_DIR = "conformance_files"
RAW_URL = "https://raw.githubusercontent.com/nokiatech/heif_conformance/{commit}/{dir}/{name}"


def upstream_url(name: str) -> str:
    return RAW_URL.format(commit=UPSTREAM_COMMIT, dir=UPSTREAM_DIR, name=name)


if __name__ == "__main__":
    sys.exit(manifestsource.run(sys.argv[1:], source_dir=HERE, url_for=upstream_url, description=__doc__))
