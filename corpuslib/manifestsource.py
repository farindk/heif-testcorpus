"""Build step shared by the sources that mirror third-party files.

Such a source keeps a manifest.txt with the sha256 of every upstream file
and, optionally, correction modules under patches/. Its build.py only
supplies the pinned upstream URL scheme and calls run(), which downloads
every manifest entry into the cache, verifies it, applies the corrections
and writes the results plus a SHA256SUMS file to the output directory.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Callable, List, Tuple

from . import fetch, output, patching

ROOT = Path(__file__).resolve().parents[1]


def read_manifest(path: Path) -> List[Tuple[str, str]]:
    """Return [(file name, sha256)] from a manifest with one
    '<sha256>  <file name>' per line; blank lines and '#' comments are skipped."""
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


def run(argv: List[str], *, source_dir: Path, url_for: Callable[[str], str], description: str) -> int:
    """Command line entry point of a manifest source's build.py.

    source_dir   the sources/<name>/ folder holding manifest.txt and patches/
    url_for      maps a manifest file name to its pinned upstream URL
    description  text for --help, usually the build.py docstring
    """
    source_name = source_dir.name
    ap = argparse.ArgumentParser(description=description, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, required=True, help="directory for the generated files")
    ap.add_argument("--cache", type=Path, default=ROOT / ".cache" / source_name,
                    help="directory holding the unmodified upstream downloads")
    ap.add_argument("--offline", action="store_true", help="fail instead of downloading missing files")
    ap.add_argument("--only", nargs="+", metavar="FILE", help="build only these files")
    ap.add_argument("--verbose", "-v", action="store_true")
    args = ap.parse_args(argv)

    def log(msg: str) -> None:
        if args.verbose:
            print(f"[{source_name}] {msg}")

    manifest = read_manifest(source_dir / "manifest.txt")
    patches = patching.load_patches(source_dir / "patches")
    known = {name for name, _ in manifest}
    for target in patches:
        if target not in known:
            raise SystemExit(f"patch target '{target}' is not in manifest.txt")
    if args.only:
        unknown = set(args.only) - known
        if unknown:
            raise SystemExit(f"not in manifest.txt: {', '.join(sorted(unknown))}")
        manifest = [entry for entry in manifest if entry[0] in args.only]

    try:
        output.prepare_output_dir(args.out)
    except output.OutputDirError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
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
            try:
                if fetch.fetch(url_for(name), cached, sha, log=log):
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
    print(f"[{source_name}] {len(manifest)} files ({downloaded} downloaded, {patched} corrected) -> {args.out}")
    return 0
