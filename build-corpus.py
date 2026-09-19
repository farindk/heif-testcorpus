#!/usr/bin/env python3
"""Build the produced part of the HEIF test corpus.

Runs the build.py of every source under sources/ and writes its files to
one folder per source under the corpus directory:

    corpus/
      nokiatech-heif-conformance/     produced: C001.heic ... SHA256SUMS
      <own images>/                   committed folders, untouched by this script

Produced folders ignore themselves in git through a generated .gitignore.
The script refuses to write into a non-empty folder that lacks this
marker, so committed image folders cannot be overwritten by a source of
the same name.

Downloads are cached under .cache/ so that later builds (for example
after changing a correction) work offline.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import List

ROOT = Path(__file__).resolve().parent
SOURCES_DIR = ROOT / "sources"
sys.path.insert(0, str(ROOT))

from corpuslib import output  # noqa: E402


def discover_sources() -> List[Path]:
    return sorted(p for p in SOURCES_DIR.iterdir() if (p / "build.py").is_file())


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=ROOT / "corpus", help="output directory (default: corpus/)")
    ap.add_argument("--cache", type=Path, default=ROOT / ".cache", help="download cache (default: .cache/)")
    ap.add_argument("--source", action="append", metavar="NAME", help="build only this source (repeatable)")
    ap.add_argument("--offline", action="store_true", help="fail instead of downloading missing files")
    ap.add_argument("--list", action="store_true", help="list the available sources and exit")
    ap.add_argument("--verbose", "-v", action="store_true")
    args = ap.parse_args(argv)

    sources = discover_sources()
    if args.list:
        for source in sources:
            print(source.name)
        return 0

    if args.source:
        names = {s.name for s in sources}
        unknown = set(args.source) - names
        if unknown:
            print(f"error: unknown source(s): {', '.join(sorted(unknown))}", file=sys.stderr)
            print(f"available: {', '.join(sorted(names))}", file=sys.stderr)
            return 2
        sources = [s for s in sources if s.name in args.source]

    failed = []
    for source in sources:
        try:
            output.prepare_output_dir(args.out / source.name)
        except output.OutputDirError as e:
            print(f"error: {e}", file=sys.stderr)
            failed.append(source.name)
            continue
        cmd = [sys.executable, str(source / "build.py"),
               "--out", str(args.out / source.name),
               "--cache", str(args.cache / source.name)]
        if args.offline:
            cmd.append("--offline")
        if args.verbose:
            cmd.append("--verbose")
        result = subprocess.run(cmd)
        if result.returncode != 0:
            failed.append(source.name)

    if failed:
        print(f"error: {len(failed)} source(s) failed: {', '.join(failed)}", file=sys.stderr)
        return 1
    print(f"corpus complete: {len(sources)} source(s) in {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
