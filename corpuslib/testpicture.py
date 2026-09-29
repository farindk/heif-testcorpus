"""The colour gradient test picture of the generated images.

Everything is computed with integer arithmetic, so the picture is
bit-identical on every machine.
"""

from __future__ import annotations

from typing import List, Sequence, Tuple

Plane = List[List[int]]


def rainbow_rgb(width: int, height: int, bit_depth: int) -> Tuple[Plane, Plane, Plane]:
    """Hue runs from left to right through red, yellow, green, cyan, blue and
    magenta. The top row is white, the rows in the middle have full
    saturation, the bottom row is black. The picture contains the lowest and
    the highest code value in every component."""
    maxv = (1 << bit_depth) - 1
    half = height // 2

    red: Plane = []
    green: Plane = []
    blue: Plane = []
    for y in range(height):
        rows: Tuple[List[int], List[int], List[int]] = ([], [], [])
        for x in range(width):
            segment, f = divmod(x * 6 * maxv // width, maxv)
            rgb = ((maxv, f, 0), (maxv - f, maxv, 0), (0, maxv, f),
                   (0, maxv - f, maxv), (f, 0, maxv), (maxv, 0, maxv - f))[segment]
            for row, c in zip(rows, rgb):
                if y < half:
                    saturation = y * maxv // (half - 1)
                    row.append(maxv - (maxv - c) * saturation // maxv)
                else:
                    value = (height - 1 - y) * maxv // (half - 1)
                    row.append(c * value // maxv)
        red.append(rows[0])
        green.append(rows[1])
        blue.append(rows[2])
    return red, green, blue


def _round_div(a: int, b: int) -> int:
    """a / b rounded to the nearest integer, halves rounded up."""
    return (2 * a + b) // (2 * b)


def rgb_to_ycbcr_bt601_full_range(red: Plane, green: Plane, blue: Plane, bit_depth: int
                                  ) -> Tuple[Plane, Plane, Plane]:
    maxv = (1 << bit_depth) - 1
    mid = 1 << (bit_depth - 1)

    luma: Plane = []
    cb: Plane = []
    cr: Plane = []
    for row_r, row_g, row_b in zip(red, green, blue):
        row_y = [_round_div(299 * r + 587 * g + 114 * b, 1000) for r, g, b in zip(row_r, row_g, row_b)]
        luma.append(row_y)
        cb.append([min(maxv, max(0, mid + _round_div((b - y) * 1000, 1772))) for b, y in zip(row_b, row_y)])
        cr.append([min(maxv, max(0, mid + _round_div((r - y) * 1000, 1402))) for r, y in zip(row_r, row_y)])
    return luma, cb, cr


def subsample(plane: Plane, horizontal: bool, vertical: bool) -> Plane:
    """Average 2x1 or 2x2 samples, halves rounded up."""
    if horizontal:
        plane = [[(row[x] + row[x + 1] + 1) // 2 for x in range(0, len(row), 2)] for row in plane]
    if vertical:
        plane = [[(a + b + 1) // 2 for a, b in zip(plane[y], plane[y + 1])] for y in range(0, len(plane), 2)]
    return plane


def make_planes(width: int, height: int, bit_depth: int, chroma: str, identity_matrix: bool) -> List[Plane]:
    """The picture in coding order. chroma is '400', '420', '422' or '444'.
    With identity_matrix the planes hold G, B, R (4:4:4 only), otherwise full
    range YCbCr with the BT.601 coefficients."""
    red, green, blue = rainbow_rgb(width, height, bit_depth)

    if identity_matrix:
        if chroma != "444":
            raise ValueError("the identity matrix needs 4:4:4")
        return [green, blue, red]

    luma, cb, cr = rgb_to_ycbcr_bt601_full_range(red, green, blue, bit_depth)
    if chroma == "400":
        return [luma]
    if chroma not in ("420", "422", "444"):
        raise ValueError(f"unknown chroma format {chroma}")
    horizontal = chroma in ("420", "422")
    vertical = chroma == "420"
    return [luma, subsample(cb, horizontal, vertical), subsample(cr, horizontal, vertical)]


def planes_to_raw16(planes: Sequence[Plane]) -> bytes:
    """Planes in the given order, 16 bit little endian samples, no header."""
    return b"".join(v.to_bytes(2, "little") for plane in planes for row in plane for v in row)
