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

import argparse
import sys
from pathlib import Path
from typing import List, Tuple

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))

from corpuslib import fetch, patching  # noqa: E402

SOURCE_NAME = HERE.name
UPSTREAM_REPO = "https://github.com/nokiatech/heif_conformance"
UPSTREAM_COMMIT = "f17e517f7518984b4450349a88edc09519082c74"
UPSTREAM_DIR = "conformance_files"
RAW_URL = "https://raw.githubusercontent.com/nokiatech/heif_conformance/{commit}/{dir}/{name}"


def read_manifest(path: Path) -> List[Tuple[str, str]]:
    entries = []
    for lineno, line in enumerate(path.read_text().splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) != 2 or len(parts[0]) != 64:
            raise SystemExit(f"{path}:{lineno}: expected '<sha256> <file name>'")
        entries.append((parts[1], parts[0].lower()))
    return entries


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, required=True, help="directory for the generated files")
    ap.add_argument("--cache", type=Path, default=ROOT / ".cache" / SOURCE_NAME,
                    help="directory holding the unmodified upstream downloads")
    ap.add_argument("--offline", action="store_true", help="fail instead of downloading missing files")
    ap.add_argument("--only", nargs="+", metavar="FILE", help="build only these files")
    ap.add_argument("--verbose", "-v", action="store_true")
    args = ap.parse_args(argv)

    def log(msg: str) -> None:
        if args.verbose:
            print(f"[{SOURCE_NAME}] {msg}")

    manifest = read_manifest(HERE / "manifest.txt")
    patches = patching.load_patches(HERE / "patches")
    known = {name for name, _ in manifest}
    for target in patches:
        if target not in known:
            raise SystemExit(f"patch target '{target}' is not in manifest.txt")
    if args.only:
        unknown = set(args.only) - known
        if unknown:
            raise SystemExit(f"not in manifest.txt: {', '.join(sorted(unknown))}")
        manifest = [entry for entry in manifest if entry[0] in args.only]

    args.out.mkdir(parents=True, exist_ok=True)
    args.cache.mkdir(parents=True, exist_ok=True)

    downloaded = 0
    patched = 0
    sums = []
    for name, sha in manifest:
        cached = args.cache / name
        if args.offline:
            if not cached.exists() or fetch.sha256_file(cached) != sha:
                raise SystemExit(f"{name}: not in cache (or hash mismatch) and --offline given")
        else:
            url = RAW_URL.format(commit=UPSTREAM_COMMIT, dir=UPSTREAM_DIR, name=name)
            try:
                if fetch.fetch(url, cached, sha, log=log):
                    downloaded += 1
            except fetch.FetchError as e:
                print(f"error: {e}", file=sys.stderr)
                return 1

        data = cached.read_bytes()
        if name in patches:
            try:
                data = patching.apply_patches(data, patches[name], log=log)
            except patching.PatchError as e:
                print(f"error: {e}", file=sys.stderr)
                return 1
            patched += 1
        fetch.write_atomic(args.out / name, data)
        sums.append(f"{fetch.sha256_bytes(data)}  {name}")

    (args.out / "SHA256SUMS").write_text("\n".join(sums) + "\n")
    print(f"[{SOURCE_NAME}] {len(manifest)} files ({downloaded} downloaded, {patched} corrected) -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
