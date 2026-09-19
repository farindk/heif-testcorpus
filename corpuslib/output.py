"""Output folders of produced corpus parts.

corpus/ holds two kinds of folders: committed ones with our own images, and
produced ones written by a source's build.py. A produced folder ignores
itself in git through a generated .gitignore, which doubles as the marker
that tells the build it may write there. Refusing to write into a folder
without the marker protects committed images from a source of the same name.
"""

from __future__ import annotations

from pathlib import Path

MARKER_NAME = ".gitignore"
MARKER_CONTENT = "# Produced by build-corpus.py, never commit this folder.\n*\n"


class OutputDirError(RuntimeError):
    pass


def is_produced_dir(path: Path) -> bool:
    marker = path / MARKER_NAME
    try:
        return "*" in marker.read_text().splitlines()
    except (FileNotFoundError, OSError, UnicodeDecodeError):
        return False


def prepare_output_dir(path: Path) -> Path:
    """Create the output folder of a produced corpus part, or verify that an
    existing one was produced by a previous build. Raises OutputDirError for
    a non-empty folder without the marker, such as a committed image folder."""
    if path.exists():
        if not path.is_dir():
            raise OutputDirError(f"{path} exists and is not a directory")
        if any(path.iterdir()) and not is_produced_dir(path):
            raise OutputDirError(
                f"{path} is not empty and was not produced by a previous build "
                f"(no self-ignoring {MARKER_NAME}). Refusing to overwrite it; "
                "is a committed corpus folder using the same name as this source?")
    path.mkdir(parents=True, exist_ok=True)
    (path / MARKER_NAME).write_text(MARKER_CONTENT)
    return path
