"""
Generate a ForzaTech modelbin from a TTF/OTF glyph. Straight-line contours
pass through unchanged; TrueType quadratic and CFF/OTF cubic Bezier curves
are flattened into line segments via De Casteljau subdivision.

Usage:
    python tools/gen_modelbin.py --char A --font-file "C:\\path\\to\\font.ttf" --out data/modelbin/CUSTOM_A.modelbin
    python tools/gen_modelbin.py --char A --font-file "C:\\path\\to\\font.ttf"  # outputs data/modelbin/CUSTOM_A.modelbin by default
    python tools/gen_modelbin.py --char O --font-file "C:\\path\\to\\font.ttf" --curve-segments 12  # smoother curves

Requires a reference modelbin (default: user-assets/S_01.modelbin) to copy the
material/mesh/layout chunks from. This file is an extracted FH6 game asset
and is not included in this repo, see README.md for how to obtain it.
"""
import argparse
import struct
import sys
import threading
from pathlib import Path

import mapbox_earcut as earcut
import numpy as np
from fontTools.pens.recordingPen import RecordingPen
from fontTools.ttLib import TTFont

# Progress messages below print arbitrary glyph characters (e.g. when
# batch-generating a font's full symbol/punctuation range). Windows consoles
# default to a codepage (cp1252 etc.) that can't encode most of Unicode, and
# a bare print() of an unencodable character raises UnicodeEncodeError and
# kills the batch. Fall back to backslash-escaping anything the console
# can't display rather than crashing on it.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(errors="backslashreplace")
        except Exception:
            pass

DEFAULT_REFERENCE_MODELBIN = Path("user-assets/S_01.modelbin")

# ForzaTech SNORM16 scale: coord / 128.0 * 32767
COORD_SCALE = 32767.0 / 128.0

# Expected chunk layout of a generated vinyl modelbin, used for validation.
EXPECTED_CHUNK_TAGS = ['Skel', 'MatI', 'Mesh', 'IndB', 'VLay', 'VerB', 'VerB', 'Modl']


def char_filename(prefix: str, char: str) -> str:
    """Filesystem-safe output filename for a glyph.

    Windows filesystems are case-insensitive, so PREFIX_A and PREFIX_a would
    collide as files. Lowercase letters get an explicit `_lc` marker to keep
    every glyph's file distinct regardless of prefix. (The shape catalog
    itself is case-sensitive; only the on-disk name needs disambiguation.)
    """
    if char.isalpha() and char.islower():
        return f"{prefix}_{char}_lc.modelbin"
    return f"{prefix}_{char}.modelbin"


# Per-thread cache of (TTFont, cmap) keyed by resolved font path. A full
# fontpack/composition run calls glyph_in_font()/extract_contours() once per
# character, up to a few hundred times for a large charset. Opening the font
# file itself is cheap (~0.5ms), but getBestCmap() is not: it merges/decodes
# the font's cmap subtables and takes ~5-19ms on real installed fonts, so
# without caching, re-deriving it on every single glyph turns a ~100-glyph
# run into roughly a second of pure repeated work reconstructing the exact
# same mapping. Caching the opened font per path avoids that, cutting a
# measured 94-glyph pass from ~960ms to ~17ms with identical output (the
# cmap and glyph outlines are static for the file's lifetime, so there's
# nothing to invalidate mid-run).
#
# threading.local() rather than a shared module-level dict: this app runs
# generation/scanning on their own freshly-spawned background threads, and
# fontTools' TTFont does lazy, state-mutating table parsing on first access,
# so sharing one mutable TTFont across threads without a lock would be a real
# race. Thread-local sidesteps that entirely (each thread gets its own
# TTFont instances, so there's nothing to lock) while still eliminating the
# redundant work within any single loop, which is where the actual cost
# is. Each new Thread() this app spawns starts with an empty cache, so
# there's no cross-run staleness or unbounded growth to manage either.
_font_cache_local = threading.local()


def _open_font(font_path: Path) -> tuple[TTFont, dict[int, str]]:
    """Return (TTFont, cmap) for `font_path`, reusing this thread's already
    -opened instance if this thread has already loaded that path."""
    cache = getattr(_font_cache_local, "cache", None)
    if cache is None:
        cache = {}
        _font_cache_local.cache = cache
    key = str(font_path)
    cached = cache.get(key)
    if cached is not None:
        return cached
    font = TTFont(str(font_path), fontNumber=0)
    cmap = font.getBestCmap()
    cache[key] = (font, cmap)
    return font, cmap


def glyph_in_font(char: str, font_path: Path) -> bool:
    """True if the font has a cmap entry for this character."""
    _font, cmap = _open_font(font_path)
    return ord(char) in cmap


# ---------------------------------------------------------------------------
# Glyph extraction
# ---------------------------------------------------------------------------

def _quad_point(p0, p1, p2, t):
    """Point at parameter t on a quadratic Bezier curve (De Casteljau)."""
    mt = 1.0 - t
    x = mt * mt * p0[0] + 2 * mt * t * p1[0] + t * t * p2[0]
    y = mt * mt * p0[1] + 2 * mt * t * p1[1] + t * t * p2[1]
    return (x, y)


def _cubic_point(p0, p1, p2, p3, t):
    """Point at parameter t on a cubic Bezier curve (De Casteljau)."""
    mt = 1.0 - t
    x = mt**3 * p0[0] + 3 * mt * mt * t * p1[0] + 3 * mt * t * t * p2[0] + t**3 * p3[0]
    y = mt**3 * p0[1] + 3 * mt * mt * t * p1[1] + 3 * mt * t * t * p2[1] + t**3 * p3[1]
    return (x, y)


def _flatten_quadratic(p0, p1, p2, segments):
    return [_quad_point(p0, p1, p2, i / segments) for i in range(1, segments + 1)]


def _flatten_cubic(p0, p1, p2, p3, segments):
    return [_cubic_point(p0, p1, p2, p3, i / segments) for i in range(1, segments + 1)]


def _decompose_qcurve(start, pts, segments):
    """Flatten a fontTools qCurveTo point list into line points.

    TrueType glyphs can chain several quadratic segments in one qCurveTo
    call, with on-curve points implied as the midpoint between successive
    off-curve control points (only the final point is guaranteed on-curve).
    A single-point call has no control point at all and is a straight line.
    """
    if pts[-1] is None:
        raise ValueError(
            "fully off-curve (implied-start) contours are not supported"
        )
    if len(pts) == 1:
        return [pts[0]]

    flat = []
    controls = pts[:-1]
    end = pts[-1]
    prev = start
    for i, control in enumerate(controls):
        if i == len(controls) - 1:
            segment_end = end
        else:
            nxt = controls[i + 1]
            segment_end = ((control[0] + nxt[0]) / 2.0, (control[1] + nxt[1]) / 2.0)
        flat.extend(_flatten_quadratic(prev, control, segment_end, segments))
        prev = segment_end
    return flat


def _decompose_curve(start, pts, segments):
    """Flatten a fontTools curveTo point list (one or more chained cubic
    Bezier segments, each defined by 2 control points + an endpoint)."""
    flat = []
    prev = start
    for i in range(0, len(pts), 3):
        c1, c2, end = pts[i], pts[i + 1], pts[i + 2]
        flat.extend(_flatten_cubic(prev, c1, c2, end, segments))
        prev = end
    return flat


def extract_contours(char: str, font_path: Path, curve_segments: int = 8):
    """Return list of contours as lists of (x, y) points in font units.

    Straight-line contours pass through unchanged. TrueType quadratic curves
    (qCurveTo) and CFF/OTF cubic curves (curveTo) are flattened into
    `curve_segments` line segments each via De Casteljau subdivision.
    """
    font, cmap = _open_font(font_path)
    cp = ord(char)
    if cp not in cmap:
        raise ValueError(f"Glyph {char!r} not in font")
    return extract_glyph_contours(cmap[cp], font_path, curve_segments)


def extract_glyph_contours(glyph_name: str, font_path: Path, curve_segments: int = 8):
    """Return contours for an explicit OpenType glyph name.

    Shaped scripts cannot be recovered by looking up each Unicode character
    in cmap: HarfBuzz may substitute contextual forms, ligatures, or reordered
    glyphs.  This entry point draws that shaped glyph identity directly.
    Empty-outline glyphs (spaces, join controls, layout glyphs) return an
    empty contour list and are valid composition tokens.
    """
    font, _cmap = _open_font(font_path)
    gs = font.getGlyphSet()
    if glyph_name not in gs:
        raise ValueError(f"Glyph name {glyph_name!r} not in font")
    pen = RecordingPen()
    gs[glyph_name].draw(pen)

    contours = []
    current = []
    start = None
    for op, pts in pen.value:
        if op == "moveTo":
            current = [pts[0]]
            start = pts[0]
        elif op == "lineTo":
            current.append(pts[0])
            start = pts[0]
        elif op == "curveTo":
            current.extend(_decompose_curve(start, pts, curve_segments))
            start = current[-1]
        elif op == "qCurveTo":
            current.extend(_decompose_qcurve(start, pts, curve_segments))
            start = current[-1]
        elif op == "closePath":
            if current:
                contours.append(current)
            current = []
            start = None
    return contours, font['head'].unitsPerEm


def glyph_bbox_and_scale(contours) -> tuple[float, float, float]:
    """The (center_x, center_y, scale) `normalize_to_128` derives from a
    glyph's own raw bounding box: `scale` maps `max(width, height)` to 200
    units (±100), `(center_x, center_y)` is the raw bbox center it
    recenters onto (0, 0). Split out so callers that need to *reverse* a
    single glyph's independent normalization, e.g.
    `forza_writer/text_compose.py`, which re-expresses each glyph on a
    shared font-wide scale/baseline instead of its own bbox, can recover
    exactly the transform that was actually applied, rather than
    re-deriving (and risking drifting from) the same bbox math twice.
    """
    all_pts = [pt for c in contours for pt in c]
    if not all_pts:
        raise ValueError("glyph has no drawable outline")
    xs = [p[0] for p in all_pts]
    ys = [p[1] for p in all_pts]
    x_min, x_max = min(xs), max(xs)
    y_min, y_max = min(ys), max(ys)

    w = x_max - x_min or 1
    h = y_max - y_min or 1
    scale = 200.0 / max(w, h)  # fit into ±100
    cx = (x_min + x_max) / 2.0
    cy = (y_min + y_max) / 2.0
    return cx, cy, scale


def normalize_to_128(contours, units_per_em: int):
    """Scale font contours from [0, units_per_em] to [-128, +128] space.

    FH6 vinyl coords are centred at origin. We scale so the glyph fits
    in ±100 (leaving a small border), and centre it on x=0, y=0.
    """
    cx, cy, scale = glyph_bbox_and_scale(contours)
    result = []
    for c in contours:
        result.append([(  (p[0] - cx) * scale,
                          (p[1] - cy) * scale  ) for p in c])
    return result


# ---------------------------------------------------------------------------
# Triangulation
# ---------------------------------------------------------------------------

def _point_in_polygon(x: float, y: float, poly) -> bool:
    """Standard ray-casting point-in-polygon test."""
    inside = False
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        if (y1 > y) != (y2 > y):
            x_at_y = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
            if x < x_at_y:
                inside = not inside
    return inside


def group_contours_by_nesting(contours_norm):
    """Partition glyph contours into earcut-ready `(outer_index,
    [hole_indices])` islands via a geometric containment tree, rather than
    assuming contour 0 is always the outer boundary: that assumption
    silently mis-triangulates any glyph whose first-drawn contour isn't its
    largest one, which decorative/display fonts hit often (disjoint accent
    marks, dots, swash flourishes listed before the main letterform). See
    `forza_writer/primitive_fit.py::rasterize_contours`'s docstring for the
    raster-space version of the same bug, found on Jokerman's 'K' (5
    disjoint contours: the main stroke plus 4 separate sparkle accents,
    with a sparkle first).

    Containment is determined per contour by point-in-polygon (one vertex
    of each contour tested against every other contour's boundary) so it
    doesn't depend on contour order. Nesting *depth* (how many other
    contours contain a given contour) alternates fill/hole exactly like the
    even-odd fill rule; a contour's immediate *parent* is the containing
    contour exactly one level up (`depth == depth[self] - 1`). Every
    even-depth contour becomes its own island's outer ring (a disjoint
    component, or a filled "island" nested two-or-more holes deep); every
    odd-depth contour becomes a hole belonging to its immediate parent's
    island. This is what correctly separates "this hole has an unrelated
    filled shape nested inside it" (that shape gets its own earcut() call)
    from "this hole is just a hole" (single-level nesting, one call).
    """
    n = len(contours_norm)
    containing: list[set[int]] = []
    for i in range(n):
        test_x, test_y = contours_norm[i][0]
        containing.append({j for j in range(n)
                            if j != i and _point_in_polygon(test_x, test_y, contours_norm[j])})
    depth = [len(containing[i]) for i in range(n)]

    parent: list[int | None] = [None] * n
    for i in range(n):
        for j in containing[i]:
            if depth[j] == depth[i] - 1:
                parent[i] = j
                break

    groups: dict[int, list[int]] = {i: [] for i in range(n) if depth[i] % 2 == 0}
    for i in range(n):
        if depth[i] % 2 == 1 and parent[i] is not None:
            groups[parent[i]].append(i)
    return [(outer, holes) for outer, holes in groups.items()]


def triangulate(contours_norm):
    """Triangulate polygon-with-holes glyph contours via earcut.

    One earcut() call per disjoint island (`group_contours_by_nesting`),
    since earcut's own outer-ring-plus-holes-list API can't express
    disjoint components (e.g. a letter's main stroke plus a separate
    decorative accent mark) in a single call. The results are merged with
    vertex-index offsets applied per island.

    Returns (vertices_xy, triangles): vertices_xy is a flat list of (x, y)
    floats across every island, triangles are index-tuples into that same
    combined list.
    """
    contours_norm = [c for c in contours_norm if len(c) >= 3]
    if not contours_norm:
        return [], []

    all_verts: list[tuple[float, float]] = []
    all_tris: list[tuple[int, int, int]] = []
    for outer_idx, hole_idxs in group_contours_by_nesting(contours_norm):
        rings = [contours_norm[outer_idx]] + [contours_norm[h] for h in hole_idxs]
        # earcut wants flat [x0,y0, x1,y1, ...] + cumulative-end-of-each-ring indices
        flat = []
        ring_ends = []
        for c in rings:
            for x, y in c:
                flat.extend([x, y])
            ring_ends.append(len(flat) // 2)

        verts = np.array(flat, dtype=np.float64).reshape(-1, 2)
        ring_ends_arr = np.array(ring_ends, dtype=np.uint32)
        indices = earcut.triangulate_float64(verts, ring_ends_arr)

        offset = len(all_verts)
        all_verts.extend((float(x), float(y)) for x, y in verts)
        for i in range(0, len(indices), 3):
            all_tris.append((int(indices[i]) + offset, int(indices[i + 1]) + offset,
                              int(indices[i + 2]) + offset))

    return all_verts, all_tris


# ---------------------------------------------------------------------------
# Modelbin binary writer
# ---------------------------------------------------------------------------

def to_snorm16(v: float) -> int:
    """Convert float in [-128, 128] to signed int16 SNORM."""
    s = v * COORD_SCALE
    return max(-32767, min(32767, int(round(s))))


# Buffer chunks (IndB/VerB) start with a 16-byte header:
#   count:u32, total_bytes:u32, stride:u16, flags:u16, format:i32
# The last field is a DXGI_FORMAT code, NOT a repeat of the count
# (S_01 reference: 13=R16G16B16A16_SNORM positions, 37=R16G16_SNORM
# first attribute of the stride-36 stream, 57=R16_UINT indices).
# flags/format are read from the reference buffers, never hardcoded.

# Attribute stream (second VerB, stride 36) per-vertex layout, per VLay:
#   0x00 NORMAL    R16G16_SNORM      constant across the reference
#   0x04 TEXCOORD0 R16G16_UNORM      varies per vertex (uv in glyph bbox)
#   0x08 TEXCOORD1-3                 zero in the reference
#   0x14 TANGENT0  R10G10B10A2_UNORM +/-X unit tangents in the reference
#   0x18 TANGENT1-2                  zero in the reference
#   0x20 COLOR     R8G8B8A8_UNORM
# Everything except TEXCOORD0 is copied from the reference's first vertex.
ATTR_TEXCOORD0_OFFSET = 4


def parse_buffer_header(data, off=0):
    """Return (count, total_bytes, stride, flags, dxgi_format)."""
    return struct.unpack_from('<IIHHi', data, off)


def pack_buffer_header(count, stride, flags, fmt):
    return struct.pack('<IIHHi', count, count * stride, stride, flags, fmt)


def pack_verB(vertices_xy, flags, fmt):
    """Pack the position stream. stride=8: x:i16, y:i16, z=0, w=0."""
    vdata = b"".join(struct.pack('<hh4x', to_snorm16(x), to_snorm16(y))
                     for x, y in vertices_xy)
    return pack_buffer_header(len(vertices_xy), 8, flags, fmt) + vdata


def pack_verB2(vertices_xy, template_row, flags, fmt):
    """Pack the full-attribute stream with one row per actual vertex.

    template_row is the reference mesh's first attribute row; only
    TEXCOORD0 is rewritten, as the vertex's UNORM16 position inside the
    glyph bounding box (v axis flipped, DirectX convention).
    """
    stride = len(template_row)
    xs = [x for x, _ in vertices_xy]
    ys = [y for _, y in vertices_xy]
    x_min, x_max = min(xs), max(xs)
    y_min, y_max = min(ys), max(ys)
    w = (x_max - x_min) or 1.0
    h = (y_max - y_min) or 1.0

    rows = []
    for x, y in vertices_xy:
        u = round((x - x_min) / w * 65535)
        v = round((y_max - y) / h * 65535)
        row = bytearray(template_row)
        struct.pack_into('<HH', row, ATTR_TEXCOORD0_OFFSET, u, v)
        rows.append(bytes(row))
    return pack_buffer_header(len(vertices_xy), stride, flags, fmt) + b"".join(rows)


def pack_indB(triangles, flags, fmt):
    """Pack index buffer chunk data. stride=2: uint16 indices."""
    indices = []
    for t in triangles:
        indices.extend(t)
    count = len(indices)
    idata = struct.pack(f'<{count}H', *indices)
    return pack_buffer_header(count, 2, flags, fmt) + idata


# The Mesh chunk embeds the draw counts; leaving the reference's values in
# place makes the game draw the wrong number of primitives. Offsets within
# the Mesh chunk data, verified against S_01 (45 indices / 15 tris / 23 verts):
MESH_INDEX_COUNT_OFFSET = 42   # u32
MESH_TRI_COUNT_OFFSET = 46     # u32
MESH_VERTS_PER_TRI_OFFSET = 50  # f32, vertex_count / triangle_count
MESH_VERT_COUNT_OFFSET = 54    # u32


def patch_mesh_counts(mesh_data, ref_counts, new_counts):
    """Rewrite the (index, triangle, vertex) counts inside a Mesh chunk.

    ref_counts are the counts read from the reference's own buffers; they
    must match what the Mesh chunk already says, otherwise the offsets
    above don't hold for this reference file and we refuse to guess.
    """
    ref_idx, ref_tri, ref_vert = ref_counts
    found = (struct.unpack_from('<I', mesh_data, MESH_INDEX_COUNT_OFFSET)[0],
             struct.unpack_from('<I', mesh_data, MESH_TRI_COUNT_OFFSET)[0],
             struct.unpack_from('<I', mesh_data, MESH_VERT_COUNT_OFFSET)[0])
    if found != (ref_idx, ref_tri, ref_vert):
        raise ValueError(
            f"reference Mesh chunk counts {found} don't match its buffers "
            f"({ref_idx}, {ref_tri}, {ref_vert}); Mesh layout differs from S_01")

    new_idx, new_tri, new_vert = new_counts
    patched = bytearray(mesh_data)
    struct.pack_into('<I', patched, MESH_INDEX_COUNT_OFFSET, new_idx)
    struct.pack_into('<I', patched, MESH_TRI_COUNT_OFFSET, new_tri)
    struct.pack_into('<f', patched, MESH_VERTS_PER_TRI_OFFSET, new_vert / new_tri)
    struct.pack_into('<I', patched, MESH_VERT_COUNT_OFFSET, new_vert)
    return bytes(patched)


def build_modelbin(char: str, font_path: Path, reference_modelbin: Path, curve_segments: int = 8,
                    flip_winding: bool = True) -> bytes:
    """Build a complete modelbin binary for the given character."""
    ref = reference_modelbin.read_bytes()

    # Parse reference Grub header to locate chunks we'll copy verbatim
    def read_tag(data, off):
        return data[off:off+4][::-1].decode('ascii', errors='replace')

    def parse_grub(data, off):
        data_offset = struct.unpack_from('<I', data, off+8)[0]
        chunk_count = struct.unpack_from('<I', data, off+16)[0]
        chunks = {}
        pos = off + 20
        for _ in range(chunk_count):
            tag = read_tag(data, pos)
            abs_off = struct.unpack_from('<I', data, pos+12)[0]
            size_a = struct.unpack_from('<I', data, pos+16)[0]
            chunks[tag] = (abs_off, size_a)
            pos += 24
        return chunks, data_offset

    top_chunks, _ = parse_grub(ref, 0)

    # S_01's Grub chunk layout is flat (all chunks at top level): Skel, MatI,
    # Mesh, IndB, VLay, VerB, VerB, Modl. Skel, MatI, Mesh, VLay, and Modl are
    # copied verbatim; IndB and the first VerB are regenerated below.

    # Extract verbatim chunks from reference
    def get_chunk(tag):
        if tag not in top_chunks:
            return None
        off, size = top_chunks[tag]
        return ref[off:off+size]

    skel_data = get_chunk('Skel')
    mati_data = get_chunk('MatI')
    mesh_data = get_chunk('Mesh')
    vlay_data = get_chunk('VLay')
    modl_data = get_chunk('Modl')

    # Second VerB (the larger one with full vertex attribs): copy verbatim.
    # parse_grub's dict is keyed by tag, so it only keeps one of the two VerB
    # entries; walk the chunk table directly to recover both, in order.
    all_chunks = []
    pos = 20
    chunk_count = struct.unpack_from('<I', ref, 16)[0]
    for _ in range(chunk_count):
        tag = read_tag(ref, pos)
        unk = struct.unpack_from('<H', ref, pos+4)[0]
        unk2 = struct.unpack_from('<H', ref, pos+6)[0]
        abs_off = struct.unpack_from('<I', ref, pos+12)[0]
        size_a = struct.unpack_from('<I', ref, pos+16)[0]
        all_chunks.append((tag, unk, unk2, abs_off, size_a))
        pos += 24

    verB_entries = [(unk, unk2, abs_off, size_a)
                    for tag, unk, unk2, abs_off, size_a in all_chunks if tag == 'VerB']
    # First VerB is position-only (stride=8), second is the full-attribute
    # stream. Both are regenerated; flags/format codes and the attribute
    # template row come from the reference.
    verB1_abs = verB_entries[0][2]
    verB2_abs = verB_entries[1][2]
    v1_count, _, v1_stride, v1_flags, v1_fmt = parse_buffer_header(ref, verB1_abs)
    v2_count, _, v2_stride, v2_flags, v2_fmt = parse_buffer_header(ref, verB2_abs)
    if v1_count != v2_count:
        raise ValueError(f"reference VerB counts disagree: {v1_count} vs {v2_count}")
    template_row = ref[verB2_abs + 16:verB2_abs + 16 + v2_stride]

    indB_abs = top_chunks['IndB'][0]
    ref_index_count, _, _, i_flags, i_fmt = parse_buffer_header(ref, indB_abs)

    # Generate glyph geometry
    contours, upm = extract_contours(char, font_path, curve_segments)
    contours_norm = normalize_to_128(contours, upm)
    vertices, triangles = triangulate(contours_norm)

    # earcut's winding doesn't match the reference: S_01's triangles are
    # majority clockwise (in this SNORM16 coordinate space) while earcut's
    # output here is uniformly counter-clockwise. If the renderer backface
    # -culls, that mismatch alone is enough to make every triangle invisible.
    if flip_winding:
        triangles = [(a, c, b) for a, b, c in triangles]

    print(f"  Glyph '{char}': {len(contours)} contours, "
          f"{len(vertices)} verts, {len(triangles)} tris"
          f"{' (winding flipped)' if flip_winding else ''}")

    new_verB1 = pack_verB(vertices, v1_flags, v1_fmt)
    new_verB2 = pack_verB2(vertices, template_row, v2_flags, v2_fmt)
    new_indB = pack_indB(triangles, i_flags, i_fmt)

    mesh_data = patch_mesh_counts(
        mesh_data,
        ref_counts=(ref_index_count, ref_index_count // 3, v1_count),
        new_counts=(len(triangles) * 3, len(triangles), len(vertices)))

    # Reassemble Grub binary
    # Order: Skel, MatI, Mesh(patched counts), IndB, VLay, VerB, VerB2, Modl
    chunk_payloads = [
        ('Skel', 1, 0,    skel_data),
        ('MatI', 1, 2,    mati_data),
        ('Mesh', 3073, 2, mesh_data),
        ('IndB', 1, 1,    new_indB),
        ('VLay', 257, 1,  vlay_data),
        ('VerB', 257, 1,  new_verB1),
        ('VerB', 257, 1,  new_verB2),
        ('Modl', 1025, 1, modl_data),
    ]

    # Layout: Grub header (20 bytes) + chunk table (8 chunks * 24 bytes = 192 bytes)
    # then chunk data
    GRUB_HEADER_SIZE = 20
    CHUNK_ENTRY_SIZE = 24
    n_chunks = len(chunk_payloads)
    data_section_start = GRUB_HEADER_SIZE + n_chunks * CHUNK_ENTRY_SIZE

    # Compute absolute offsets for each chunk payload
    abs_offsets = []
    cursor = data_section_start
    for _, _, _, payload in chunk_payloads:
        abs_offsets.append(cursor)
        cursor += len(payload)

    total_data_size = cursor - data_section_start
    file_size = cursor

    # Build Grub header: tag(4), version(2), flags(2), data_offset(4), data_size(4), count(4)
    def write_tag(s): return s.encode('ascii')[::-1]

    grub_header = (write_tag('Grub')
                   + struct.pack('<HH', 257, 0)           # version=0x101, flags=0
                   + struct.pack('<II', data_section_start, total_data_size)
                   + struct.pack('<I', n_chunks))

    # Build chunk table
    chunk_table = b""
    for i, (tag, unk, unk2, payload) in enumerate(chunk_payloads):
        abs_off = abs_offsets[i]
        size = len(payload)
        # Entry: tag(4), unk(2), unk2(2), chunk_off(4), abs(4), size_a(4), size_b(4)
        # chunk_off = abs_off - data_section_start (relative to data section)
        chunk_off = abs_off - data_section_start
        entry = (write_tag(tag)
                 + struct.pack('<HH', unk, unk2)
                 + struct.pack('<IIII', chunk_off, abs_off, size, size))
        chunk_table += entry

    # Assemble
    data_section = b"".join(payload for _, _, _, payload in chunk_payloads)
    result = grub_header + chunk_table + data_section

    assert len(result) == file_size
    return result


def _parse_chunk_table(data: bytes) -> list[tuple[str, int, int]]:
    """Walk a Grub chunk table, returning [(tag, abs_offset, size), ...] in
    file order. Raises ValueError on a truncated/malformed table; callers
    that want a (bool, message) result instead should catch that (see
    validate_modelbin); callers that just want the chunks (read_mesh_triangles)
    can let it propagate."""
    if len(data) < 20 or data[0:4][::-1] != b'Grub':
        raise ValueError("missing Grub magic")
    chunk_count = struct.unpack_from('<I', data, 16)[0]
    chunks = []
    pos = 20
    for _ in range(chunk_count):
        if pos + 24 > len(data):
            raise ValueError("chunk table truncated")
        tag = data[pos:pos + 4][::-1].decode('ascii', errors='replace')
        abs_off = struct.unpack_from('<I', data, pos + 12)[0]
        size = struct.unpack_from('<I', data, pos + 16)[0]
        if abs_off + size > len(data):
            raise ValueError(f"chunk {tag} extends past end of file")
        chunks.append((tag, abs_off, size))
        pos += 24
    return chunks


def validate_modelbin(path: Path) -> tuple[bool, str]:
    """Structural and consistency check. Verifies the expected 8-chunk
    layout, that both vertex buffers hold the same number of vertices,
    that no index reaches past either buffer, and that the Mesh chunk's
    embedded draw counts match the actual buffers. Returns (ok, message)."""
    try:
        data = path.read_bytes()
        chunks = _parse_chunk_table(data)
        tags = [tag for tag, _off, _size in chunks]
        if tags != EXPECTED_CHUNK_TAGS:
            return False, f"unexpected chunk layout: {tags}"

        verbs = [(off, size) for tag, off, size in chunks if tag == 'VerB']
        indb_off = next(off for tag, off, size in chunks if tag == 'IndB')
        mesh_off = next(off for tag, off, size in chunks if tag == 'Mesh')

        v1_count, v1_bytes, v1_stride, _, _ = parse_buffer_header(data, verbs[0][0])
        v2_count, v2_bytes, v2_stride, _, _ = parse_buffer_header(data, verbs[1][0])
        i_count, i_bytes, i_stride, _, _ = parse_buffer_header(data, indb_off)
        if v1_bytes != v1_count * v1_stride or v2_bytes != v2_count * v2_stride:
            return False, "vertex buffer size/stride/count mismatch"
        if v1_count != v2_count:
            return False, (f"vertex buffer counts disagree: position stream has "
                           f"{v1_count}, attribute stream has {v2_count}")
        if i_count % 3 != 0:
            return False, f"index count {i_count} is not a multiple of 3"

        indices = struct.unpack_from(f'<{i_count}H', data, indb_off + 16)
        max_index = max(indices)
        if max_index >= v1_count:
            return False, (f"index {max_index} out of bounds for "
                           f"{v1_count}-vertex buffers")

        mesh_idx = struct.unpack_from('<I', data, mesh_off + MESH_INDEX_COUNT_OFFSET)[0]
        mesh_tri = struct.unpack_from('<I', data, mesh_off + MESH_TRI_COUNT_OFFSET)[0]
        mesh_vert = struct.unpack_from('<I', data, mesh_off + MESH_VERT_COUNT_OFFSET)[0]
        if (mesh_idx, mesh_tri, mesh_vert) != (i_count, i_count // 3, v1_count):
            return False, (f"Mesh chunk counts ({mesh_idx} idx, {mesh_tri} tri, "
                           f"{mesh_vert} vert) don't match buffers "
                           f"({i_count} idx, {i_count // 3} tri, {v1_count} vert)")

        return True, (f"{len(chunks)} chunks ok; {v1_count} verts in both streams, "
                      f"{i_count} indices (max {max_index}), Mesh counts match")
    except Exception as exc:
        return False, str(exc)


def read_mesh_triangles(path: Path) -> tuple[list[tuple[float, float]], list[tuple[int, int, int]]]:
    """Read a flat 2D triangle mesh back out of a vinyl .modelbin. This is the
    inverse of pack_verB/pack_indB. Returns (vertices_xy, triangles) in the
    same +-128 space build_modelbin works in (position stream is SNORM16,
    inverted here via `1/COORD_SCALE`). Used by tools/file_preview.py for a
    read-only mesh preview; raises ValueError on a malformed file, same as
    _parse_chunk_table.
    """
    data = path.read_bytes()
    chunks = _parse_chunk_table(data)
    verb_offsets = [off for tag, off, _size in chunks if tag == 'VerB']
    indb_off = next((off for tag, off, _size in chunks if tag == 'IndB'), None)
    if not verb_offsets or indb_off is None:
        raise ValueError("missing VerB/IndB chunks")

    # First VerB is always the position-only stream (stride 8: x:i16, y:i16,
    # z=0, w=0, see pack_verB); the second, if present, is the fuller
    # attribute stream this preview has no use for.
    v_count, _v_bytes, v_stride, _flags, _fmt = parse_buffer_header(data, verb_offsets[0])
    vertices = []
    for i in range(v_count):
        x_raw, y_raw = struct.unpack_from('<hh', data, verb_offsets[0] + 16 + i * v_stride)
        vertices.append((x_raw / COORD_SCALE, y_raw / COORD_SCALE))

    i_count, _i_bytes, i_stride, _flags, _fmt = parse_buffer_header(data, indb_off)
    indices = struct.unpack_from(f'<{i_count}H', data, indb_off + 16)
    triangles = [(indices[i], indices[i + 1], indices[i + 2]) for i in range(0, i_count, 3)]

    return vertices, triangles


def generate_glyph(char: str, font_path: Path, reference_modelbin: Path,
                   out_path: Path, curve_segments: int = 8, flip_winding: bool = True) -> Path:
    """Generate one glyph modelbin. Raises ValueError if the font lacks the
    glyph. Returns the output path."""
    if not glyph_in_font(char, font_path):
        raise ValueError(f"font {font_path.name} has no glyph for {char!r}")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    data = build_modelbin(char, font_path, reference_modelbin, curve_segments, flip_winding)
    out_path.write_bytes(data)
    return out_path


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--char', default='A', help='Character to generate (default: A)')
    ap.add_argument('--font-file', required=True, help='Path to a TTF/OTF font file (straight-line/stencil-style glyphs only)')
    ap.add_argument('--reference-modelbin', default=str(DEFAULT_REFERENCE_MODELBIN),
                     help=f'Path to a reference FH6 modelbin to copy material/mesh/layout chunks from '
                          f'(default: {DEFAULT_REFERENCE_MODELBIN}). Not included in this repo — see README.md.')
    ap.add_argument('--out', default=None, help='Output path (default: data/modelbin/CUSTOM_<CHAR>.modelbin)')
    ap.add_argument('--curve-segments', type=int, default=8,
                     help='Line segments per Bezier curve when flattening (default: 8; higher = smoother, more vertices)')
    ap.add_argument('--no-flip-winding', dest='flip_winding', action='store_false',
                     help="Don't reverse earcut's triangle winding to match the reference "
                          "(default: flip; earcut output is CCW, S_01's is majority CW)")
    args = ap.parse_args()

    char = args.char
    if len(char) != 1:
        print("--char must be a single character")
        sys.exit(1)

    if args.curve_segments < 1:
        print("--curve-segments must be at least 1")
        sys.exit(1)

    font_path = Path(args.font_file)
    if not font_path.exists():
        print(f"Font file not found: {font_path}")
        sys.exit(1)

    if not glyph_in_font(char, font_path):
        print(f"Font {font_path.name} has no glyph for {char!r}")
        sys.exit(1)

    reference_modelbin = Path(args.reference_modelbin)
    if not reference_modelbin.exists():
        print(f"Reference modelbin not found: {reference_modelbin}")
        print("This file is an extracted FH6 game asset and is not included in this repo.")
        print("See README.md for how to obtain your own copy.")
        sys.exit(1)

    out_path = Path(args.out) if args.out else Path("data/modelbin") / char_filename("CUSTOM", char)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"Generating modelbin for '{char}' from {font_path.name}...")
    data = build_modelbin(char, font_path, reference_modelbin, args.curve_segments, args.flip_winding)
    out_path.write_bytes(data)
    print(f"Wrote {len(data)} bytes -> {out_path}")


if __name__ == '__main__':
    main()
