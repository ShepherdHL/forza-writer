# ML-Guided Generation Plan

Forza Writer has three generation methods. This plan covers where ML fits
across all three, then goes deep on the one worth building first.

**Status: experimental / not implemented.** Everything below is a design
sketch, not committed work. Whenever any part of this ships, it must be an
explicit "Experimental" toggle the user switches on/off before generation,
defaulting off, never a silent change to the existing deterministic
generators' behavior.

| Method | Implementation | ML fit |
|---|---|---|
| MODELBIN Translation | `.modelbin` mesh translation (RESEARCH.md Phase 2) | **Out of scope.** Deterministic outline→mesh repackaging (an SVG-equivalent in a proprietary container) with no approximation step to improve — nothing for a model to learn. |
| Shape Fitting (`.json`) | `forza_writer/primitive_fit.py` (`fit_silhouette`/`fit_placements`) | **Primary target.** Full primitive-shape library + masks, and an explicit greedy search loop already tuned for exactly the kind of learned proposal this plan adds. |
| Pixel Tracing (`.json`) | `forza_writer/legacy_primitive_fit.py` (`_decompose_mask_to_rectangles`) | **Secondary/exploratory.** Different problem shape (see its own section below) — smaller, less certain win, worth scoping separately rather than building first. |

## Part 1 — Shape Fitting (`.json`): primary target

### Problem

`fit_silhouette` picks each layer by exhaustively scanning every allowed
primitive shape across a fixed grid of `SCALES × ASPECTS × ROTATIONS ×
POSITION_GRID`, scoring each with `candidate_gain`, then locally hill-climbing
the winner (`refine_candidate`). Cost scales with catalog size × grid density
per layer, and the grid is the same shape regardless of what the residual
actually looks like. Complex/high-stroke-count glyphs (CJK, Devanagari
conjuncts, Arabic ligatures) need the most layers and are exactly where a
fixed candidate grid is most likely to waste search on the wrong region and
hit `max_layers`/`quality_target` shortfalls (see `fit_placements`' fallback
ladder, which exists because this already happens).

### Goal

Add a learned proposal step that looks at the current residual mask and
predicts promising `(shape_id, cx, cy, scale_x, scale_y, rotation, skew_x)`
candidates directly, cutting `candidates_tested` while matching or beating
today's achieved IoU/shape-count — with the biggest expected win on
non-Latin/complex scripts, where the fixed grid is weakest.

### Non-goals

- **Not** training on other users' hand-drawn Fabric Editor glyphs. That data
  is small, stylistically inconsistent, and answers a different question
  (freehand drawing) than what this generator does (font outline → primitive
  decomposition).
- **Not** touching the `.modelbin` mesh-hijack path in this plan.
- **Not** replacing exact scoring. `candidate_gain` and `refine_candidate`
  keep arbitrating and polishing every candidate, model-proposed or not — the
  model only proposes *where to look*, so output quality can never fall below
  today's grid-search floor.

### Data (fully synthetic — no user data involved)

1. Source glyphs: a broad multi-font, multi-script corpus (existing
   `assets/fonts` plus a Google Fonts pull covering Latin, Cyrillic, CJK,
   Devanagari, Arabic, etc.).
2. For each `(font, glyph)`: rasterize the target mask with the existing
   `rasterize_contours`, then run the current search (or a slower/better
   offline search — beam search or simulated annealing, no runtime cost since
   this is a one-time data generation pass) to produce a labeled trajectory:
   at each step, `(residual_mask_state) -> (PlacedShape actually accepted)`.
3. Every step of every accepted trajectory becomes one training example.
4. The corpus is large and regenerable — commit only the generation script
   and a manifest, never the corpus itself, mirroring how `gen_fontpack.py`
   already treats font-derived output as regenerable rather than checked in.

### Model

- Small CNN over the residual mask at `DEFAULT_RESOLUTION` (64×64) — one
  classification head over `PRIMITIVE_CATALOG` shape IDs (~17-way) plus
  regression heads for `cx, cy, scale_x, scale_y, rotation_deg, skew_x`,
  trained multi-task.
- Small enough for CPU inference with no CUDA dependency, so it doesn't
  regress the CPU-only fallback path that `docs/RUST_CPU_ACCELERATION.md`
  is also protecting. Export via ONNX/TorchScript, load once per process.

### Integration into `fit_silhouette`

- Add the model's top-K proposals as an *additional* candidate source
  alongside the existing per-shape grid scan — not a replacement, at least
  initially. Proposals get rendered and scored through the exact same
  `candidate_gain` → `per_shape` → `refine_candidate` pipeline every grid
  candidate already goes through.
- Failure mode is a no-op: if the model proposes nothing useful, the grid
  candidates still cover the search exactly as they do today. Purely
  additive, not a rewrite.
- Gate behind an explicit option, e.g. `candidate_source: "grid" |
  "grid+model"`, analogous to the existing `compute_backend: "cpu"|"cuda"`
  switch — so it's A/B-comparable and can be disabled instantly.

### Gates (same discipline as `docs/RUST_CPU_ACCELERATION.md`)

1. Build the synthetic corpus + offline trajectory generator; check in the
   script, not the data.
2. Train a first model on Latin only. Verify no regression on the benchmark
   glyphs already referenced in `primitive_fit.py`'s own docstrings (e.g.
   Amarillo USAF's E/O, Jokerman's multi-contour K, Minecraft Standard
   Galactic Alphabet's X/Z).
3. Extend the corpus to non-Latin scripts; re-measure specifically on
   CJK/Devanagari-heavy fonts where layer budgets are tightest today.
4. Require both a material drop in `candidates_tested` *and* IoU/shape-count
   at parity or better, measured end-to-end through `fit_placements` (not a
   microbenchmark on the model alone).
5. Ship as an opt-in, fallback-safe candidate source before ever making it
   the default.

### Open questions

- Does a change to `PRIMITIVE_CATALOG` (new shapes added later) force
  retraining the classification head, or should the model be designed
  catalog-agnostic (e.g. score shape *embeddings* rather than a fixed class
  list) from the start?
- `GenerationPolicy` already restricts which shapes are usable per run
  (`policy.shapes()`) — does the model need to condition on the active
  policy's allowed set, or is it acceptable to over-propose and let
  `per_shape`/policy filtering discard disallowed proposals for free?

## Part 2 — Pixel Tracing (`.json`): secondary/exploratory

### Why this is a different problem, not a smaller version of Part 1

`legacy_primitive_fit.py` doesn't search over a shape catalog at all — it
rasterizes the glyph with PIL, buckets pixels into a `cell_size` grid at a
fixed fill threshold (`_FILL_THRESHOLD_FRACTION`), then greedily merges
filled cells into maximal axis-aligned rectangles
(`_decompose_mask_to_rectangles`, a row-scan-and-grow-height merge, always
Squares). There's no per-candidate scoring loop to plug a proposal network
into the way `fit_silhouette` has — Part 1's design doesn't transfer
directly.

Two distinct angles, not one:

1. **Rectangle-count minimization.** The row-scan-and-grow merge is a greedy
   heuristic for what's a well-studied combinatorial problem (minimum
   rectangle partition of an orthogonal region). `forza_writer/
   rect_decompose.py`'s largest-rectangle approach (already used inside
   `primitive_fit.py`'s rectilinear routing) is a better-motivated classical
   algorithm than the legacy greedy merge — worth comparing against that
   *before* reaching for ML, since a non-learned exact/near-optimal method
   may already close most of the gap for free.
2. **Per-glyph raster parameter selection.** `font_size`/`cell_size`/fill
   threshold are fixed constants today regardless of script or glyph
   complexity. A dense CJK glyph and a simple Latin dot want different
   settings to stay both recognizable and layer-cheap. This is a much
   smaller learning problem than Part 1's proposal network — closer to a
   regression model predicting good raster parameters per glyph than a
   search-guidance model — and could reuse Part 1's synthetic multi-script
   corpus if that gets built first.

### Recommendation

Don't start here. Land Part 1 first — it validates the synthetic-corpus
pipeline and the "model proposes, exact code verifies" pattern this would
also need. Revisit angle 2 above only if the classical `rect_decompose.py`
comparison in angle 1 still leaves a real quality/layer-count gap on
non-Latin scripts that a fixed raster threshold can't close.

## Part 3 — MODELBIN Translation: out of scope

Confirmed out of scope per the method's own nature, not just this plan's
choice: it translates a font's outline directly into the `.modelbin` mesh
container FH6 reads — functionally an SVG re-packaged into a proprietary
format, with no lossy approximation step in the middle. There's nothing for
a model to *learn to do better*, since the translation is already exact.
Only relevant to this plan as a possible future reuse of its synthetic
multi-font/multi-script corpus, if some other mesh-generation problem shows
up in Phase 2 work — not assumed or scoped here.
