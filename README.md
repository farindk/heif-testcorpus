# heif-testcorpus

A reproducible recipe for assembling a HEIF/AVIF test corpus from third-party
sources, for testing HEIF implementations such as [libheif](https://github.com/strukturag/libheif).

The image files themselves are **not** stored in this repository. Every source
pins its origin (repository, commit, sha256 of every file), and the build
script downloads the files, verifies them, and applies scripted corrections to
files that are known to be invalid. Each correction carries the hash of the
file it expects and the hash of the file it produces, so the generated corpus
is bit-identical on every machine.

## Layout

```
build-corpus.py        builds the whole corpus (run this)
corpuslib/             shared helpers: box editing, verified download, patch loading
sources/<name>/        one directory per image source, scripts and hashes only
    build.py           downloads, verifies and corrects the files of this source
    manifest.txt       pinned upstream commit and sha256 of every upstream file
    patches/*.py       one module per correction
    README.md          provenance, licence status, known upstream defects
corpus/<name>/         generated images (git-ignored), plus a SHA256SUMS file
.cache/<name>/         unmodified upstream downloads (git-ignored)
```

Sources currently included:

| Source | Content |
|---|---|
| `nokiatech-heif-conformance` | MPEG HEIF and MIAF conformance file candidates published by Nokia |

## Building the corpus

Requirements: Python 3.8 or newer, no third-party packages. Network access is
needed on the first run only; the downloads are cached in `.cache/`.

```
python3 build-corpus.py
```

This writes the corpus to `corpus/<source>/`. Useful options:

```
python3 build-corpus.py --out /some/dir        # different output directory
python3 build-corpus.py --source NAME          # build one source only
python3 build-corpus.py --offline              # never download, use the cache
python3 build-corpus.py --list                 # list the available sources
python3 build-corpus.py --verbose              # show downloads and patches
```

Every source's `build.py` can also be run on its own, see `--help`.

## Adding a correction

1. Report the defect upstream first and reference the report in the module.
2. Add `sources/<name>/patches/<file>_<topic>.py` defining `FILE`,
   `DESCRIPTION`, `UPSTREAM_ISSUE`, `INPUT_SHA256`, `OUTPUT_SHA256` and
   `apply(data) -> bytes`. Set `OUTPUT_SHA256 = None`, run the build once, verify
   the produced file with an independent decoder, then pin the printed hash.
3. Add the correction to the source's README.

`corpuslib/isobmff.py` provides the box editing needed for container-level
fixes: appending a box to a container and updating all enclosing sizes and
the `iloc`, `stco` and `co64` file offsets behind the edit. Defects in the
coded bitstream itself cannot be corrected this way; list those in the
source's README as known defects instead.

## Adding a source

Create `sources/<name>/` with a `build.py` that accepts `--out`, `--cache`,
`--offline` and `--verbose`, and writes the generated files plus a
`SHA256SUMS` file to `--out`. `build-corpus.py` picks it up automatically.

## Licence

The scripts in this repository are released under the MIT licence, see
`LICENSE`. The downloaded image files remain the property of their respective
publishers and are subject to their terms; see the README of each source. They
are downloaded for local testing and are not redistributed here.
