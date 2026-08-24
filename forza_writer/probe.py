"""Read FH6 process memory at vinyl resource pointers for catalog research."""

from __future__ import annotations

import argparse
import ctypes
import json
import math
import struct
import time
from ctypes import wintypes
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psutil

from forza_writer.shapes import (
    DIGIT_MAP,
    LOWER,
    SYMBOL_MAP,
    UPPER,
    UPPER_SYMBOL_MAP,
    resource_to_shape_word,
)

FH6_PROCESS_NAMES = (
    "ForzaHorizon6.exe",
    "ForzaHorizon6-Win64-Shipping.exe",
    "forzahorizon6.exe",
)
PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
PROCESS_VM_READ = 0x0010
MEM_COMMIT = 0x1000
MEM_PRIVATE = 0x20000
PAGE_NOACCESS = 0x01
PAGE_GUARD = 0x100
RW_MASK = 0xCC

GROUP_COUNT_OFFSET = 0x5A
GROUP_TABLE_OFFSET = 0x78
GROUP_TABLE_END_OFFSET = 0x80
GROUP_TABLE_CAPACITY_OFFSET = 0x88
FULL_LAYER_SIZE = 0x140
LAYER_PROBE_SIZE = 0xC0
RESOURCE_PTR_OFFSET = 0xA8
SHAPE_WORD_OFFSET = 0x7A
TYPE_CODE_BASE = 0x100000

USER_MIN = 0x10000
USER_MAX = 0x7FFFFFFFFFFF

DEFAULT_EXPORT = Path("research/memory/fh6-current-group-12-20260623-144738.json")
DEFAULT_OUTPUT = Path("research/memory/resource_ptr_dump.json")
FILE_READ_SIZE = 512
LIVE_READ_SIZE = 2048
RESOURCE_OBJ_DESCRIPTOR_OFFSET = 0x10
RESOURCE_OBJ_MESH_OFFSET = 0x18
DESCRIPTOR_READ_SIZE = 256

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


class MemoryBasicInformation(ctypes.Structure):
    _fields_ = [
        ("BaseAddress", wintypes.LPVOID),
        ("AllocationBase", wintypes.LPVOID),
        ("AllocationProtect", wintypes.DWORD),
        ("RegionSize", ctypes.c_size_t),
        ("State", wintypes.DWORD),
        ("Protect", wintypes.DWORD),
        ("Type", wintypes.DWORD),
    ]


_k32 = ctypes.WinDLL("kernel32", use_last_error=True)
_k32.OpenProcess.restype = wintypes.HANDLE
_k32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
_k32.CloseHandle.argtypes = (wintypes.HANDLE,)
_k32.ReadProcessMemory.restype = wintypes.BOOL
_k32.ReadProcessMemory.argtypes = (
    wintypes.HANDLE,
    wintypes.LPCVOID,
    wintypes.LPVOID,
    ctypes.c_size_t,
    ctypes.POINTER(ctypes.c_size_t),
)
_k32.VirtualQueryEx.restype = ctypes.c_size_t
_k32.VirtualQueryEx.argtypes = (
    wintypes.HANDLE,
    wintypes.LPCVOID,
    ctypes.POINTER(MemoryBasicInformation),
    ctypes.c_size_t,
)


def parse_address(value: str | int) -> int:
    return int(str(value), 0)


def hx(value: int) -> str:
    return f"0x{int(value):x}"


def bytes_to_hex(data: bytes) -> str:
    return " ".join(f"{byte:02x}" for byte in data)


def finite(value: float, limit: float = 100_000.0) -> bool:
    return math.isfinite(value) and -limit <= value <= limit


def type_word_to_shape_name(type_word: int) -> str:
    for font in range(1, 12):
        for index, char in enumerate(UPPER, start=1):
            family = f"Upper_Letters_{font}"
            if resource_to_shape_word(family, index) == type_word:
                return f"{char} ({family}/{index})"
        for index, char in enumerate(LOWER, start=1):
            family = f"Lower_Letters_{font}"
            if resource_to_shape_word(family, index) == type_word:
                return f"{char} ({family}/{index})"
        for char, index in SYMBOL_MAP.items():
            family = f"Lower_Letters_{font}"
            if resource_to_shape_word(family, index) == type_word:
                return f"{char} ({family}/{index})"
        for char, index in {**DIGIT_MAP, **UPPER_SYMBOL_MAP}.items():
            family = f"Upper_Letters_{font}"
            if resource_to_shape_word(family, index) == type_word:
                return f"{char} ({family}/{index})"
    return f"unknown (type_word={type_word}, hex=0x{type_word:x})"


def find_fh6_pid(pid: int | None = None) -> int:
    if pid is not None:
        return int(pid)
    known = {name.lower() for name in FH6_PROCESS_NAMES}
    for proc in psutil.process_iter(["pid", "name"]):
        try:
            name = (proc.info.get("name") or "").lower()
            if name in known:
                return int(proc.info["pid"])
        except (psutil.Error, psutil.NoSuchProcess):
            continue
    raise RuntimeError(
        "FH6 process not found. Start the game or pass --pid explicitly."
    )


def attach(pid: int) -> int:
    access = PROCESS_QUERY_INFORMATION | PROCESS_QUERY_LIMITED_INFORMATION | PROCESS_VM_READ
    handle = _k32.OpenProcess(access, False, int(pid))
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    return int(handle)


def close_handle(handle: int) -> None:
    if handle:
        _k32.CloseHandle(int(handle))


def read_process_memory(handle: int, address: int, size: int) -> bytes:
    if size <= 0:
        return b""
    buf = ctypes.create_string_buffer(size)
    read = ctypes.c_size_t(0)
    ok = _k32.ReadProcessMemory(
        int(handle), int(address), buf, int(size), ctypes.byref(read)
    )
    if not ok or read.value != size:
        raise RuntimeError(
            f"read failed at {hx(address)} wanted={size} got={read.value}"
        )
    return buf.raw[: read.value]


def try_read_process_memory(handle: int, address: int, size: int) -> tuple[bytes, str | None]:
    try:
        return read_process_memory(handle, address, size), None
    except Exception as exc:
        return b"", str(exc)


def read_partial_memory(handle: int, address: int, size: int) -> bytes:
    if size <= 0:
        return b""
    buf = ctypes.create_string_buffer(size)
    read = ctypes.c_size_t(0)
    ok = _k32.ReadProcessMemory(
        int(handle), int(address), buf, int(size), ctypes.byref(read)
    )
    if not ok or read.value == 0:
        return b""
    return buf.raw[: read.value]


def read_u16(handle: int, address: int) -> int | None:
    raw = read_partial_memory(handle, address, 2)
    return struct.unpack("<H", raw)[0] if len(raw) == 2 else None


def read_u64(handle: int, address: int) -> int | None:
    raw = read_partial_memory(handle, address, 8)
    return struct.unpack("<Q", raw)[0] if len(raw) == 8 else None


def region_is_readable(protect: int) -> bool:
    if protect & PAGE_GUARD or protect & PAGE_NOACCESS:
        return False
    return bool(protect & RW_MASK)


def iter_private_rw_regions(handle: int):
    address = USER_MIN
    info = MemoryBasicInformation()
    while address < USER_MAX:
        queried = _k32.VirtualQueryEx(
            int(handle), address, ctypes.byref(info), ctypes.sizeof(info)
        )
        if not queried:
            address += 0x10000
            continue
        base = int(info.BaseAddress)
        size = int(info.RegionSize)
        if (
            int(info.State) == MEM_COMMIT
            and int(info.Type) == MEM_PRIVATE
            and region_is_readable(int(info.Protect))
        ):
            yield {"base": base, "end": base + size, "size": size}
        next_address = base + size
        if next_address <= address:
            break
        address = next_address


def build_address_contains(regions: list[dict[str, int]]):
    ranges = sorted((region["base"], region["end"]) for region in regions)

    def contains(value: int, size: int = 1) -> bool:
        value = int(value)
        if not (USER_MIN <= value <= USER_MAX) or size < 1:
            return False
        low, high = 0, len(ranges) - 1
        while low <= high:
            mid = (low + high) // 2
            start, end = ranges[mid]
            if value < start:
                high = mid - 1
            elif value + size > end:
                low = mid + 1
            else:
                return True
        return False

    return contains


def layer_looks_valid(handle: int, ptr: int, contains) -> dict[str, Any] | None:
    raw = read_partial_memory(handle, ptr, LAYER_PROBE_SIZE)
    if len(raw) < RESOURCE_PTR_OFFSET + 8:
        return None
    px, py = struct.unpack_from("<ff", raw, 0x18)
    sx, sy = struct.unpack_from("<ff", raw, 0x28)
    rotation = struct.unpack_from("<f", raw, 0x50)[0]
    resource_ptr = struct.unpack_from("<Q", raw, RESOURCE_PTR_OFFSET)[0]
    shape_word = struct.unpack_from("<H", raw, SHAPE_WORD_OFFSET)[0]
    if not all(finite(value) for value in (px, py, sx, sy)):
        return None
    if not finite(rotation, 1_000_000.0):
        return None
    resource_ok = USER_MIN <= resource_ptr <= USER_MAX and contains(resource_ptr, 8)
    return {
        "ok": True,
        "shape_word": shape_word,
        "type_code": TYPE_CODE_BASE + shape_word,
        "resource_ptr_0xa8": hx(resource_ptr) if resource_ok else None,
        "resource_ptr": resource_ptr if resource_ok else 0,
    }


def candidate_rank(candidate: dict[str, Any]) -> tuple:
    count = int(candidate.get("count") or 0)
    valid_ptrs = int(candidate.get("valid_ptrs") or 0)
    invalid_ptrs = int(candidate.get("invalid_ptrs") or 0)
    ok_count = int(candidate.get("layer_ok_count") or 0)
    exact_table = int(valid_ptrs == count and invalid_ptrs == 0)
    exact_ok = int(exact_table and ok_count == count)
    vector_bonus = int(candidate.get("vector_ok") is True)
    source_bonus = 1 if candidate.get("source") == "vector_header" else 0
    return (
        exact_ok,
        exact_table,
        valid_ptrs,
        ok_count,
        -invalid_ptrs,
        vector_bonus,
        source_bonus,
        int(candidate.get("score") or 0),
    )


def keep_top_candidates(candidates: list[dict[str, Any]], item: dict[str, Any], limit: int = 50):
    if not item:
        return
    candidates.append(item)
    candidates.sort(key=candidate_rank, reverse=True)
    del candidates[limit:]


def validate_group_candidate(
    handle: int,
    contains,
    group: int,
    table: int | None,
    count: int,
    source: str,
) -> dict[str, Any] | None:
    if table is None or not contains(group, GROUP_TABLE_CAPACITY_OFFSET + 8):
        return None
    if not contains(table, max(8, count * 8)):
        return None
    if read_u16(handle, group + GROUP_COUNT_OFFSET) != count:
        return None

    table_end = read_u64(handle, group + GROUP_TABLE_END_OFFSET)
    table_capacity = read_u64(handle, group + GROUP_TABLE_CAPACITY_OFFSET)
    if table_end is None or table_capacity is None:
        return None

    expected_end = int(table) + count * 8
    vector_reasons: list[str] = []
    if table_end != expected_end:
        vector_reasons.append(f"table_end={hx(table_end)} expected={hx(expected_end)}")
    if table_capacity < expected_end:
        return None
    if (table_end - table) % 8 or (table_capacity - table) % 8:
        return None
    if not contains(table_capacity - 1):
        return None

    vector_count = (table_end - table) // 8
    capacity_count = (table_capacity - table) // 8
    if vector_count != count:
        vector_reasons.append(f"vector_count={vector_count}")
    if capacity_count < count or capacity_count > max(count + 10_000, count * 16):
        return None

    ptr_raw = read_partial_memory(handle, table, count * 8)
    if len(ptr_raw) != count * 8:
        return None
    ptrs = list(struct.unpack(f"<{count}Q", ptr_raw))
    valid_ptrs = [ptr for ptr in ptrs if contains(ptr, 0x7C)]
    if len(valid_ptrs) < min(count, max(4, count // 4)):
        return None

    ok_count = 0
    for ptr in ptrs:
        summary = layer_looks_valid(handle, ptr, contains)
        if summary and summary.get("ok"):
            ok_count += 1

    invalid_ptrs = max(0, len(ptrs) - len(valid_ptrs))
    duplicate_ptr_count = len(ptrs) - len(set(ptrs)) if ptrs else 0
    vector_ok = not vector_reasons
    exact_bonus = 100_000 if len(valid_ptrs) == count and invalid_ptrs == 0 else 0
    ok_bonus = 50_000 if ok_count == count else 0
    score = (
        exact_bonus
        + ok_bonus
        + len(valid_ptrs) * 10
        + ok_count * 4
        + (1000 if source == "vector_header" else 0)
        + (500 if vector_ok else 0)
        - len(vector_reasons) * 250
        - invalid_ptrs * 100
        - duplicate_ptr_count * 20
    )
    return {
        "score": score,
        "source": source,
        "group": hx(group),
        "table": hx(table),
        "table_end": hx(table_end),
        "table_capacity": hx(table_capacity),
        "count": count,
        "vector_count": vector_count,
        "capacity_count": capacity_count,
        "vector_ok": vector_ok,
        "vector_reasons": vector_reasons,
        "valid_ptrs": len(valid_ptrs),
        "invalid_ptrs": invalid_ptrs,
        "duplicate_ptr_count": duplicate_ptr_count,
        "layer_ok_count": ok_count,
        "layer_ptrs": [hx(ptr) for ptr in ptrs],
    }


def scan_count_header_groups(
    handle: int,
    regions: list[dict[str, int]],
    contains,
    count: int,
    deadline: float | None,
    candidates: list[dict[str, Any]],
    seen: set[int],
):
    pattern = struct.pack("<H", count)
    for region in regions:
        if deadline and time.time() > deadline:
            break
        raw = read_partial_memory(handle, region["base"], min(region["size"], 128 * 1024 * 1024))
        if not raw:
            continue
        offset = 0
        while True:
            hit = raw.find(pattern, offset)
            if hit < 0:
                break
            offset = hit + 1
            group = region["base"] + hit - GROUP_COUNT_OFFSET
            if group in seen or group < region["base"]:
                continue
            table = read_u64(handle, group + GROUP_TABLE_OFFSET)
            item = validate_group_candidate(handle, contains, group, table, count, "count_header")
            if item:
                seen.add(group)
                keep_top_candidates(candidates, item)


def scan_vector_header_groups(
    handle: int,
    regions: list[dict[str, int]],
    contains,
    count: int,
    deadline: float | None,
    candidates: list[dict[str, Any]],
    seen: set[int],
):
    for region in regions:
        if deadline and time.time() > deadline:
            break
        raw = read_partial_memory(handle, region["base"], min(region["size"], 128 * 1024 * 1024))
        if not raw:
            continue
        limit = len(raw) - GROUP_TABLE_CAPACITY_OFFSET - 8
        for offset in range(0, max(0, limit), 8):
            if deadline and time.time() > deadline:
                break
            group = region["base"] + offset
            if group in seen:
                continue
            begin = struct.unpack_from("<Q", raw, offset + GROUP_TABLE_OFFSET)[0]
            end = struct.unpack_from("<Q", raw, offset + GROUP_TABLE_END_OFFSET)[0]
            capacity = struct.unpack_from("<Q", raw, offset + GROUP_TABLE_CAPACITY_OFFSET)[0]
            if end != begin + count * 8:
                continue
            if capacity < end or (capacity - begin) % 8:
                continue
            if not contains(begin, max(8, count * 8)) or not contains(end - 1) or not contains(capacity - 1):
                continue
            item = validate_group_candidate(handle, contains, group, begin, count, "vector_header")
            if item:
                seen.add(group)
                keep_top_candidates(candidates, item)


def locate_vinyl_group(handle: int, layer_count: int, max_seconds: float = 45.0) -> dict[str, Any]:
    regions = list(iter_private_rw_regions(handle))
    contains = build_address_contains(regions)
    candidates: list[dict[str, Any]] = []
    seen: set[int] = set()
    started = time.time()
    count_deadline = started + max(8.0, max_seconds * 0.65) if max_seconds else None
    vector_deadline = started + max_seconds if max_seconds else None

    scan_count_header_groups(handle, regions, contains, layer_count, count_deadline, candidates, seen)

    has_exact = any(
        int(candidate.get("valid_ptrs") or 0) == layer_count
        and int(candidate.get("invalid_ptrs") or 0) == 0
        and int(candidate.get("layer_ok_count") or 0) >= min(8, layer_count)
        for candidate in candidates
    )
    if not has_exact:
        scan_vector_header_groups(handle, regions, contains, layer_count, vector_deadline, candidates, seen)

    candidates.sort(key=candidate_rank, reverse=True)
    if not candidates:
        raise RuntimeError(
            f"No vinyl group with {layer_count} layers found in process memory. "
            "Confirm the correct layer count is loaded in the FH6 vinyl editor."
        )
    return candidates[0]


def read_layer_fields(handle: int, layer_ptr: int) -> dict[str, Any]:
    raw, error = try_read_process_memory(handle, layer_ptr, FULL_LAYER_SIZE)
    if error:
        raw, error = try_read_process_memory(handle, layer_ptr, LAYER_PROBE_SIZE)
    if error or len(raw) < RESOURCE_PTR_OFFSET + 8:
        return {
            "layer_ptr": hx(layer_ptr),
            "read_ok": False,
            "error": error or f"short layer read ({len(raw)} bytes)",
        }

    shape_word = struct.unpack_from("<H", raw, SHAPE_WORD_OFFSET)[0]
    resource_ptr = struct.unpack_from("<Q", raw, RESOURCE_PTR_OFFSET)[0]
    return {
        "layer_ptr": hx(layer_ptr),
        "read_ok": True,
        "type_code": TYPE_CODE_BASE + shape_word,
        "type_word": shape_word,
        "type_word_hex": f"0x{shape_word:x}",
        "resource_ptr_0xa8": hx(resource_ptr),
        "resource_ptr": resource_ptr,
    }


def is_user_pointer(value: int) -> bool:
    return USER_MIN <= int(value) <= USER_MAX


def read_follow_fields(
    handle: int,
    resource_ptr: int,
    *,
    descriptor_read_size: int = DESCRIPTOR_READ_SIZE,
) -> dict[str, Any]:
    header, header_error = try_read_process_memory(handle, resource_ptr, RESOURCE_OBJ_MESH_OFFSET + 8)
    if header_error or len(header) < RESOURCE_OBJ_MESH_OFFSET + 8:
        return {
            "descriptor_ptr": None,
            "descriptor_hex": "",
            "descriptor_read_ok": False,
            "descriptor_bytes_read": 0,
            "mesh_data_ptr": None,
            "follow_error": header_error or f"short resource header ({len(header)} bytes)",
        }

    descriptor_ptr = struct.unpack_from("<Q", header, RESOURCE_OBJ_DESCRIPTOR_OFFSET)[0]
    mesh_data_ptr = struct.unpack_from("<Q", header, RESOURCE_OBJ_MESH_OFFSET)[0]
    follow: dict[str, Any] = {
        "descriptor_ptr": hx(descriptor_ptr) if is_user_pointer(descriptor_ptr) else None,
        "mesh_data_ptr": hx(mesh_data_ptr) if is_user_pointer(mesh_data_ptr) else None,
    }

    if not is_user_pointer(descriptor_ptr):
        follow.update(
            {
                "descriptor_hex": "",
                "descriptor_read_ok": False,
                "descriptor_bytes_read": 0,
                "follow_error": "descriptor pointer out of user range",
            }
        )
        return follow

    desc_raw, desc_error = try_read_process_memory(handle, descriptor_ptr, descriptor_read_size)
    follow["descriptor_hex"] = bytes_to_hex(desc_raw)
    follow["descriptor_read_ok"] = desc_error is None
    follow["descriptor_bytes_read"] = len(desc_raw)
    if desc_error:
        follow["descriptor_error"] = desc_error
    return follow


def build_dump_entry(
    handle: int,
    *,
    layer_index: int,
    layer_number: int | None,
    layer_ptr: str,
    type_word: int,
    type_code: int | None,
    resource_ptr: int,
    resource_ptr_hex: str,
    read_size: int,
    follow: bool = False,
    descriptor_read_size: int = DESCRIPTOR_READ_SIZE,
) -> dict[str, Any]:
    raw, error = try_read_process_memory(handle, resource_ptr, read_size)
    entry: dict[str, Any] = {
        "layer_index": layer_index,
        "layer": layer_number,
        "layer_ptr": layer_ptr,
        "shape_name": type_word_to_shape_name(type_word),
        "type_code": type_code,
        "type_word": type_word,
        "type_word_hex": f"0x{type_word:x}",
        "resource_ptr_0xa8": resource_ptr_hex,
        "read_ok": error is None,
        "bytes_read": len(raw),
        "error": error,
        "hex": bytes_to_hex(raw),
    }
    if follow and error is None:
        entry.update(read_follow_fields(handle, resource_ptr, descriptor_read_size=descriptor_read_size))
    return entry


def dump_live(
    output_path: Path,
    *,
    layer_count: int,
    pid: int | None = None,
    read_size: int = LIVE_READ_SIZE,
    max_seconds: float = 45.0,
    follow: bool = False,
    descriptor_read_size: int = DESCRIPTOR_READ_SIZE,
) -> dict[str, Any]:
    attached_pid = find_fh6_pid(pid)
    handle = attach(attached_pid)

    dumps: list[dict[str, Any]] = []
    located: dict[str, Any] = {}
    try:
        located = locate_vinyl_group(handle, layer_count, max_seconds=max_seconds)
        group = parse_address(located["group"])
        table = parse_address(located["table"])
        ptr_raw = read_process_memory(handle, table, layer_count * 8)
        layer_ptrs = list(struct.unpack(f"<{layer_count}Q", ptr_raw))

        for index, layer_ptr in enumerate(layer_ptrs):
            layer_info = read_layer_fields(handle, layer_ptr)
            if not layer_info.get("read_ok"):
                dumps.append(
                    {
                        "layer_index": index,
                        "layer": index + 1,
                        "layer_ptr": hx(layer_ptr),
                        "read_ok": False,
                        "error": layer_info.get("error"),
                        "hex": "",
                    }
                )
                continue

            resource_ptr = int(layer_info["resource_ptr"])
            dumps.append(
                build_dump_entry(
                    handle,
                    layer_index=index,
                    layer_number=index + 1,
                    layer_ptr=hx(layer_ptr),
                    type_word=int(layer_info["type_word"]),
                    type_code=int(layer_info["type_code"]),
                    resource_ptr=resource_ptr,
                    resource_ptr_hex=str(layer_info["resource_ptr_0xa8"]),
                    read_size=read_size,
                    follow=follow,
                    descriptor_read_size=descriptor_read_size,
                )
            )
    finally:
        close_handle(handle)

    result = {
        "mode": "live",
        "created_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "pid": attached_pid,
        "requested_layer_count": layer_count,
        "located_group": located.get("group"),
        "located_table": located.get("table"),
        "locator_source": located.get("source"),
        "locator_score": located.get("score"),
        "locator_valid_ptrs": located.get("valid_ptrs"),
        "locator_layer_ok_count": located.get("layer_ok_count"),
        "read_size": read_size,
        "layer_count": len(dumps),
        "dumps": dumps,
    }
    if follow:
        result["follow"] = True
        result["descriptor_read_size"] = descriptor_read_size

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def load_layer_entries(export_path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    data = json.loads(export_path.read_text(encoding="utf-8"))

    if data.get("layers"):
        return data, list(data["layers"])

    shapes = data.get("shapes", [])
    if shapes and all("resource_ptr_0xa8" in shape for shape in shapes):
        layers = []
        for index, shape in enumerate(shapes):
            layers.append(
                {
                    "index": index,
                    "type_code": shape.get("type"),
                    "type_word": shape.get("type_word"),
                    "resource_ptr_0xa8": shape["resource_ptr_0xa8"],
                }
            )
        return data, layers

    report_path = export_path.with_name(f"{export_path.stem}.report.json")
    if report_path.exists():
        report = json.loads(report_path.read_text(encoding="utf-8"))
        layers = report.get("layers", [])
        if layers:
            return data, layers

    raise ValueError(
        f"No resource_ptr_0xa8 entries found in {export_path} "
        f"or companion report {report_path.name}"
    )


def export_pid_from_metadata(data: dict[str, Any]) -> int | None:
    source = data.get("source") or {}
    pid = source.get("pid")
    if pid is not None:
        return int(pid)
    top_level_pid = data.get("pid")
    if top_level_pid is not None:
        return int(top_level_pid)
    return None


def dump_resource_pointers(
    export_path: Path,
    output_path: Path,
    *,
    pid: int | None = None,
    read_size: int = FILE_READ_SIZE,
    follow: bool = False,
    descriptor_read_size: int = DESCRIPTOR_READ_SIZE,
) -> dict[str, Any]:
    export_data, layers = load_layer_entries(export_path)
    export_pid = export_pid_from_metadata(export_data)
    attached_pid = find_fh6_pid(pid)
    handle = attach(attached_pid)

    dumps: list[dict[str, Any]] = []
    try:
        for layer in layers:
            resource_ptr = layer.get("resource_ptr_0xa8")
            if not resource_ptr:
                continue

            address = parse_address(resource_ptr)
            type_word = int(layer.get("type_word", 0))

            dumps.append(
                build_dump_entry(
                    handle,
                    layer_index=int(layer.get("index") or 0),
                    layer_number=layer.get("layer"),
                    layer_ptr="",
                    type_word=type_word,
                    type_code=layer.get("type_code"),
                    resource_ptr=address,
                    resource_ptr_hex=str(resource_ptr),
                    read_size=read_size,
                    follow=follow,
                    descriptor_read_size=descriptor_read_size,
                )
            )
    finally:
        close_handle(handle)

    result = {
        "mode": "export",
        "created_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_export": str(export_path.resolve()),
        "export_pid": export_pid,
        "pid": attached_pid,
        "read_size": read_size,
        "layer_count": len(dumps),
        "dumps": dumps,
    }
    if follow:
        result["follow"] = True
        result["descriptor_read_size"] = descriptor_read_size

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def resolve_path(path: Path) -> Path:
    if path.is_absolute():
        return path
    candidate = _PROJECT_ROOT / path
    if candidate.exists() or path.parent != Path("."):
        return candidate
    return candidate


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Dump FH6 memory at vinyl resource_ptr_0xa8 addresses."
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Locate the active vinyl group in memory and dump resource pointers live",
    )
    parser.add_argument(
        "--layers",
        type=int,
        default=None,
        help="Layer count of the vinyl group loaded in the FH6 editor (required with --live)",
    )
    parser.add_argument(
        "--export",
        type=Path,
        default=DEFAULT_EXPORT,
        help="Exported vinyl group JSON for offline dump (report companion used if needed)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Output dump JSON path",
    )
    parser.add_argument(
        "--pid",
        type=int,
        default=None,
        help="FH6 process ID (auto-detected if omitted)",
    )
    parser.add_argument(
        "--read-size",
        type=int,
        default=None,
        help="Bytes to read at each resource pointer (default: 2048 live, 512 export)",
    )
    parser.add_argument(
        "--max-seconds",
        type=float,
        default=45.0,
        help="Memory scan time limit for --live mode",
    )
    parser.add_argument(
        "--follow",
        action="store_true",
        help="Follow resource_ptr+0x10 (descriptor) and +0x18 (mesh_data_ptr)",
    )
    args = parser.parse_args()

    output_path = resolve_path(args.out)

    if args.live:
        if args.layers is None:
            parser.error("--layers is required with --live")
        read_size = args.read_size if args.read_size is not None else LIVE_READ_SIZE
        result = dump_live(
            output_path,
            layer_count=args.layers,
            pid=args.pid,
            read_size=read_size,
            max_seconds=args.max_seconds,
            follow=args.follow,
        )
        print(
            f"Live dump: located group {result['located_group']} "
            f"table {result['located_table']} "
            f"(score {result['locator_score']}, source {result['locator_source']})"
        )
    else:
        export_path = resolve_path(args.export)
        read_size = args.read_size if args.read_size is not None else FILE_READ_SIZE
        result = dump_resource_pointers(
            export_path,
            output_path,
            pid=args.pid,
            read_size=read_size,
            follow=args.follow,
        )

    ok_count = sum(1 for entry in result["dumps"] if entry.get("read_ok"))
    desc_ok = sum(1 for entry in result["dumps"] if entry.get("descriptor_read_ok"))
    summary = (
        f"Wrote {output_path} — {ok_count}/{result['layer_count']} "
        f"reads OK at {result['read_size']} bytes each (pid {result['pid']})"
    )
    if args.follow:
        summary += f"; {desc_ok}/{result['layer_count']} descriptor reads OK"
    print(summary)


if __name__ == "__main__":
    main()
