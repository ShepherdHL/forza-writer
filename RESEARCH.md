# forza-writer — Reverse-Engineering Reference

This is the technical reference for how **forza-writer** talks to Forza
Horizon 6: the memory layout, the built-in shape catalog, the live SQLite
database backing that catalog, and the `.modelbin` mesh format vinyl shapes
are stored in. It consolidates three earlier working documents
(`forza-writer-briefing.md`, `forza-writer-cursor-briefing.md`,
`forza-writer-project-summary.md`) into one, in place of them.

Everything here concerns **offline/solo use only**. FH6-DBDUMPER and the
memory probe write to a live game process — never run this tooling while
connected to Xbox Live, and never on a shared/online session.

---

## What forza-writer does

FH6's livery editor stores each vinyl layer as a fixed **0x140-byte struct**
in process memory. One field in that struct is a `uint16` **shape word** — an
index into the game's shape catalog, which covers primitives (square,
circle...), effect shapes (stripes, flames, tribal...), and 11 built-in fonts
(uppercase + lowercase + symbols each). forza-writer generates and writes
shape words per character, so typed text renders as real native vinyl
layers — the same visual quality as the game's own font system — rather than
a decal or an image trace.

**Phase 1 — complete, verified in-game.** Generate JSON for any of the 11
built-in Forza fonts from the known shape catalog; import via KFPS.

**Phase 2 — active research.** Custom font support: not by registering
*new* catalog entries (confirmed not to work — see Phase 2 §4), but by
*hijacking* an existing catalog row to point at a custom mesh, so arbitrary
fonts render as real native layers too. Registration and mesh delivery are
both proven; the remaining blocker is a specific bug in how custom meshes
are generated (Phase 2 §6).

## Prior art / reference tools

| Tool | Repo | License | Relevant to |
|------|------|---------|-------------|
| forza-painter-fh6 (bvzrays) | github.com/bvzrays/forza-painter-fh6 | MIT | Memory probe/import scripts, game process profiles |
| forza-painter-fh6 v1.9.2 (bvzrays) | (archived ZIP) | MIT | Shape catalog CSV w/ `resource_path`, PIL-based glyph metrics |
| KFPS — Kloudy's Forza Painter Suite | github.com/heyitshestia/kloudys-forza-painter-suite | MIT | `editor.js` shape/layout math, `fh6_font_registry.json`, vertex JSON resources |
| FH6-DBDUMPER (matkhl) | github.com/matkhl/FH6-DBDUMPER | — | Live SQLite catalog dump + SQL injection |
| ForzaTech-extraction-tools (Doliman100) | github.com/Doliman100/ForzaTech-extraction-tools | — | `.modelbin` format documentation, Blender importer |
| ForzaTechStudio (D3FEKT) | github.com/D3FEKT/ForzaTechStudio | — | `.modelbin` GUI editor/viewer |
| ForzaModelTool (Das) | — | — | Confirms a `MediaOverride` loose-file mechanism exists in FH5 |

All shape data, layout math, and import logic that originates from KFPS is
MIT-licensed and attributed here and in `THIRD_PARTY_NOTICES.md`.

---

## Memory layout (confirmed)

```
CLiveryGroup layer struct size: 0x140 bytes per layer
Known livery signature:         b'\x12\x47\x9B\x13\x29\xD9\xA2\xB1'
Process names:                  ForzaHorizon6.exe, ForzaHorizon6-Win64-Shipping.exe

Pointer chain (from forza-painter-fh6's game_profiles.py):
  livery_root_pointer_offset = 0xB8
  editor_pointer_offset      = 0xA58
  livery_pointer_offset      = 0x8
  livery_group_offset        = 0x20
  livery_count_offset        = 0x5A
  layer_table_offset         = 0x78

Per-layer offsets:
  0x18  float[2]  Position (X, Y)       — memory_y = -trace_y
  0x28  float[2]  Scale (X, Y)
  0x50  float     Rotation
  0x58  uint32    Vertex/shape count    — FH6 recomputes this; do not write
  0x70  float     Skew
  0x74  byte[4]   Color (RGBA)
  0x78  bool      Mask flag
  0x7A  uint16    Shape word            — THE FONT CHARACTER SELECTOR
  0xA8  pointer   Resource pointer      — session-local; never write, never reuse across sessions
```

**Safe to write:** `0x18`, `0x28`, `0x50`, `0x70`, `0x74`, `0x78`, `0x7A`.
**Never write:** `0xA8` (crashes FH6 if invalid/stale), `0x58` (FH6-owned).

Memory probe scan regions (from live probing): `(0x06000000, 0x02000000)`,
`(0x08000000, 0x02000000)`, `(0x0A000000, 0x02000000)`.

Always save/reload the vinyl group after a memory write — FH6 resolves
shape IDs on reload, not immediately.

---

## The shape catalog system

### Type code formula

```python
typecode = 0x100000 + shape_word   # shape_word is the uint16 at offset 0x7A
```

### `VINYL_TYPE_BASES` (from KFPS `editor.js`)

```python
VINYL_TYPE_BASES = {
    "Primitives":          1048677,   # Square=1, Circle=2, Triangle=3...
    "Gradient_Shapes":     1048777,
    "Stripes":             1048877,
    "Tears":                1048977,
    "Racing_Icons":         1049077,
    "Flames":               1049177,
    "Paint_Splats":         1049277,
    "Tribal":               1049377,
    "Nature":               1049477,
    "Upper_Letters_2":      1049877,   "Lower_Letters_2":      1049977,
    "Upper_Letters_3":      1050077,   "Lower_Letters_3":      1050177,
    "Upper_Letters_4":      1050277,   "Lower_Letters_4":      1050377,
    "Upper_Letters_1":      1050477,   "Lower_Letters_1":      1050577,  # Font 1
    "Community_Vinyls_1":   1050677,   "Community_Vinyls_2":   1050777,
    "Community_Vinyls_3":   1050877,   "Community_Vinyls_4":   1050977,
    "Upper_Letters_5":      1051077,   "Lower_Letters_5":      1051177,
    "Upper_Letters_6":      1051277,   "Lower_Letters_6":      1051377,
    "Upper_Letters_7":      1051477,   "Lower_Letters_7":      1051577,
    "Upper_Letters_8":      1051677,   "Lower_Letters_8":      1051777,
    "Upper_Letters_9":      1051877,   "Lower_Letters_9":      1051977,
    "Upper_Letters_10":     1052077,   "Lower_Letters_10":     1052177,
    "Upper_Letters_11":     1052277,   "Lower_Letters_11":     1052377,
}

def resource_to_shape_word(family: str, index: int) -> int:
    if family == "Primitives":
        return (100 + index) & 0xFFFF
    base = VINYL_TYPE_BASES[family]
    return (base - 0x100000 + index - 1) & 0xFFFF   # index is 1-based (A=1, B=2...)

def resource_to_typecode(family: str, index: int) -> int:
    return 0x100000 + resource_to_shape_word(family, index)

# Example: Font 1 'A' = Upper_Letters_1 index 1 -> shape_word 1901 (0x076d), typecode 1050477
```

### Character → resource mapping (from KFPS `editor.js`)

```python
UPPER = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"   # indices 1-26 in Upper_Letters_N
LOWER = "abcdefghijklmnopqrstuvwxyz"   # indices 1-26 in Lower_Letters_N
SYMBOL_MAP = {                          # indices in Lower_Letters_N
    "%": 27, ":": 28, ";": 29, "/": 30, "$": 31,
    "£": 32, "¥": 33, "€": 34, "æ": 35, "Æ": 35,
    "^": 36, "ß": 37, "@": 38, "#": 39, "+": 40,
}

def char_to_resource(char: str, font: int = 1):
    """Returns (family, index) or None for unsupported characters
    (space, digits via this path, CJK, etc.)."""
    font = max(1, min(11, font))
    if (i := UPPER.find(char)) >= 0:
        return (f"Upper_Letters_{font}", i + 1)
    if (i := LOWER.find(char)) >= 0:
        return (f"Lower_Letters_{font}", i + 1)
    if char in SYMBOL_MAP:
        return (f"Lower_Letters_{font}", SYMBOL_MAP[char])
    return None
```

Digits (0-9) exist in `fh6_font_registry.json` (880 glyphs across all 11
fonts) but **not** in KFPS's own glyph-resource function above — they need
to be looked up from the registry JSON directly rather than via
`char_to_resource()`.

The confirmed catalog range (dumped directly from the live DB, see below) is
**IDs 101–3840, 1442 rows** — narrower and more precise than the
originally-inferred "~1301–3840, 11 fonts × ~200 glyphs" estimate.

---

## Text layout math (from KFPS `editor.js`'s `buildTextVinylForzaLetterShapes`, verified in-game)

```python
PIXEL_ART_SQUARE_SIZE = 128.498032   # FH6 mesh half-extent (coordinate space)

# Per text block:
line_height  = target_height / num_lines
glyph_height = line_height * 0.82
scale        = glyph_height / PIXEL_ART_SQUARE_SIZE
advance      = glyph_height * 0.72     # per-character advance
space_advance = advance * 0.58         # space width

# Per character:
x = cursor + char_advance / 2          # center of character
y = -y_trace                           # negated: memory_y = -trace_y
```

Unsupported characters (no `char_to_resource` match) still advance the
cursor at half-width (`advance * 0.5`) so surrounding text doesn't collapse
around them.

**Note:** forza-painter v1.9.2 uses a different coordinate model
(`POSITION_SCALE = 1.28`, `SIZE_SCALE = 0.01` in `pixel_art_geometry.py`) and
its `forza_fonts.py` uses PIL glyph metrics with an additional
`FORZA_GLYPH_SCALE = 2.55` for more accurate kerning. The KFPS pixel-space
model above is what forza-writer's Phase 1 actually uses, and it's verified
in-game.

---

## Vertex/mesh JSON format (KFPS `Resources/Vinyls/`)

Each shape has a resource file at `Resources/Vinyls/{family}/{index}`
(plus a `{index}.png` 220×220 preview thumbnail):

```json
{
  "Info": {"Type": 1050477, "TypeIndex": 1},
  "Vertices": [{"X": 110.27, "Y": -110.31}, ...],
  "Indices": [0, 1, 2, ...],
  "VerticesAlpha": "base64..."
}
```

- Coordinates range roughly ±128 (`PIXEL_ART_SQUARE_SIZE`).
- `VerticesAlpha` is base64-encoded per-vertex alpha; the first 12 vertices
  (indices 0-11) are always transparent — rounded-corner cutouts shared by
  every shape — and body vertices from index 12 onward are opaque.
- Complexity varies hugely: Square = 4 vertices / 6 indices. Letter 'A' = 23
  vertices. Symbol '%' = 185 vertices.

## JSON output format (`fh6_typecode_json_export_v1`)

This is what forza-writer's Phase 1 CLI (`python -m forza_writer "TEXT"
--font N --out out.json`) produces, and what KFPS / forza-painter's
handmade-JSON import consumes:

```json
{
  "format": "fh6_typecode_json_export_v1",
  "source": "forza-writer",
  "shapes": [
    {
      "type": 1050481,
      "type_word": 1905,
      "data": [x, y, sx, sy, 0.0, 0.0, 0],
      "color": [255, 255, 255, 255],
      "mask": false
    }
  ]
}
```

---

## `.modelbin` — the mesh format vinyl shapes are stored in

**Source:** Doliman100/ForzaTech-extraction-tools + D3FEKT/ForzaTechStudio,
cross-checked by directly extracting and parsing FH6's own `S_01.modelbin`
from `media\Livery\Vinyls.zip`.

A `.modelbin` is ForzaTech's binary 3D model container — a sequence of
tagged blob chunks, each with a 4-byte multicharacter tag:

```
Tag     Description
Skel    Skeleton (bone hierarchy)
Mrph    Morph targets
MatI    Material Info — Name, Id
Mesh    Geometry — Name, BBox
IndB    Index Buffer — Id
VLay    Vertex Layouts — Id, vertex format descriptor
VerB    Vertex Buffer — Id
Skin    Skinning data — Id
MBuf    Mesh buffer
Modl    Model root — BBox, TRef
```

Each entry carries a tag, properties (Name, Id, BBox, TRef), and a
4-byte-aligned data address.

**Vinyl modelbins are simpler than car models** — no skeleton, no morph, no
skinning. Confirmed (by parsing `S_01.modelbin` directly) to contain
`MatI` / `VLay` / `IndB` / `Modl`, plus **`VerB` twice** — this is the one
correction to the original extraction pass, only discovered once forza-writer
started *writing* these files instead of just reading them (see "The
malformed-mesh bug" below): one `VerB` is **position-only** (SNORM16 `(x, y)`
pairs, 8-byte stride, coordinates in the same ±128 space as everything else
here), the other carries the **full per-vertex attribute set** — position,
normal, tangent, texcoord, and vertex color. The KFPS vertex JSON format
above (`Vertices`/`Indices`/`VerticesAlpha`) is a simplified read of the
position-only buffer plus per-vertex alpha; it doesn't capture the second
buffer at all, which turned out to matter a great deal (below).

Outlines are straight-line polygons with holes where needed (e.g. letter
'A' has an outer contour plus a triangular counter/hole) — well suited to
earcut-style triangulation with hole support. **Triangle winding is
clockwise** (confirmed by signed-area comparison against `S_01.modelbin`,
majority clockwise there vs. `mapbox-earcut`'s uniformly counter-clockwise
output) — `tools/gen_modelbin.py` flips winding by default
(`--no-flip-winding` to disable); getting this backwards is a plausible
backface-culling explanation for an early round of invisible-glyph results.

**Encryption status:** FH5/FM2023 GameDB (`.slt`) is TransformIT-encrypted
(Arxan + CRC-32). FH6 vinyl modelbins, by contrast, were readable directly —
`S_01.modelbin` parsed cleanly with no decryption step, and KFPS's own
`Resources/Vinyls/` JSON extraction confirms this too.

### `tools/gen_modelbin.py` — generating a custom modelbin

1. **Glyph extraction** — pull a glyph's outline from a TTF/OTF via
   `fonttools`.
2. **Curve flattening** — Bézier curves become line segments via De
   Casteljau subdivision, handling both TrueType quadratic and CFF/OTF
   cubic curves; `--curve-segments` trades smoothness against vertex
   count. Straight-line stencil fonts skip this step entirely.
3. **Triangulation** (with hole support, e.g. the counter of an "A") via
   `mapbox-earcut`.
4. **Binary reassembly** — write a valid `.modelbin`, copying the
   material/vertex-layout chunks from a reference file (`S_01.modelbin`)
   and substituting the generated geometry.

Two fonts deliberately chosen as opposite stress cases: **Amarillo USAF**
(`amarurgt.ttf`) — all straight lines, no curve flattening needed, the
simplest case — and **Jokerman** — ornate, curve-heavy, multiple nested
contours per glyph, a real stress test for the flattening/triangulation
code (its "S" produces the densest mesh generated so far). Both produce
structurally valid output (round-tripped through the project's own
parser) — see "The malformed-mesh bug" below for why structurally valid
doesn't yet mean it renders.

One filesystem gotcha worth knowing before it costs you a debugging
session: Windows filesystems are case-insensitive, so `PREFIX_A.modelbin`
and `PREFIX_a.modelbin` collide on disk even though the shape catalog
treats upper/lower as distinct shape words — lowercase glyph files need an
explicit marker (`_lc`) to stay separate from their uppercase counterpart.

---

## Phase 1 — complete and verified

```
python -m forza_writer "EXPERIMENTAL" --font 1 --out out.json
```

Produces 12 shapes; imported via KFPS, renders as perfect native Forza Font
1 letterforms in-game at 12 layers. Output confirmed identical to KFPS's
own export for the same text.

---

## Phase 2 — custom font catalog registration (active research)

The goal: get a custom font's glyphs into FH6's shape catalog, so custom
text renders as real native vinyl layers rather than a decal/trace hack.
Phase 2 is really two problems stacked — get the game to *know about* a
new shape, and get it to *load a mesh* for that shape — and the story
below is the order things were actually learned, including a conclusion
that had to be walked back once better instrumentation existed. The short
version, if you read nothing else in this section: **the registration
path is proven — not by adding new catalog entries, which turned out not
to work, but by hijacking an existing catalog row — mesh delivery via
`Vinyls.zip` injection is proven, and the remaining blocker is a specific,
understood bug in this project's own mesh writer, not an unknown in the
game.** See "Current status" near the end for the
capability-by-capability breakdown.

### 1. FH6 enforces its shape catalog at save time

Early experiments wrote out-of-range shape words directly to offset `0x7A`:

- **`0xFFFF`:** accepted in memory, rendered as a mask layer.
- **`0x0F01` (3841, one past the last known Font 11 entry):** accepted in
  memory, briefly rendered something E-like — but on export after
  save/reload, the game had **silently normalized it back to `0x0771`**
  (Font 1 'E'). `resource_ptr_0xA8` confirmed both pointed at identical mesh
  data.

**Conclusion:** the catalog is enforced somewhere in FH6's asset system, not
just checked once at write time. Writing an unrecognized shape word to
`0x7A` alone is not sufficient for custom shapes — the catalog itself has
to be extended.

### 2. FH6-DBDUMPER and the live catalog table

Runtime memory probing (before DBDUMPER) found the `resource_ptr_0xA8`
field points to a render-pass object, not the catalog directly — at
`+0x10` a descriptor object, at `+0x18` mesh data, in a mesh pool with a
fixed **720-byte (0x2D0) stride** per shape, with descriptor objects
carrying a monotonically increasing *load-order* ID (not shape-word order)
at descriptor offset `0x038`. That path was abandoned once a more direct
route was found:

**FH6-DBDUMPER** (`github.com/matkhl/FH6-DBDUMPER`, C++, built locally) —
locates FH6's live in-memory SQLite database via an AOB (array-of-bytes)
pattern scan, then executes arbitrary SQL against it via
`CreateRemoteThread` injection:

```
CDatabase AOB pattern:
48 8B 0D ?? ?? ?? ?? 48 8B 01 4C 8D 45 ?? 48 8D 55 ?? FF 50 48 90 48 8B 4D ?? 48 85 C9
```

`execute_query` sits at vtable index 9 (offset `0x48`). Confirmed-working
SQL against a live FH6 process (from prior modding research, cited here as
context — not run as part of this project except the custom-SQL insert
below):

```sql
UPDATE Data_Car SET BaseCost = 0
UPDATE Data_Car SET NotAvailableInAutoshow = 0
INSERT INTO CarBuckets(CarId) SELECT Id FROM Data_Car ...
DROP VIEW IF EXISTS Drivable_Data_Car
CREATE VIEW Drivable_Data_Car AS SELECT * FROM Data_Car
CREATE TABLE _backup_AutoshowState AS SELECT ...
```

DBDUMPER also supports a **persist** mode: write a modified local `.sqlite`
file back into the live database (delete existing rows + insert from the
local file, table by table). It was extended this session with a
lightweight "execute custom SQL" option, since a full 214-table persist
took over 20 hours in an earlier attempt and had to be aborted — a single
`INSERT`/`UPDATE` via custom SQL takes seconds instead.

**The catalog table, confirmed:** dumping FH6's live database (214 tables
total) identified `Livery_VinylsDecals` as the shape catalog:

| Column | Meaning |
|---|---|
| `ID` | shape word — matches the values written to `0x7A` |
| `Path` | asset path, e.g. `GAME:\Media\Livery\Vinyls\S_01.modelbin` |
| `Category`, `Name`, `SortOrder` | UI metadata |

1,442 existing rows, IDs 101–3840.

### 3. The ID 4001 test, and a conclusion that had to be corrected

Inserted a new row directly into the **live** in-memory database via
DBDUMPER's custom-SQL option: `ID = 4001`, `Path =
GAME:\Media\Livery\Vinyls\S_01.modelbin` (reusing an existing mesh file as
a placeholder). Built a 2-layer test vinyl (layer 1 = shape word 4001,
layer 2 = known shape word 1901 as a baseline), imported via KFPS, saved
and reloaded in-game.

Reading `0x7A` back afterward (via forza-writer's own memory probe,
`forza_writer/probe.py`) confirmed:

- Layer 1: `type_word = 4001` — **survived, not normalized**.
- Layer 2: `type_word = 1901` — baseline correct, confirming the right
  group was read.

At the time this was read as "a catalog row is enough to anchor a custom
shape" — it felt like the breakthrough for Phase 2. **That was only a
partial read, and it's worth being honest about the correction**: what
survived was the *shape word in memory*. `resource_ptr_0xA8` for layer 1
came back `0x0` the entire time — a null resource pointer. FH6 accepted the
shape ID and found a catalog row, but never actually resolved a mesh for
it; the layer was registered but invisible. This didn't become clear until
much later, once better instrumentation (§8 below) made the null pointer
impossible to explain away. A partial success can look more complete than
it is — that's the general lesson, not just a footnote about this one test.

### 4. Why new rows don't actually work: the encrypted startup catalog

The natural next move was inserting many new rows at once — 62 of them (IDs
4002–4063), one per glyph of a test font. DBDUMPER's `INSERT` reported
`OK`, but a follow-up `SELECT COUNT(*)` for those exact IDs came back
**0**. The rows weren't there, despite the insert "succeeding."

A discriminating test settled whether this was DBDUMPER failing to commit
anything, or FH6 specifically rejecting *new* rows: instead of inserting, an
existing legitimate row (101) was `UPDATE`-ed and read back. It persisted.
**Writes do commit — FH6 specifically does not keep brand-new catalog rows
inserted at runtime.** New IDs never enter whatever set the renderer
actually resolves against.

The working theory, consistent with every observation so far: FH6's
authoritative shape catalog is built once at process startup from a
**packed, encrypted on-disk database, `gamedbRC.slt`** — not the live,
in-memory SQLite table DBDUMPER edits. The live table can be *read* and
individual existing rows can be *updated* (both changes are real and
persist), but it isn't the source the renderer consults for "does this ID
exist at all" — that check happens against something already resolved from
the encrypted database before DBDUMPER ever gets a chance to touch memory.
This reframes Phase 2 entirely: **don't add new rows — hijack existing
ones.**

### 5. The hijack: repointing an existing row, and how to tell it worked

Since `UPDATE`s to existing rows stick, an existing shape word FH6 already
knows about can be repointed at a custom mesh instead of registering a new
one. Tested by repointing shape word 1901 (normally a built-in Font 1 'A')
at a custom mesh file.

At first this looked like a failure — placed layers using shape word 1901
still showed the original built-in glyph. But those layers had their
meshes **cached** from before the edit; live-placed layers don't
necessarily re-resolve just because the catalog row changed underneath
them. The tell came from the **font-selection menu**, which renders its
thumbnails fresh on every open: after the hijack, that glyph's thumbnail
rendered **invisible** rather than as the original shape. An
invisible-but-changed thumbnail is a positive result, not a null one — it
means FH6 *did* read the new catalog path on a fresh resolve and *did* try
to load the new mesh. The remaining problem is narrower than "does hijacking
work" — it's "why does our mesh render nothing."

**This — hijacking an existing row, not inserting a new one — is the
confirmed, working registration path for Phase 2.**

### 6. The malformed-mesh bug: why hijacked custom meshes render nothing

Comparing a generated file against the reference pinned this down exactly.
The generator regenerates the position-only `VerB` and the `IndB` index
buffer from the glyph's actual geometry, but it **copies the full-attribute
`VerB` verbatim from the reference mesh** (see the two-`VerB` correction
above). So for a generated glyph with more vertices than the reference —
Jokerman's "A" needs up to 50, the reference mesh it was copied from only
has 23 — the index buffer references vertex indices past the end of the
attribute buffer the GPU actually renders from. The mesh is structurally
malformed and draws nothing, silently.

This is a fixable, purely offline code problem, not anything about the
game's behavior — regenerate the full-attribute buffer (correct vertex
count, flat viewer-facing normals, UVs, tangents, opaque vertex colors)
to match the newly-generated geometry instead of copying it from the
reference. It's the single most likely fix to turn an invisible hijacked
glyph into a visible one, and it's the current top priority (see "Next
steps" below).

### 7. Delivering the mesh: `Vinyls.zip`, not `MediaOverride`

All existing vinyl shapes live inside `media\Livery\Vinyls.zip`. There is
**no `MediaOverride` loose-file folder anywhere in this actual FH6
installation** — despite ForzaModelTool documenting that mechanism for FH5;
that FH5 precedent doesn't carry over here. A loose-file test (placing a
`.modelbin` next to the zip, updating the DB row's `Path` to point at it)
was tried and instrumentation (§8) later confirmed the game never touched
that file.

**Confirmed working instead: inject the custom mesh directly into
`Vinyls.zip`** (with a backup taken first). Diagnostics later caught FH6
reading `Vinyls.zip` during shape resolution, which both confirms the zip
is the real delivery channel and that injected files are reachable there.

### 8. Diagnostics tooling, and three separate resolution paths in FH6

Diagnosing this by hand from raw hex dumps, and via KFPS's memory scanner
(unreliable for small vinyl groups — too many candidate matches in memory),
kept producing ambiguous conclusions. `forza_writer/diagnostics/` is a
read-only, three-source event logger built to stop guessing:

- Polls FH6 process memory (`0x7A` / `0xA8` per layer) for changes, flagging
  values that change and then revert to baseline — the fingerprint of
  catalog normalization.
- Polls a SQLite database file for catalog changes, flagging an
  out-of-range ID that gets silently dropped.
- Watches a filesystem path for file creation/modification/read-access.

All three streams merge into one correlated, timestamped session log (JSON
+ human-readable Markdown summary), meant to be pasted directly into an AI
conversation for diagnosis:

```
python -m forza_writer.diagnostics --layers 3 --sqlite "<path to a live-updating db dump>" --fs-path "<MediaOverride or Vinyls folder>" --duration 120
```

**Operational note:** the memory watcher needs an **elevated
(Administrator) terminal** to open the game process — without it, it fails
silently and captures nothing. Easy to lose a session to.

This instrumentation is what surfaced the most important structural
finding about *how* FH6 resolves shapes: **live placement, thumbnail
generation, and the save/reload cycle are separate resolution paths, and
they don't agree.** After the hijack + winding-order fix below, a freshly
placed layer using the hijacked shape word rendered correctly — a real,
correctly-shaped letterform. Saving and reloading that *same session* (not
a restart, not session contamination — confirmed by isolating it to a
single fresh layer with nothing else touching that shape word first) made
it go blank again. Meanwhile the file-thumbnail preview rendered the same
hijacked shape correctly, in the same session, at the same time the loaded
vinyl itself was blank. Three resolution paths, at least, and only the
authoritative reload path currently rejects the injected mesh — which,
combined with §6, is now explained by the malformed attribute buffer rather
than being a separate mystery.

**One unresolved thread from this stretch of testing, deliberately not
overclaimed:** an early live retest (hijacking 1901 before the winding-order
fix below) produced two silent FH6 crashes. Windows Event Log showed
`LiveKernelEvent` id 1001, bugcheck `0x193` (`VIDEO_DXGKRNL_LIVEDUMP`) — a
GPU driver watchdog stall, not an application-level exception. An Nvidia
driver update was installed, and a subsequent diagnostics-instrumented run
completed cleanly with no crashes. That's a correlation, not a diagnosis —
the crash was never root-caused, and it's entirely possible the *actual*
trigger was the malformed pre-winding-fix mesh choking the driver rather
than anything the update itself fixed. Treat this as **unresolved and
worth re-investigating**, not closed: if a similar crash recurs during
future live testing (especially anything involving a mesh that hasn't been
validated yet), don't assume it's unrelated to the driver just because it
didn't recur once before.

### Current status

Precise about demonstrated-vs-assumed:

| Capability | Status |
|---|---|
| Built-in font text as native vinyl | **Works, verified in-game** (Phase 1) |
| Reading/writing the live shape catalog | **Works** (FH6-DBDUMPER) |
| Updating an existing catalog row so it takes effect on a fresh render | **Works** (the hijack — confirmed via the font-menu thumbnail) |
| Delivering custom meshes to the game | **Works** (injected into `Vinyls.zip`; game confirmed reading it) |
| Generating meshes from arbitrary fonts (geometry) | **Works** (TTF → flatten → triangulate; Amarillo + Jokerman sets structurally valid) |
| Generated meshes actually *rendering* | **Broken** — malformed full-attribute vertex buffer, glyphs render invisible (§6) |
| Adding brand-new catalog rows at runtime | **Doesn't hold** — new IDs don't persist into the render catalog (§4); points at the encrypted `gamedbRC.slt` |
| Custom glyph visible on a car | **Not yet achieved** |

The *registration* path for custom shapes is proven (hijacking existing
catalog entries). Mesh *delivery* is proven (`Vinyls.zip` injection). Mesh
*generation* produces geometrically correct but structurally broken files —
that's the immediate wall. New-row catalog insertion is a separate,
unsolved problem pointing at the encrypted startup database, not something
blocking the hijack approach.

Two ceilings worth keeping in mind independent of the remaining technical
work:

- **This is inherently local-only.** A hijacked shape word resolves to the
  *other player's* unmodified mesh on their machine, and a genuinely new
  shape word wouldn't resolve for them at all even if that path worked.
  Custom fonts are a single-player / local-cosmetic capability unless every
  viewer has identical modified files — not a distributable situation.
- **Modifying `Vinyls.zip` is a modified game file.** For online play that
  carries real, non-zero anti-cheat risk — restore the backup
  (`Vinyls.zip.bak`) before going online. Runtime database edits (the
  hijack itself) are session-only and clear on restart, so those alone
  don't carry the same risk; the persistent zip modification is the part
  that does.

### Next steps for Phase 2, in priority order

1. **Fix mesh generation** — regenerate the full-attribute vertex buffer
   (correct vertex count, normals, UVs, tangents, vertex colors) to match
   the generated geometry instead of copying it from the reference (§6).
   Entirely offline, and the single most likely fix to produce a visible
   custom glyph. Highest priority.
2. **Re-run the hijack test with a fixed mesh** — repoint an existing shape
   word at the corrected custom glyph and confirm it renders on a fresh
   resolve (freshly placed layer or menu thumbnail). This is the milestone
   that proves the whole local pipeline end-to-end.
3. **If still invisible, check winding/culling again** on the new mesh
   specifically — the fix in the modelbin section above was validated on
   the original test case, not re-verified against every subsequent
   geometry variant.
4. **Map the hijack approach into a real feature** — decide which existing
   shape words are expendable to repurpose, and how typed text maps onto
   them, so "type a word in a custom font" can drive catalog updates
   automatically.
5. **Longer term: the new-catalog-row problem** — genuinely adding shapes
   (rather than hijacking existing ones) means getting entries into
   `gamedbRC.slt` or finding an in-memory catalog structure the encrypted
   database resolves into at startup. Separate research effort; only worth
   attempting if the hijack approach proves too limiting in practice.

---

## Key numbers

- Layer budget: 3000 (sides/roof), 1000 (other panels)
- Font glyph mesh stride: 720 bytes (0x2D0) in the runtime mesh pool
- `PIXEL_ART_SQUARE_SIZE`: 128.498032
- Confirmed catalog range: IDs 101–3840, 1442 rows (`Livery_VinylsDecals`)
- Full font registry: 880 documented glyphs across 11 built-in fonts
- Memory probe scan regions: `(0x06000000, 0x02000000)`,
  `(0x08000000, 0x02000000)`, `(0x0A000000, 0x02000000)`
- The renderer's *authoritative* catalog is resolved at process startup
  from the packed, encrypted `gamedbRC.slt` — the live `Livery_VinylsDecals`
  SQLite table is readable/updatable at runtime, but new rows inserted into
  it never enter what the renderer actually checks against (Phase 2 §4).

## Safety constraints (always in effect)

- Run FH6-DBDUMPER, the memory probe, and the diagnostics tooling **only
  while offline** — disconnect from Xbox Live before launching FH6. This
  tooling modifies live game memory; online use risks detection and account
  action.
- Never write to memory offset `0xA8` (volatile resource pointer — crashes
  FH6 if invalid) or `0x58` (vertex/shape count — FH6-recomputed).
- The resource pointer at `0xA8` is session-local; never reuse one captured
  from an old session/dump.
- Always save/reload the vinyl group after any memory write.
- The diagnostics memory watcher needs an **elevated (Administrator)
  terminal** to open the game process — it fails silently, capturing
  nothing, if the terminal isn't elevated.
- A modified `Vinyls.zip` (the mesh-delivery mechanism, Phase 2 §7) is a
  modified game file — restore `Vinyls.zip.bak` before playing online. See
  Phase 2's "two ceilings" for the full local-only/anti-cheat picture.
- An early live test produced a GPU driver watchdog crash (bugcheck
  `0x193`) that was only correlated with a driver update, never actually
  root-caused (Phase 2 §8) — don't assume a recurrence during live testing
  is unrelated just because it didn't happen again once.

## Key external references

- forza-painter-fh6: https://github.com/bvzrays/forza-painter-fh6
- KFPS: https://github.com/heyitshestia/kloudys-forza-painter-suite
- FH6-DBDUMPER: https://github.com/matkhl/FH6-DBDUMPER
- Modelbin format / extraction tools: https://github.com/Doliman100/ForzaTech-extraction-tools
- Modelbin decryption tool (FH5/FM2023): https://github.com/Doliman100/ForzaTech-encryption-tool
- Modelbin GUI editor/viewer: https://github.com/D3FEKT/ForzaTechStudio (credits Nenkai's ForzaTools library and Doliman100 for format research)
