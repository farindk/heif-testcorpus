"""Loading and applying per-file correction modules.

A correction is a Python module in a source's patches/ directory that
defines:

    FILE            name of the corpus file it applies to
    DESCRIPTION     one paragraph on what is wrong and what is changed
    UPSTREAM_ISSUE  URL of the report to the file's publisher (or None)
    INPUT_SHA256    sha256 the module expects to receive
    OUTPUT_SHA256   sha256 the module must produce
    apply(data)     bytes -> bytes

Both hashes are checked on every build. A module that receives a file it
was not written for, or that no longer produces the pinned output, stops
the build instead of silently generating something different. Several
modules for the same file are chained in module-name order, each one
seeing the previous module's output.
"""

from __future__ import annotations

import importlib.util
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional

from .fetch import sha256_bytes

REQUIRED = ("FILE", "DESCRIPTION", "INPUT_SHA256", "OUTPUT_SHA256", "apply")


class PatchError(RuntimeError):
    pass


@dataclass
class Patch:
    name: str
    file: str
    description: str
    upstream_issue: Optional[str]
    input_sha256: str
    output_sha256: Optional[str]
    apply: Callable[[bytes], bytes]


def load_patches(patch_dir: Path) -> Dict[str, List[Patch]]:
    """Return {corpus file name: [patches in module-name order]}."""
    patches: Dict[str, List[Patch]] = {}
    if not patch_dir.is_dir():
        return patches
    for module_path in sorted(patch_dir.glob("*.py")):
        if module_path.name.startswith("_"):
            continue
        spec = importlib.util.spec_from_file_location(f"patch_{module_path.stem}", module_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)  # type: ignore[union-attr]
        missing = [attr for attr in REQUIRED if not hasattr(module, attr)]
        if missing:
            raise PatchError(f"{module_path}: missing {', '.join(missing)}")
        patch = Patch(
            name=module_path.stem,
            file=module.FILE,
            description=module.DESCRIPTION.strip(),
            upstream_issue=getattr(module, "UPSTREAM_ISSUE", None),
            input_sha256=module.INPUT_SHA256.lower(),
            output_sha256=module.OUTPUT_SHA256.lower() if module.OUTPUT_SHA256 else None,
            apply=module.apply,
        )
        patches.setdefault(patch.file, []).append(patch)
    return patches


def apply_patches(data: bytes, patches: List[Patch],
                  log: Callable[[str], None] = lambda msg: None) -> bytes:
    for patch in patches:
        actual = sha256_bytes(data)
        if actual != patch.input_sha256:
            raise PatchError(
                f"{patch.name}: input sha256 mismatch for {patch.file}\n"
                f"  expected {patch.input_sha256}\n  received {actual}")
        log(f"applying {patch.name} to {patch.file}")
        result = patch.apply(data)
        produced = sha256_bytes(result)
        if patch.output_sha256 is None:
            raise PatchError(
                f"{patch.name}: OUTPUT_SHA256 is not pinned. The module produced {produced}; "
                "verify the result and pin that value.")
        if produced != patch.output_sha256:
            raise PatchError(
                f"{patch.name}: output sha256 mismatch for {patch.file}\n"
                f"  expected {patch.output_sha256}\n  produced {produced}\n"
                "  The patch code changed its behaviour. Re-verify the output before re-pinning.")
        data = result
    return data
