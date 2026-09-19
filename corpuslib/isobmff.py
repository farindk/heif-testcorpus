"""Minimal ISO base media file format (ISO/IEC 14496-12) box editing.

This is deliberately small. It knows just enough about the box tree to
append a box to a container, keep the sizes of all enclosing boxes
correct, and shift the absolute file offsets that point behind the edit
('iloc' with construction method 0, 'stco' and 'co64').

Nothing here interprets codec payloads. Every edit is done in place on a
bytearray and the tree is re-parsed afterwards, so a patch module can
chain several edits without tracking offsets itself.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import List, Optional

# Containers whose child boxes start right after the box header.
PLAIN_CONTAINERS = {
    b"moov", b"trak", b"mdia", b"minf", b"stbl", b"edts", b"mvex", b"moof",
    b"traf", b"dinf", b"iprp", b"ipco", b"grpl",
}


def _full_container_prefix(box_type: bytes, version: int) -> Optional[int]:
    """Number of payload bytes between version/flags and the first child of a
    FullBox container, or None when the type is not a container."""
    if box_type in (b"meta", b"iref"):
        return 0
    if box_type in (b"dref", b"stsd"):
        return 4
    if box_type == b"iinf":
        return 2 if version == 0 else 4
    return None


@dataclass
class Box:
    type: bytes
    start: int
    end: int
    header_size: int
    size_to_end: bool = False  # size field was 0: box extends to the end of the file
    children_start: Optional[int] = None
    children: List["Box"] = field(default_factory=list)

    @property
    def size(self) -> int:
        return self.end - self.start

    @property
    def payload_start(self) -> int:
        return self.start + self.header_size

    @property
    def fourcc(self) -> str:
        return self.type.decode("latin-1")

    @property
    def is_container(self) -> bool:
        return self.children_start is not None


def parse_boxes(data, start: int, end: int) -> List[Box]:
    boxes: List[Box] = []
    pos = start
    while pos + 8 <= end:
        size, = struct.unpack_from(">I", data, pos)
        box_type = bytes(data[pos + 4:pos + 8])
        header = 8
        if size == 1:
            if pos + 16 > end:
                raise ValueError(f"truncated largesize header of '{box_type!r}' at {pos}")
            size, = struct.unpack_from(">Q", data, pos + 8)
            header = 16
        to_end = False
        if size == 0:
            size = end - pos
            to_end = True
        if box_type == b"uuid":
            header += 16
        if size < header or pos + size > end:
            raise ValueError(f"box '{box_type!r}' at {pos} has invalid size {size}")

        box = Box(box_type, pos, pos + size, header, to_end)

        children_start = None
        if box_type in PLAIN_CONTAINERS:
            children_start = box.payload_start
        elif box.payload_start + 4 <= box.end:
            version = data[box.payload_start]
            prefix = _full_container_prefix(box_type, version)
            if prefix is not None:
                children_start = box.payload_start + 4 + prefix
        if children_start is not None and children_start <= box.end:
            box.children_start = children_start
            box.children = parse_boxes(data, children_start, box.end)

        boxes.append(box)
        pos = box.end
    if pos != end:
        raise ValueError(f"{end - pos} trailing bytes after the last box at {pos}")
    return boxes


def make_box(box_type: bytes, payload: bytes) -> bytes:
    return struct.pack(">I4s", 8 + len(payload), box_type) + payload


def make_full_box(box_type: bytes, version: int, flags: int, payload: bytes) -> bytes:
    return make_box(box_type, bytes([version]) + flags.to_bytes(3, "big") + payload)


class BoxEditor:
    """In-place editor over a bytearray copy of the file."""

    def __init__(self, data: bytes):
        self.data = bytearray(data)
        self.reparse()

    def reparse(self) -> None:
        self.boxes = parse_boxes(self.data, 0, len(self.data))

    # --- lookup

    def find_path(self, path: str) -> List[Box]:
        """Return the chain of boxes for a path like 'meta/iprp/ipco', taking
        the first match on every level."""
        chain: List[Box] = []
        level = self.boxes
        for name in path.split("/"):
            wanted = name.encode("latin-1")
            for box in level:
                if box.type == wanted:
                    chain.append(box)
                    level = box.children
                    break
            else:
                raise KeyError(f"box path '{path}' not found (missing '{name}')")
        return chain

    def find(self, path: str) -> Box:
        return self.find_path(path)[-1]

    def find_all(self, fourcc: str) -> List[Box]:
        wanted = fourcc.encode("latin-1")

        def walk(boxes: List[Box]) -> List[Box]:
            out = []
            for box in boxes:
                if box.type == wanted:
                    out.append(box)
                out.extend(walk(box.children))
            return out

        return walk(self.boxes)

    def tree(self) -> str:
        lines: List[str] = []

        def walk(boxes: List[Box], depth: int) -> None:
            for box in boxes:
                lines.append(f"{'  ' * depth}{box.fourcc} @{box.start} size={box.size}")
                walk(box.children, depth + 1)

        walk(self.boxes, 0)
        return "\n".join(lines)

    # --- integer access

    def read_uint(self, pos: int, width: int) -> int:
        return int.from_bytes(self.data[pos:pos + width], "big") if width else 0

    def write_uint(self, pos: int, width: int, value: int) -> None:
        self.data[pos:pos + width] = value.to_bytes(width, "big")

    # --- structural edits

    def append_child(self, container_path: str, blob: bytes) -> Box:
        """Append a complete box (header included) as the last child of the
        container at container_path. Enclosing box sizes and absolute file
        offsets behind the insertion point are updated."""
        chain = self.find_path(container_path)
        container = chain[-1]
        if not container.is_container:
            raise ValueError(f"'{container.fourcc}' is not a container")
        pos = container.end
        self._grow(chain, len(blob))
        self._shift_offsets(pos, len(blob))
        self.data[pos:pos] = blob
        self.reparse()
        return self.find(container_path).children[-1]

    def _grow(self, chain: List[Box], delta: int) -> None:
        for box in chain:
            if box.size_to_end:
                continue
            new_size = box.size + delta
            has_largesize = box.header_size in (16, 32)  # 32: uuid box with largesize
            if has_largesize:
                struct.pack_into(">Q", self.data, box.start + 8, new_size)
            else:
                if new_size >= 1 << 32:
                    raise ValueError(f"'{box.fourcc}' would exceed the 32-bit size field")
                struct.pack_into(">I", self.data, box.start, new_size)

    def _shift_offsets(self, pos: int, delta: int) -> None:
        for box in self.find_all("iloc"):
            self._shift_iloc(box, pos, delta)
        for box in self.find_all("stco"):
            self._shift_chunk_offsets(box, pos, delta, 4)
        for box in self.find_all("co64"):
            self._shift_chunk_offsets(box, pos, delta, 8)

    def _shift_iloc(self, box: Box, pos: int, delta: int) -> None:
        p = box.payload_start
        version = self.data[p]
        p += 4
        sizes = self.read_uint(p, 2)
        p += 2
        offset_size = (sizes >> 12) & 0xF
        length_size = (sizes >> 8) & 0xF
        base_offset_size = (sizes >> 4) & 0xF
        index_size = (sizes & 0xF) if version >= 1 else 0
        for width in (offset_size, length_size, base_offset_size, index_size):
            if width not in (0, 4, 8):
                raise ValueError(f"'iloc' has invalid field width {width}")

        id_width = 2 if version < 2 else 4
        item_count = self.read_uint(p, id_width)
        p += id_width

        for _ in range(item_count):
            p += id_width  # item_ID
            construction_method = 0
            if version >= 1:
                construction_method = self.read_uint(p, 2) & 0xF
                p += 2
            data_reference_index = self.read_uint(p, 2)
            p += 2
            base_pos = p
            base_offset = self.read_uint(p, base_offset_size)
            p += base_offset_size
            extent_count = self.read_uint(p, 2)
            p += 2

            shift_base = False
            for _ in range(extent_count):
                p += index_size
                offset_pos = p
                extent_offset = self.read_uint(p, offset_size)
                p += offset_size
                p += length_size

                if construction_method != 0 or data_reference_index != 0:
                    continue  # not a file offset
                if base_offset + extent_offset < pos:
                    continue  # data lies before the edit
                if offset_size > 0:
                    self.write_uint(offset_pos, offset_size, extent_offset + delta)
                elif base_offset_size > 0:
                    shift_base = True
                else:
                    raise ValueError("'iloc' extent has no offset field to shift")
            if shift_base:
                self.write_uint(base_pos, base_offset_size, base_offset + delta)

    def _shift_chunk_offsets(self, box: Box, pos: int, delta: int, width: int) -> None:
        p = box.payload_start + 4
        count = self.read_uint(p, 4)
        p += 4
        for _ in range(count):
            value = self.read_uint(p, width)
            if value >= pos:
                self.write_uint(p, width, value + delta)
            p += width


# --- 'ipma' helpers (item property associations)

def ipma_associations(editor: BoxEditor, path: str = "meta/iprp/ipma") -> dict:
    """Return {item_id: [(essential, property_index), ...]}."""
    box = editor.find(path)
    p = box.payload_start
    version = editor.data[p]
    flags = editor.read_uint(p + 1, 3)
    p += 4
    entry_count = editor.read_uint(p, 4)
    p += 4
    id_width = 2 if version == 0 else 4
    wide = bool(flags & 1)
    result = {}
    for _ in range(entry_count):
        item_id = editor.read_uint(p, id_width)
        p += id_width
        count = editor.data[p]
        p += 1
        assocs = []
        for _ in range(count):
            if wide:
                raw = editor.read_uint(p, 2)
                assocs.append((bool(raw >> 15), raw & 0x7FFF))
                p += 2
            else:
                raw = editor.data[p]
                assocs.append((bool(raw >> 7), raw & 0x7F))
                p += 1
        result[item_id] = assocs
    return result


def ipma_replace_index(editor: BoxEditor, item_id: int, old_index: int, new_index: int,
                       path: str = "meta/iprp/ipma") -> None:
    """Point one association of item_id from property old_index to new_index,
    keeping its essential flag. Field widths are unchanged."""
    box = editor.find(path)
    p = box.payload_start
    version = editor.data[p]
    flags = editor.read_uint(p + 1, 3)
    p += 4
    entry_count = editor.read_uint(p, 4)
    p += 4
    id_width = 2 if version == 0 else 4
    wide = bool(flags & 1)
    limit = 0x7FFF if wide else 0x7F
    if not 1 <= new_index <= limit:
        raise ValueError(f"property index {new_index} does not fit the 'ipma' field width")

    replaced = 0
    for _ in range(entry_count):
        entry_id = editor.read_uint(p, id_width)
        p += id_width
        count = editor.data[p]
        p += 1
        for _ in range(count):
            width = 2 if wide else 1
            raw = editor.read_uint(p, width)
            essential_bit = 1 << (15 if wide else 7)
            index = raw & (essential_bit - 1)
            if entry_id == item_id and index == old_index:
                editor.write_uint(p, width, (raw & essential_bit) | new_index)
                replaced += 1
            p += width
    if replaced == 0:
        raise ValueError(f"item {item_id} has no association with property {old_index}")
