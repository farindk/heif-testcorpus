"""Build step shared by the sources that generate their images.

Such a source has no downloads. Its build.py supplies a function that
returns the generated files and the pinned sha256 of every file, and calls
run(), which verifies the hashes and writes the files plus a SHA256SUMS
file to the output directory.

The pinned hashes keep the corpus bit-identical: an unintended change of a
generator fails the build instead of silently changing the images.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Callable, Dict, List, Tuple

from . import fetch, output


def run(argv: List[str], *, source_dir: Path, generate: Callable[[], List[Tuple[str, bytes]]],
        expected_sha256: Dict[str, str], description: str) -> int:
    """Command line entry point of a generating source's build.py.

    source_dir       the sources/<name>/ folder
    generate         returns [(file name, content)]
    expected_sha256  pinned sha256 of every generated file
    description      text for --help, usually the build.py docstring
    """
    source_name = source_dir.name
    ap = argparse.ArgumentParser(description=description, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, required=True, help="directory for the generated files")
    ap.add_argument("--cache", type=Path, help="unused, nothing is downloaded")
    ap.add_argument("--offline", action="store_true", help="unused, nothing is downloaded")
    ap.add_argument("--print-hashes", action="store_true",
                    help="print the sha256 list for build.py instead of verifying the pinned one")
    ap.add_argument("--verbose", "-v", action="store_true")
    args = ap.parse_args(argv)

    try:
        output.prepare_output_dir(args.out)
    except output.OutputDirError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    files = generate()
    hashes = {name: fetch.sha256_bytes(data) for name, data in files}
    if len(hashes) != len(files):
        print("error: generated file names are not unique", file=sys.stderr)
        return 1

    if args.print_hashes:
        for name, sha in hashes.items():
            print(f'    "{name}":\n        "{sha}",')
    elif hashes != expected_sha256:
        for name, sha in hashes.items():
            if expected_sha256.get(name) != sha:
                print(f"error: {name}: sha256 {sha} differs from the pinned {expected_sha256.get(name)}",
                      file=sys.stderr)
        for name in expected_sha256.keys() - hashes.keys():
            print(f"error: {name}: pinned but not generated", file=sys.stderr)
        return 1

    for name, data in files:
        if args.verbose:
            print(f"[{source_name}] {name} ({len(data)} bytes)")
        fetch.write_atomic(args.out / name, data)
    (args.out / "SHA256SUMS").write_text("".join(f"{sha}  {name}\n" for name, sha in hashes.items()))

    print(f"[{source_name}] {len(files)} files generated -> {args.out}")
    return 0
