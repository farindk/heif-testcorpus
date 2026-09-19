"""Verified downloads with a local cache.

A file is only ever accepted when its sha256 matches the value pinned in
the source manifest. The cache holds the unmodified upstream files, so a
rebuild after a patch change needs no network access.
"""

from __future__ import annotations

import hashlib
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable

USER_AGENT = "heif-testcorpus (https://github.com/farindk/heif-testcorpus)"


class FetchError(RuntimeError):
    pass


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_atomic(path: Path, data: bytes) -> None:
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, path)


def fetch(url: str, dest: Path, sha256: str, *, retries: int = 3, timeout: float = 60.0,
          log: Callable[[str], None] = lambda msg: None) -> bool:
    """Ensure dest holds the file at url with the given sha256.

    Returns True when a download happened, False when the cached copy was
    already valid. Raises FetchError when the file cannot be obtained or
    does not match the pinned hash.
    """
    if dest.exists() and sha256_file(dest) == sha256:
        return False

    dest.parent.mkdir(parents=True, exist_ok=True)
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            log(f"downloading {url} (attempt {attempt})")
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=timeout) as response:
                data = response.read()
        except (urllib.error.URLError, OSError) as e:
            last_error = e
            time.sleep(min(2.0 * attempt, 10.0))
            continue

        actual = sha256_bytes(data)
        if actual != sha256:
            raise FetchError(
                f"{url}: sha256 mismatch\n  expected {sha256}\n  received {actual}\n"
                "  The upstream file differs from the pinned version. Refusing to use it.")
        write_atomic(dest, data)
        return True

    raise FetchError(f"{url}: download failed after {retries} attempts: {last_error}")
