"""Approximate a glyph's silhouette by greedily composing FH6's built-in
"Primitives" shape catalog (`forza_writer.primitive_shapes`), not a fixed
pixel grid. Output is a list of shape dicts in exactly the format
`forza_writer.layout` already produces, so `forza_writer.export.to_json()`
works unmodified and the result needs no catalog hijack: every shape it uses
already exists in FH6 today.

Algorithm: rasterize the target glyph to a boolean silhouette mask, then
repeatedly search over (shape x position x scale x rotation) for the
candidate placement that most reduces the still-uncovered "residual" area
without spilling much ink outside the glyph, accept it, subtract its
coverage from the residual, and repeat until a layer budget or quality
target is hit. This is a from-scratch greedy hill-climb (the same family of
algorithm as tools like "Primitive"/geometrize use), not ported from any
third-party codebase.
"""

from __future__ import annotations

import math
import sys
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal

import numpy as np
from PIL import Image

from forza_writer.generation_policy import (
    DEFAULT_MAX_LAYERS,
    DEFAULT_MIN_GAIN,
    DEFAULT_OVERSHOOT_PENALTY,
    DEFAULT_POLICY,
    DEFAULT_QUALITY_TARGET,
    GenerationPolicy,
    GenerationStats,
)
from forza_writer.primitive_shapes import PRIMITIVE_CATALOG, PrimitiveShape

# Optional Rust CPU kernel (rust/primitive_fit_rs) for the candidate
# scoring/mask-coverage comparison in this module's CPU search loop -- see
# docs/RUST_CPU_ACCELERATION.md. Purely an accelerator for the "cpu"
# compute_backend path below: it never touches the CUDA path
# (forza_writer.compute_backend), and every call site here keeps the pure
# -Python implementation as a correctness fallback when the extension isn't
# built/installed, so a missing wheel degrades to "a bit slower", not a
# crash.
try:
    from primitive_fit_rs import primitive_fit_rs as _rust_kernel
except ImportError:
    _rust_kernel = None


def rust_kernel_available() -> bool:
    """Whether the optional Rust CPU kernel is importable. Exposed so a
    caller (e.g. the GUI's diagnostics) can surface fallback status instead
    of the acceleration being silently absent."""
    return _rust_kernel is not None


# "auto": pick whichever of direct-fill/stencil needs fewer shapes (today's
# behavior). "force": use a mask-cutout stencil whenever one is achievable at
# all, even if it needs more shapes than direct fill. "never": never
# consider a stencil, always direct-fill.
MaskMode = Literal["auto", "force", "never"]

# extract_contours/normalize_to_128 live in tools/gen_modelbin.py (a script,
# not a package) rather than in forza_writer, so the glyph geometry pipeline
# has exactly one implementation shared by both the .modelbin and primitive
# -fit paths. Same sys.path bridge tools/gen_modelbin_gui.py and
# tools/gen_fontpack.py already use.
_TOOLS_DIR = str(Path(__file__).resolve().parent.parent / "tools")
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

COORD_RANGE = 100.0  # glyph coordinate space is roughly [-100, 100], per normalize_to_128

DEFAULT_RESOLUTION = 64
# DEFAULT_MAX_LAYERS / DEFAULT_QUALITY_TARGET / DEFAULT_MIN_GAIN and the
# overshoot penalty now live on GenerationPolicy (imported above) so the
# policy and this module can't drift apart; the historical name is kept as an
# alias because callers and tests already import it from here.
OVERSHOOT_PENALTY = DEFAULT_OVERSHOOT_PENALTY

SCALES = (0.35, 0.55, 0.8, 1.05)
ASPECTS = (1.0, 1.4, 1 / 1.4)  # scale_x = scale*aspect, scale_y = scale/aspect: lets rings/rects stretch to match non-circular strokes
ROTATIONS_ASYMMETRIC = (0.0, 60.0, 120.0)
ROTATIONS_SYMMETRIC = (0.0,)
POSITION_GRID = 3  # samples per axis over the residual's bounding box
MAX_ABS_SKEW = 0.8  # stored FH6 shear slope (not degrees); ~= 38.7 degrees


@dataclass(frozen=True)
class PlacedShape:
    shape_id: str
    cx: float  # glyph-space x, [-100, 100]
    cy: float  # glyph-space y, [-100, 100]
    scale_x: float
    scale_y: float
    rotation_deg: float
    skew_x: float = 0.0  # FH6 data[5]: horizontal shear slope, tan(angle)
    is_mask: bool = False  # stencil-mode cutout: punches transparency through layers below it


def rasterize_contours(contours: list[list[tuple[float, float]]], resolution: int = DEFAULT_RESOLUTION) -> np.ndarray:
    """Rasterize normalized glyph contours (±COORD_RANGE space, as produced
    by `gen_modelbin.normalize_to_128`) to a boolean fill mask, using the
    standard even-odd fill rule: XOR together each contour's own
    independently-rasterized solid fill. A pixel ends up filled if an odd
    number of contours cover it: a nested hole is covered by both its
    enclosing contour and itself (even, cancels to unfilled), a disjoint
    component is covered by only itself (odd, stays filled), and this falls
    out correctly for arbitrary nesting depth with no separate
    depth/parent bookkeeping needed.

    This must not assume contour 0 is always the outer boundary with every
    other contour a hole cut from it: fontTools' `RecordingPen` does not
    guarantee the largest/outer contour comes first, and decorative
    multi-part glyphs break that assumption outright (e.g. Jokerman's 'K'
    is 5 disjoint contours, the main stroke plus 4 separate sparkle
    accents, with a sparkle first; treating that first contour as the
    whole glyph would subtract the real letterform from it as a "hole").
    `tools/gen_modelbin.py`'s earcut mesh triangulation has the same
    requirement, handled there via `group_contours_by_nesting` (a proper
    containment tree, since earcut's outer-ring-plus-holes API needs one
    earcut() call per disjoint island rather than a single fill mask).
    """
    from PIL import ImageDraw

    def to_px(pt: tuple[float, float]) -> tuple[float, float]:
        x, y = pt
        px = (x + COORD_RANGE) / (2 * COORD_RANGE) * resolution
        py = (COORD_RANGE - y) / (2 * COORD_RANGE) * resolution
        return (px, py)

    polys = [[to_px(p) for p in contour] for contour in contours]
    polys = [pts for pts in polys if len(pts) >= 3]
    if not polys:
        return np.zeros((resolution, resolution), dtype=bool)

    result = np.zeros((resolution, resolution), dtype=bool)
    for pts in polys:
        img = Image.new("L", (resolution, resolution), 0)
        ImageDraw.Draw(img).polygon(pts, fill=255)
        result ^= np.array(img, dtype=bool)
    return result


def _resize_mask(mask: np.ndarray, size: tuple[int, int]) -> np.ndarray:
    if size[0] <= 0 or size[1] <= 0:
        return np.zeros((max(size[1], 0), max(size[0], 0)), dtype=bool)
    img = Image.fromarray((mask * 255).astype(np.uint8))
    img = img.resize(size, Image.NEAREST)
    return np.array(img, dtype=bool)


def _candidate_image(shape: PrimitiveShape, scale_x: float, scale_y: float,
                     rotation_deg: float, canvas_res: int,
                     skew_x: float = 0.0) -> np.ndarray:
    """Create the cropped transformed image used by both CPU placement and
    CUDA's template cache. Keeping this exact Pillow path shared makes CUDA
    candidate scores pixel-identical to CPU candidate masks."""
    w = max(1, round(canvas_res * scale_x))
    h = max(1, round(canvas_res * scale_y))
    img = _resize_mask(shape.mask, (w, h))
    if skew_x:
        # FH6/KFPS stores data[5] as the horizontal shear slope rather than
        # degrees. Apply the same centered x' = x + skew_x*y transform here
        # so fitting, preview, QA, and exported JSON all agree.
        pil = Image.fromarray((img * 255).astype(np.uint8))
        extra = math.ceil(abs(skew_x) * h)
        out_w = w + extra
        pad = (out_w - w) / 2.0
        inverse = (1.0, -skew_x, skew_x * h / 2.0 - pad, 0.0, 1.0, 0.0)
        pil = pil.transform(
            (out_w, h), Image.Transform.AFFINE, inverse,
            resample=Image.Resampling.NEAREST, fillcolor=0)
        img = np.array(pil, dtype=bool)
    if rotation_deg and not shape.rotationally_symmetric:
        pil = Image.fromarray((img * 255).astype(np.uint8))
        pil = pil.rotate(rotation_deg, expand=True, resample=Image.NEAREST, fillcolor=0)
        img = np.array(pil, dtype=bool)
    return img


def render_candidate(shape: PrimitiveShape, cx_px: float, cy_px: float,
                      scale_x: float, scale_y: float, rotation_deg: float,
                      canvas_res: int, skew_x: float = 0.0) -> np.ndarray:
    """Render one candidate placement onto a `canvas_res` x `canvas_res`
    boolean canvas. `scale_x`/`scale_y` are fractions of the canvas size."""
    img = _candidate_image(shape, scale_x, scale_y, rotation_deg, canvas_res, skew_x)
    canvas = np.zeros((canvas_res, canvas_res), dtype=bool)
    ph, pw = img.shape
    px = round(cx_px - pw / 2)
    py = round(cy_px - ph / 2)
    src_x0, src_y0 = max(0, -px), max(0, -py)
    dst_x0, dst_y0 = max(0, px), max(0, py)
    dst_x1 = min(canvas_res, px + pw)
    dst_y1 = min(canvas_res, py + ph)
    if dst_x1 <= dst_x0 or dst_y1 <= dst_y0:
        return canvas
    src_x1 = src_x0 + (dst_x1 - dst_x0)
    src_y1 = src_y0 + (dst_y1 - dst_y0)
    canvas[dst_y0:dst_y1, dst_x0:dst_x1] = img[src_y0:src_y1, src_x0:src_x1]
    return canvas


def _residual_bbox(residual: np.ndarray) -> tuple[int, int, int, int] | None:
    ys, xs = np.nonzero(residual)
    if len(xs) == 0:
        return None
    return int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())


def _sample_positions(bbox: tuple[int, int, int, int], grid: int) -> list[tuple[float, float]]:
    x0, y0, x1, y1 = bbox
    xs = [x0] if x1 == x0 else [x0 + (x1 - x0) * i / (grid - 1) for i in range(grid)]
    ys = [y0] if y1 == y0 else [y0 + (y1 - y0) * i / (grid - 1) for i in range(grid)]
    return [(x, y) for x in xs for y in ys]


def candidate_gain(candidate_mask: np.ndarray, residual: np.ndarray, target_mask: np.ndarray,
                    overshoot_penalty: float = OVERSHOOT_PENALTY) -> float:
    """Score a candidate placement: reward newly-covered still-uncovered ink,
    penalize ink that lands outside the target silhouette entirely. The
    overshoot penalty must outweigh the coverage reward meaningfully or the
    greedy search degenerates to one oversized shape covering everything."""
    new_coverage = int(np.count_nonzero(candidate_mask & residual))
    overshoot = int(np.count_nonzero(candidate_mask & ~target_mask))
    return new_coverage - overshoot_penalty * overshoot


def refine_candidate(best: PlacedShape, residual: np.ndarray, target_mask: np.ndarray,
                      resolution: int, overshoot_penalty: float = OVERSHOOT_PENALTY,
                      rounds: int = 3) -> tuple[PlacedShape, np.ndarray, float]:
    """Locally hill-climb a coarse winner's position, scale, and x-skew.

    The coarse search samples a small discrete ladder of scales/aspects, so
    the shape it picks is rarely the best *version* of that shape: it's the
    best one that happened to be on the grid. This nudges each parameter
    independently with shrinking steps, which recovers most of the benefit of
    a continuous aspect/skew search (arbitrary sx/sy plus bounded FH6 shear,
    as both hand-made vinyl packs and forza-painter-fh6 use) at a fraction of the cost:
    a few dozen extra renders per accepted shape rather than multiplying the
    whole candidate grid.
    """
    shape = PRIMITIVE_CATALOG[best.shape_id]
    current = best
    current_mask = render_candidate(shape, current.cx, current.cy, current.scale_x,
                                     current.scale_y, current.rotation_deg, resolution,
                                     current.skew_x)
    current_gain = candidate_gain(current_mask, residual, target_mask, overshoot_penalty)

    pos_step = max(1.0, resolution * 0.06)
    scale_step = 0.12
    skew_step = 0.24
    # Keep shrinking the step until it's finer than a single pixel of scale.
    # Stopping early leaves the shape a pixel or two off the ideal size, and
    # that leftover sliver is big enough to pull in a whole extra layer it
    # doesn't deserve.
    min_scale_step = 0.5 / resolution
    while scale_step >= min_scale_step:
        improved = False
        for dx, dy, dsx, dsy, dskew in (
            (pos_step, 0, 0, 0, 0), (-pos_step, 0, 0, 0, 0),
            (0, pos_step, 0, 0, 0), (0, -pos_step, 0, 0, 0),
            (0, 0, scale_step, 0, 0), (0, 0, -scale_step, 0, 0),
            (0, 0, 0, scale_step, 0), (0, 0, 0, -scale_step, 0),
            (0, 0, 0, 0, skew_step), (0, 0, 0, 0, -skew_step),
        ):
            trial_sx = current.scale_x + dsx
            trial_sy = current.scale_y + dsy
            if trial_sx < 0.03 or trial_sy < 0.03 or trial_sx > 2.5 or trial_sy > 2.5:
                continue
            trial_skew = current.skew_x + dskew
            if abs(trial_skew) > MAX_ABS_SKEW:
                continue
            trial = PlacedShape(
                current.shape_id, current.cx + dx, current.cy + dy,
                trial_sx, trial_sy, current.rotation_deg,
                skew_x=trial_skew, is_mask=current.is_mask)
            if _rust_kernel is not None:
                # Score-only: skip materializing trial_mask (the expensive
                # Pillow resize/rotate/skew path) for every trial. Only the
                # trial that actually wins needs a real mask, rendered below.
                trial_gain = _rust_kernel.score_candidate(
                    shape.mask.view(np.uint8), shape.rotationally_symmetric,
                    trial.scale_x, trial.scale_y, trial.rotation_deg, trial.skew_x,
                    trial.cx, trial.cy, resolution,
                    residual.view(np.uint8), target_mask.view(np.uint8), overshoot_penalty)
                if trial_gain > current_gain:
                    trial_mask = render_candidate(shape, trial.cx, trial.cy, trial.scale_x,
                                                   trial.scale_y, trial.rotation_deg, resolution,
                                                   trial.skew_x)
                    current, current_mask, current_gain = trial, trial_mask, trial_gain
                    improved = True
            else:
                trial_mask = render_candidate(shape, trial.cx, trial.cy, trial.scale_x,
                                               trial.scale_y, trial.rotation_deg, resolution,
                                               trial.skew_x)
                trial_gain = candidate_gain(trial_mask, residual, target_mask, overshoot_penalty)
                if trial_gain > current_gain:
                    current, current_mask, current_gain = trial, trial_mask, trial_gain
                    improved = True
        if not improved:
            pos_step = max(0.5, pos_step / 2.0)
            scale_step /= 2.0
            skew_step /= 2.0
    return current, current_mask, current_gain


def fit_silhouette(target_mask: np.ndarray, resolution: int = DEFAULT_RESOLUTION,
                    max_layers: int | None = None,
                    quality_target: float | None = None,
                    min_gain: int | None = None,
                    overshoot_penalty: float | None = None,
                    refine: bool = True, compute_backend: str = "cpu",
                    policy: GenerationPolicy | None = None,
                    stats: GenerationStats | None = None) -> list[PlacedShape]:
    """Greedily cover `target_mask` (boolean, `resolution`x`resolution`)
    with primitive placements. Returns placements in pixel space; callers
    convert to glyph-space via `_px_to_glyph`.

    `policy` restricts which primitives may be used and biases scoring toward
    preferred ones (see `forza_writer.generation_policy`). Disallowed shapes
    are never turned into candidates in the first place, so a narrow policy
    searches proportionally less rather than generating work it then throws
    away.

    The four tuning arguments default to None meaning "take it from the
    policy". An explicit value still wins, which keeps every existing caller
    that passes them positionally behaving exactly as before.
    """
    policy = policy or DEFAULT_POLICY
    max_layers = policy.max_layers if max_layers is None else max_layers
    quality_target = policy.quality_target if quality_target is None else quality_target
    min_gain = policy.min_gain if min_gain is None else min_gain
    overshoot_penalty = (policy.overshoot_penalty if overshoot_penalty is None
                         else overshoot_penalty)

    target_area = int(target_mask.sum())
    if target_area == 0:
        return []

    # Materialized once rather than per layer: this is the "allowed" stage of
    # the pipeline, and it cannot change mid-fit.
    usable_shapes = list(policy.shapes())
    if not usable_shapes:
        return []

    residual = target_mask.copy()
    covered = np.zeros_like(target_mask)
    placed: list[PlacedShape] = []

    for _ in range(max_layers):
        bbox = _residual_bbox(residual)
        if bbox is None:
            break
        positions = _sample_positions(bbox, POSITION_GRID)

        # Best coarse candidate *per shape type*, all of which then get
        # refined before a winner is chosen.
        #
        # Picking the winner from coarse scores alone is a real bug, not a
        # micro-optimization: the ladder's discrete scales rarely match the
        # target exactly, which systematically favours shapes that *under*-
        # fill their bounding box (circle, hexagon, pentagon) over ones that
        # fill it (square), because the under-fillers overshoot less at a
        # too-large scale. On an exact square target, square ranks 11th of 17
        # coarse, yet it is the only shape that refines to a perfect fit
        # (1024 vs rounded_square's 929). Refining a truncated top-N wouldn't
        # rescue it either; the coarse ranking has to be treated as nothing
        # more than a per-shape starting point.
        per_shape: dict[str, tuple[float, PlacedShape, np.ndarray]] = {}

        if compute_backend in ("cuda", "directml"):
            if compute_backend == "cuda":
                from forza_writer.compute_backend import cuda_scorer
                scorer = cuda_scorer(resolution)
            else:
                from forza_writer.compute_backend import directml_scorer
                scorer = directml_scorer(resolution)
            candidates: list[PlacedShape] = []
            template_ids: list[int] = []
            xs: list[int] = []
            ys: list[int] = []
            for shape in usable_shapes:
                rotations = ROTATIONS_SYMMETRIC if shape.rotationally_symmetric else ROTATIONS_ASYMMETRIC
                for scale in SCALES:
                    for aspect in ASPECTS:
                        scale_x, scale_y = scale * aspect, scale / aspect
                        for rot in rotations:
                            template_key = (shape.shape_id, scale_x, scale_y, rot)
                            template_id, (ph, pw) = scorer.get_or_create_template(
                                template_key,
                                lambda s=shape, x=scale_x, y=scale_y, r=rot:
                                    _candidate_image(s, x, y, r, resolution))
                            for cx, cy in positions:
                                candidates.append(PlacedShape(shape.shape_id, cx, cy, scale_x, scale_y, rot))
                                template_ids.append(template_id)
                                xs.append(round(cx - pw / 2))
                                ys.append(round(cy - ph / 2))
            gains = scorer.score(template_ids, xs, ys, residual, target_mask, overshoot_penalty)
            if stats is not None:
                stats.candidates_tested += len(candidates)
            for gain, candidate in zip(gains, candidates):
                gain = policy.score(candidate.shape_id, float(gain))
                existing = per_shape.get(candidate.shape_id)
                if existing is None or float(gain) > existing[0]:
                    shape = PRIMITIVE_CATALOG[candidate.shape_id]
                    cmask = render_candidate(shape, candidate.cx, candidate.cy, candidate.scale_x,
                                             candidate.scale_y, candidate.rotation_deg, resolution)
                    per_shape[candidate.shape_id] = (float(gain), candidate, cmask)
        elif _rust_kernel is not None:
            # Fused render+score kernel: sweeps the whole scale x aspect x
            # rotation x position grid for one shape inside Rust (building
            # each scale/aspect/rotation template once, same idea as the
            # CUDA path's template cache above) and returns only the single
            # best-scoring placement, instead of materializing a Pillow mask
            # for every one of the ~thousands of candidates per shape.
            # policy.score() is applied afterward rather than inside the
            # sweep: it only ever scales a shape's *positive* gains by one
            # constant weight_for(shape_id), so it can't change which raw
            # candidate is the argmax for that shape (verified in
            # docs/RUST_CPU_ACCELERATION.md's implementation notes).
            residual_u8 = residual.view(np.uint8)
            target_u8 = target_mask.view(np.uint8)
            for shape in usable_shapes:
                rotations = ROTATIONS_SYMMETRIC if shape.rotationally_symmetric else ROTATIONS_ASYMMETRIC
                raw_gain, cx, cy, scale_x, scale_y, rot, evaluated = _rust_kernel.best_over_grid(
                    shape.mask.view(np.uint8), shape.rotationally_symmetric,
                    list(SCALES), list(ASPECTS), list(rotations), positions, resolution,
                    residual_u8, target_u8, overshoot_penalty)
                if stats is not None:
                    stats.candidates_tested += evaluated
                gain = policy.score(shape.shape_id, float(raw_gain))
                existing = per_shape.get(shape.shape_id)
                if existing is None or gain > existing[0]:
                    cmask = render_candidate(shape, cx, cy, scale_x, scale_y, rot, resolution)
                    per_shape[shape.shape_id] = (
                        gain, PlacedShape(shape.shape_id, cx, cy, scale_x, scale_y, rot), cmask)
        else:
            for shape in usable_shapes:
                rotations = ROTATIONS_SYMMETRIC if shape.rotationally_symmetric else ROTATIONS_ASYMMETRIC
                for scale in SCALES:
                    for aspect in ASPECTS:
                        scale_x, scale_y = scale * aspect, scale / aspect
                        for rot in rotations:
                            for (cx, cy) in positions:
                                cmask = render_candidate(shape, cx, cy, scale_x, scale_y, rot, resolution)
                                gain = policy.score(
                                    shape.shape_id,
                                    candidate_gain(cmask, residual, target_mask, overshoot_penalty))
                                if stats is not None:
                                    stats.candidates_tested += 1
                                existing = per_shape.get(shape.shape_id)
                                if existing is None or gain > existing[0]:
                                    per_shape[shape.shape_id] = (
                                        gain, PlacedShape(shape.shape_id, cx, cy, scale_x, scale_y, rot), cmask)

        if not per_shape:
            break

        if refine:
            # Re-apply the preference weight to the *refined* gain. Weighting
            # only the coarse pass would let a preference choose which shape
            # gets refined and then be discarded at the moment the winner is
            # actually picked, which is the one place it has to count.
            refined = []
            for _gain, cand, _mask in per_shape.values():
                r_shape, r_mask, r_gain = refine_candidate(
                    cand, residual, target_mask, resolution, overshoot_penalty)
                refined.append((policy.score(r_shape.shape_id, r_gain), r_mask, r_shape))
            best_gain, best_mask, best = max(refined, key=lambda item: item[0])
        else:
            best_gain, best, best_mask = max(per_shape.values(), key=lambda item: item[0])

        if stats is not None:
            # Every shape but the winner loses this round; a sub-threshold
            # winner is rejected too, and ends the fit.
            stats.candidates_rejected += max(0, len(per_shape) - 1)
            if best is None or best_gain < min_gain:
                stats.candidates_rejected += 1

        if best is None or best_gain < min_gain:
            break

        placed.append(best)
        covered |= best_mask
        residual &= ~best_mask

        intersection = int(np.count_nonzero(covered & target_mask))
        union = int(np.count_nonzero(covered | target_mask))
        iou = intersection / union if union else 1.0
        if iou >= quality_target:
            break

    if stats is not None:
        # Recomputed here rather than reusing the loop's last value: the loop
        # can exit without ever computing one (no viable candidate on the
        # first pass), and an early `break` leaves it stale by a layer.
        stats.iou = _coverage_iou(placed, target_mask, resolution)
        stats.record_placements(placed)

    return placed


def _coverage_iou(placements: list[PlacedShape], target_mask: np.ndarray,
                   resolution: int) -> float:
    """IoU of what `placements` actually cover against the target.

    Honours mask layers the same way FH6 does: a cutout subtracts from what
    is already covered rather than adding, so a stencil result is measured as
    what the player would see, not as the union of its layers.
    """
    covered = np.zeros_like(target_mask)
    for placement in placements:
        shape_mask = render_candidate(
            PRIMITIVE_CATALOG[placement.shape_id], placement.cx, placement.cy,
            placement.scale_x, placement.scale_y, placement.rotation_deg,
            resolution, placement.skew_x)
        covered = (covered & ~shape_mask) if placement.is_mask else (covered | shape_mask)
    intersection = int(np.count_nonzero(covered & target_mask))
    union = int(np.count_nonzero(covered | target_mask))
    return intersection / union if union else 1.0


def _curved_stencil_placements(target_mask: np.ndarray, resolution: int = DEFAULT_RESOLUTION,
                                max_layers: int | None = None,
                                quality_target: float | None = None,
                                overshoot_penalty: float | None = None,
                                compute_backend: str = "cpu",
                                policy: GenerationPolicy | None = None
                                ) -> list[PlacedShape] | None:
    """Stencil decomposition for a non-rectilinear (curved) glyph: one
    background Square sized to the glyph's bounding box, plus mask cutouts
    for the negative space within that box, found by the same greedy
    `fit_silhouette` search used for direct fills, run against the negative
    space instead of the glyph itself, rather than `rect_decompose`'s exact
    rectangle cover (which only works when the negative space is itself
    rectilinear).

    Because the cutout cover comes from a search, not an exact decomposition,
    it can leave a visible gap between the background's edge and the glyph's
    true outline. Callers that care about quality should check the result
    against `target_mask` (e.g. via IoU) rather than assuming a perfect cover
    the way the rectilinear stencil path can.

    Returns None if the glyph has no negative space within its own bounding
    box (masking would change nothing), the search finds nothing to cut, or
    the policy disallows the Square this strategy needs for its background.
    """
    policy = policy or DEFAULT_POLICY
    if not policy.allows_exact_cover:
        # The background here is a Square by construction; without it there is
        # no stencil to build, so the caller falls back to a direct fill.
        return None
    bbox = _residual_bbox(target_mask)
    if bbox is None:
        return None
    x0, y0, x1, y1 = bbox
    background = PlacedShape(
        shape_id="square", cx=(x0 + x1 + 1) / 2.0, cy=(y0 + y1 + 1) / 2.0,
        scale_x=(x1 - x0 + 1) / resolution, scale_y=(y1 - y0 + 1) / resolution,
        rotation_deg=0.0, is_mask=False)

    negative_mask = np.zeros_like(target_mask)
    negative_mask[y0:y1 + 1, x0:x1 + 1] = True
    negative_mask &= ~target_mask
    if not negative_mask.any():
        return None

    cutouts = fit_silhouette(
        negative_mask, resolution=resolution, max_layers=max_layers,
        quality_target=quality_target, overshoot_penalty=overshoot_penalty,
        compute_backend=compute_backend, policy=policy)
    if not cutouts:
        return None
    cutouts = [replace(p, is_mask=True) for p in cutouts]
    return [background] + cutouts


def _px_to_glyph(x_px: float, y_px: float, resolution: int) -> tuple[float, float]:
    x = x_px / resolution * (2 * COORD_RANGE) - COORD_RANGE
    y = COORD_RANGE - y_px / resolution * (2 * COORD_RANGE)
    return x, y


def _glyph_to_px(x: float, y: float, resolution: int) -> tuple[float, float]:
    """Inverse of `_px_to_glyph`."""
    x_px = (x + COORD_RANGE) / (2 * COORD_RANGE) * resolution
    y_px = (COORD_RANGE - y) / (2 * COORD_RANGE) * resolution
    return x_px, y_px


def shape_to_render_params(shape: dict, resolution: int = DEFAULT_RESOLUTION,
                            glyph_size: float = 300.0
                            ) -> tuple[str | None, float, float, float, float, float, float]:
    """Inverse of `placements_to_shapes`: given one forza_writer shape dict
    (real FH6 editor units), return `(shape_id, cx_px, cy_px, scale_x,
    scale_y, rotation_deg)` in the same normalized/pixel space
    `rasterize_contours`/`render_candidate` use, so an existing glyph's
    saved shapes can be redrawn with the same preview pipeline the fitter's
    own debug rendering uses. `shape_id` is None if `type_word` doesn't
    resolve to a known Primitives-family shape (nothing to render, but the
    caller can still show the raw data)."""
    from forza_writer.layout import PIXEL_ART_SQUARE_SIZE
    from forza_writer.shapes import shape_word_to_resource

    real_x, data_y, fh6_scale_x, fh6_scale_y, rotation_deg = shape["data"][:5]
    real_units_per_glyph_unit = glyph_size / (2 * COORD_RANGE)
    gx = real_x / real_units_per_glyph_unit
    gy = -data_y / real_units_per_glyph_unit
    cx_px, cy_px = _glyph_to_px(gx, gy, resolution)

    scale_x = fh6_scale_x * PIXEL_ART_SQUARE_SIZE / glyph_size
    scale_y = fh6_scale_y * PIXEL_ART_SQUARE_SIZE / glyph_size

    shape_id = None
    resource = shape_word_to_resource(shape["type_word"])
    if resource and resource[0] == "Primitives":
        for candidate_id, candidate in PRIMITIVE_CATALOG.items():
            if candidate.resource_index == resource[1]:
                shape_id = candidate_id
                break

    skew_x = float(shape["data"][5]) if len(shape["data"]) > 5 else 0.0
    return shape_id, cx_px, cy_px, scale_x, scale_y, rotation_deg, skew_x


def placements_to_shapes(placements: list[PlacedShape], resolution: int,
                          glyph_size: float = 300.0,
                          solid_color: tuple[int, int, int, int] = (255, 255, 255, 255),
                          high_contrast_seed: int | None = None) -> list[dict]:
    """Convert PlacedShape placements (pixel space, normalized ±COORD_RANGE
    glyph space) into forza_writer shape dicts in real FH6 editor units,
    matching forza_writer.layout's convention exactly:
    `data = [x, -y, scaleX, scaleY, rotationDeg, skewSlope, mask]`.

    Two different unit spaces meet here and must not be confused:
    normalize_to_128's ±COORD_RANGE space is sized for SNORM16 mesh
    coordinates, not FH6's actual vinyl-layer coordinate/scale convention,
    where `scale=1.0` means a fixed native size of
    `forza_writer.layout.PIXEL_ART_SQUARE_SIZE` editor units (~128.5),
    regardless of glyph size. `glyph_size` is the real-unit width/height a
    single glyph's ±COORD_RANGE bounding box should occupy once placed,
    300 default, matching layout.py's own single-line glyph_height for its
    default target_height=360 (360 * 0.82 ~= 295).

    Every non-mask shape gets `solid_color` (defaults to plain white,
    exactly the old hardcoded behavior) unless `high_contrast_seed` is
    given, in which case each shape gets its own color from
    `forza_writer.high_contrast`'s curated palette instead -- deterministic
    for a given seed and layout, so regenerating the same glyph with the
    same seed reproduces the same per-shape colors (see that module for
    why). Mask shapes always stay the special mask color regardless of
    either: a mask is a transparency cutout, never actually drawn, so
    "which color" doesn't apply to it the way it does to a visible shape.
    """
    from forza_writer.high_contrast import assign_high_contrast_colors
    from forza_writer.layout import PIXEL_ART_SQUARE_SIZE
    from forza_writer.shapes import resource_to_shape_word, resource_to_typecode

    real_units_per_glyph_unit = glyph_size / (2 * COORD_RANGE)

    glyph_centers = [_px_to_glyph(p.cx, p.cy, resolution) for p in placements]
    shape_colors = (assign_high_contrast_colors(glyph_centers, high_contrast_seed)
                     if high_contrast_seed is not None else None)

    shapes = []
    for i, p in enumerate(placements):
        shape = PRIMITIVE_CATALOG[p.shape_id]
        gx, gy = glyph_centers[i]
        real_x = gx * real_units_per_glyph_unit
        real_y = gy * real_units_per_glyph_unit
        fh6_scale_x = p.scale_x * glyph_size / PIXEL_ART_SQUARE_SIZE
        fh6_scale_y = p.scale_y * glyph_size / PIXEL_ART_SQUARE_SIZE
        # Mask convention matches forza-painter-fh6's make_fh6_mask_shape:
        # color (0,0,0,255) and data[6]=1, which is what the game reads as
        # "this layer punches transparency through what's below it", plus
        # our own "mask" key, which export.to_json() must preserve rather
        # than reset to False.
        if p.is_mask:
            color = [0, 0, 0, 255]
        elif shape_colors is not None:
            color = list(shape_colors[i])
        else:
            color = list(solid_color)
        mask_flag = 1 if p.is_mask else 0
        shapes.append({
            "type": resource_to_typecode("Primitives", shape.resource_index),
            "type_word": resource_to_shape_word("Primitives", shape.resource_index),
            "data": [round(real_x, 6), round(-real_y, 6) or 0.0,
                     round(fh6_scale_x, 6), round(fh6_scale_y, 6),
                     round(p.rotation_deg, 6), round(p.skew_x, 6) or 0.0, mask_flag],
            "color": color,
            "mask": p.is_mask,
        })
    return shapes


# A rectilinear glyph whose decomposition needs more rectangles than this
# isn't really benefiting from the exact-cover path any more (think a blocky
# glyph with lots of small stair-stepped detail), so fall back to the search,
# which trades a little accuracy for far fewer layers.
RECT_DECOMPOSE_MAX = 20


def _rectilinear_placements(target_mask: np.ndarray, resolution: int,
                             mode: MaskMode = "auto"
                             ) -> tuple[list[PlacedShape], str] | None:
    """Compare the exact-cover strategies available for a rectilinear mask,
    and return whichever `mode` selects, or None if none produces a usable
    cover (caller falls back to the primitive search).

    Direct (fill the ink) and stencil (background + negative-space cutout
    masks) are both zero-error on a rectilinear glyph, so under `mode="auto"`
    this is a pure shape-count comparison, not an accuracy tradeoff. Direct
    wins ties: it needs no mask-layer semantics, and those haven't been
    verified against a live FH6 session yet (see RESEARCH.md) where the
    plain fill path has.

    `mode="never"` (the GUI's "Allow layer masks" toggle, unchecked) skips
    the stencil candidate entirely, forcing direct fill even when stencil
    would need fewer shapes. `mode="force"` (a per-glyph Advanced Mode
    override) returns the stencil cover whenever one exists, even if it
    needs more shapes than direct fill: an explicit per-glyph choice, not
    the shape-count-minimizing default.
    """
    from forza_writer.rect_decompose import (
        decompose_mask_to_rects, rects_to_placements, stencil_placements)

    rects = decompose_mask_to_rects(target_mask, max_rects=RECT_DECOMPOSE_MAX + 1)
    direct = rects_to_placements(rects, resolution) if 0 < len(rects) <= RECT_DECOMPOSE_MAX else None
    stencil = (stencil_placements(target_mask, resolution, max_rects=RECT_DECOMPOSE_MAX)
               if mode != "never" else None)

    if mode == "force" and stencil:
        return stencil, "stencil"

    candidates = []
    if direct:
        candidates.append((direct, "rect_decompose"))
    if stencil:
        candidates.append((stencil, "stencil"))
    if not candidates:
        return None
    return min(candidates, key=lambda c: len(c[0]))  # stable: direct sorts first on ties


def fit_placements(contours_norm, resolution: int = DEFAULT_RESOLUTION,
                    max_layers: int | None = None,
                    quality_target: float | None = None,
                   mask_mode: MaskMode = "auto", compute_backend: str = "cpu",
                   policy: GenerationPolicy | None = None,
                   stats: GenerationStats | None = None) -> tuple[list[PlacedShape], str]:
    """Route a glyph to whichever fitting strategy suits its geometry, and
    return `(placements, strategy_name)`.

    Rectilinear glyphs (blocky/stencil fonts, every contour edge horizontal
    or vertical) get an exact rectangle decomposition, in whichever of two
    forms `mask_mode` selects (see `_rectilinear_placements`): fewer layers
    *and* perfect coverage either way, because the answer can be computed
    rather than searched for. Everything else gets the greedy primitive
    search, which handles curves in a handful of shapes where rectangles
    would need dozens.

    Measured on Amarillo USAF: routing takes 'E' from 9 shapes at IoU 0.855
    to 4 shapes at IoU 1.000, while leaving 'O' at 2 shapes rather than the
    18 rectangles an unrouted decomposition would produce. On that
    particular font the stencil path never actually wins under `"auto"`:
    its strokes are already the "simple" side of the shape. It does win on
    other fonts though, e.g. the Minecraft Standard Galactic Alphabet's 'X'
    (14 direct vs. 10 stencil) and 'Z' (12 vs. 7), so `"auto"` compares
    automatically rather than assuming, and `"never"` exists for callers who'd
    rather opt out of that trade entirely.

    `mask_mode="force"` on a curved (non-rectilinear) glyph invokes
    `_curved_stencil_placements` (see its docstring for why
    this is a search, not an exact cover, unlike the rectilinear case). This
    is deliberately *not* attempted under `"auto"`: it doubles the cost of an
    already-expensive greedy search, so it only runs when a caller explicitly
    asks for it on a specific glyph, never as a blind per-glyph comparison
    across a whole batch.
    """
    from forza_writer.rect_decompose import is_rectilinear

    policy = policy or DEFAULT_POLICY
    effective_quality = policy.quality_target if quality_target is None else quality_target
    target_mask = rasterize_contours(contours_norm, resolution)

    # The exact-cover routes are built entirely from Square (see
    # generation_policy.EXACT_COVER_SHAPE). If the policy withholds it, or
    # disables exact cover outright, as "Primitive Only" does, skip them
    # rather than let rect_decompose's assertion fire, and let the greedy
    # search answer the glyph instead.
    if is_rectilinear(contours_norm) and policy.allows_exact_cover:
        result = _rectilinear_placements(target_mask, resolution, mask_mode)
        if result is not None:
            if stats is not None:
                stats.strategy = result[1]
                stats.record_placements(result[0])
                stats.iou = _coverage_iou(result[0], target_mask, resolution)
            return result

    def search(active: GenerationPolicy) -> tuple[list[PlacedShape], str]:
        direct = (fit_silhouette(
            target_mask, resolution=resolution, max_layers=max_layers,
            quality_target=quality_target, compute_backend=compute_backend,
            policy=active, stats=stats),
            "primitive_search")
        if mask_mode != "force":
            return direct
        stencil = _curved_stencil_placements(
            target_mask, resolution=resolution, max_layers=max_layers,
            quality_target=quality_target, compute_backend=compute_backend,
            policy=active)
        if not stencil:
            return direct
        return stencil, "stencil_search"

    placements, strategy = search(policy)
    achieved = _coverage_iou(placements, target_mask, resolution)

    # Fallback ladder. Only reached when the restricted set genuinely fell
    # short, so an unrestricted policy never pays for it. Whatever happens,
    # the outcome is recorded rather than applied silently. The one thing
    # this must never do is quietly ignore the user's restriction.
    if achieved < effective_quality:
        shortfall = (f"Selected shapes reached IoU {achieved:.3f}, "
                     f"below the {effective_quality:.3f} target.")
        widened = policy.fallback_policy()
        if widened is None:
            if stats is not None and policy.fallback == "warn":
                stats.warn(shortfall + " Kept the selection (fallback: warn).")
        else:
            retry_placements, retry_strategy = search(widened)
            retry_achieved = _coverage_iou(retry_placements, target_mask, resolution)
            # Keep the fallback only if it actually helped; otherwise the user
            # gets extra shape types they restricted away for nothing.
            if retry_achieved > achieved:
                placements, strategy, achieved = retry_placements, retry_strategy, retry_achieved
                if stats is not None:
                    stats.fallback_used = True
                    stats.fallback_reason = (
                        f"{shortfall} Re-fit with the '{policy.fallback}' fallback "
                        f"reached IoU {retry_achieved:.3f}.")
            elif stats is not None:
                stats.warn(shortfall + " The fallback did not improve on it; kept the selection.")

    if stats is not None:
        stats.strategy = strategy
        stats.record_placements(placements)
        stats.iou = achieved

    return placements, strategy


def fit_glyph_with_strategy(char: str, font_path: Path, curve_segments: int = 8,
                             resolution: int = DEFAULT_RESOLUTION, max_layers: int | None = None,
                             quality_target: float | None = None,
                             glyph_size: float = 300.0, mask_mode: MaskMode = "auto",
                             compute_backend: str = "cpu",
                             policy: GenerationPolicy | None = None,
                             stats: GenerationStats | None = None,
                             solid_color: tuple[int, int, int, int] = (255, 255, 255, 255),
                             high_contrast_seed: int | None = None) -> tuple[list[dict], str]:
    """Like `fit_glyph`, but also returns which strategy was used
    (`"rect_decompose"` / `"stencil"` / `"stencil_search"` /
    `"primitive_search"`), for callers that want to record it, e.g.
    gen_fontpack.py's manifest.

    Pass a `GenerationStats` to collect per-glyph diagnostics (shape counts by
    type, candidates tested/rejected, achieved IoU, whether a fallback fired,
    elapsed time) without re-deriving any of it from the returned shapes.

    `solid_color`/`high_contrast_seed` pass straight through to
    `placements_to_shapes` -- see its docstring for how they interact
    (`high_contrast_seed`, when given, wins).
    """
    from gen_modelbin import extract_contours, normalize_to_128

    if stats is not None:
        stats.start()
    contours, upm = extract_contours(char, font_path, curve_segments)
    contours_norm = normalize_to_128(contours, upm)
    placements, strategy = fit_placements(contours_norm, resolution, max_layers, quality_target,
                                           mask_mode, compute_backend, policy=policy, stats=stats)
    if stats is not None:
        stats.finish()
    shapes = placements_to_shapes(placements, resolution, glyph_size,
                                   solid_color=solid_color, high_contrast_seed=high_contrast_seed)
    return shapes, strategy


def fit_glyph_name_with_strategy(glyph_name: str, font_path: Path, curve_segments: int = 8,
                                  resolution: int = DEFAULT_RESOLUTION,
                                  max_layers: int = DEFAULT_MAX_LAYERS,
                                  quality_target: float = DEFAULT_QUALITY_TARGET,
                                  glyph_size: float = 300.0,
                                  mask_mode: MaskMode = "auto",
                                  compute_backend: str = "cpu",
                                  solid_color: tuple[int, int, int, int] = (255, 255, 255, 255),
                                  ) -> tuple[list[dict], str]:
    """Fit an explicit shaped OpenType glyph rather than a cmap character."""
    from gen_modelbin import extract_glyph_contours, normalize_to_128

    contours, upm = extract_glyph_contours(glyph_name, font_path, curve_segments)
    if not any(contours):
        return [], "empty_outline"
    contours_norm = normalize_to_128(contours, upm)
    placements, strategy = fit_placements(
        contours_norm, resolution, max_layers, quality_target,
        mask_mode, compute_backend)
    shapes = placements_to_shapes(placements, resolution, glyph_size, solid_color=solid_color)
    return shapes, strategy


def fit_glyph(char: str, font_path: Path, curve_segments: int = 8,
              resolution: int = DEFAULT_RESOLUTION, max_layers: int = DEFAULT_MAX_LAYERS,
              quality_target: float = DEFAULT_QUALITY_TARGET, glyph_size: float = 300.0) -> list[dict]:
    """Generate a primitive-composed FH6 shape list for one glyph. No
    .modelbin/catalog hijack involved: every shape used already exists in
    FH6's built-in Primitives family."""
    shapes, _strategy = fit_glyph_with_strategy(
        char, font_path, curve_segments, resolution, max_layers, quality_target, glyph_size)
    return shapes


def inspect_glyph_geometry(char: str, font_path: Path, curve_segments: int = 8,
                           resolution: int = DEFAULT_RESOLUTION) -> dict:
    """Cheap Configurator-list metadata without running primitive search.

    Rectilinear glyphs can still report their exact strategy/count because
    rectangle decomposition is deterministic and inexpensive. Curved glyphs
    deliberately defer their fit until selected.
    """
    from forza_writer.rect_decompose import is_rectilinear
    from gen_modelbin import extract_contours, normalize_to_128

    contours, upm = extract_contours(char, font_path, curve_segments)
    contours_norm = normalize_to_128(contours, upm)
    rectilinear = is_rectilinear(contours_norm)
    result = {
        "rectilinear": rectilinear,
        "auto_strategy": None,
        "auto_shape_count": None,
        "can_force_mask": False,
        "forced_shape_count": None,
        "forced_iou": None,
    }
    if not rectilinear:
        return result
    target_mask = rasterize_contours(contours_norm, resolution)
    auto = _rectilinear_placements(target_mask, resolution, "auto")
    forced = _rectilinear_placements(target_mask, resolution, "force")
    if auto:
        result["auto_strategy"] = auto[1]
        result["auto_shape_count"] = len(auto[0])
    if forced and forced[1] == "stencil":
        result["can_force_mask"] = True
        result["forced_shape_count"] = len(forced[0])
        result["forced_iou"] = 1.0
    return result


def preview_glyph_mask_options(char: str, font_path: Path, curve_segments: int = 8,
                                resolution: int = DEFAULT_RESOLUTION, max_layers: int = DEFAULT_MAX_LAYERS,
                                quality_target: float = DEFAULT_QUALITY_TARGET,
                                curved_force_check: bool = True, compute_backend: str = "cpu",
                                return_placements: bool = False) -> dict:
    """Per-glyph mask summary for Advanced Mode's glyph list: what `"auto"`
    picks today, and whether `"force"` is even achievable for this glyph.

    For rectilinear glyphs this whole thing is essentially free (exact
    rectangle decomposition, no search, same as `_rectilinear_placements`
    already does), so it's always computed. For curved glyphs,
    `auto_strategy`/`auto_shape_count` are free too: `"auto"` never
    attempts a mask on a curved glyph by construction (see `fit_placements`),
    but `can_force_mask`/`forced_shape_count`/`forced_iou` require
    actually running `_curved_stencil_placements`, which *is* the expensive
    part. `curved_force_check=False` skips that one call (leaving those
    expensive forced fit. It can still report whether the glyph has negative
    space that could be cut, but leaves the forced shape count and IoU unset.
    Pass it when a responsive caller only needs the normal preview; request
    the forced fit when the user actually chooses that mode.

    Returns a dict: `rectilinear`, `auto_strategy`, `auto_shape_count`,
    `can_force_mask`, `forced_shape_count` (None if masking isn't
    achievable, or wasn't checked), `forced_iou` (1.0 for an exact
    rectilinear cover; the measured IoU against the true outline for a
    curved glyph's searched cover; None if masking isn't achievable or
    wasn't checked).
    """
    from forza_writer.rect_decompose import is_rectilinear
    from gen_modelbin import extract_contours, normalize_to_128

    contours, upm = extract_contours(char, font_path, curve_segments)
    contours_norm = normalize_to_128(contours, upm)
    target_mask = rasterize_contours(contours_norm, resolution)
    rectilinear = is_rectilinear(contours_norm)

    auto_placements, auto_strategy = fit_placements(
        contours_norm, resolution, max_layers, quality_target, "auto", compute_backend)

    result = {
        "rectilinear": rectilinear,
        "auto_strategy": auto_strategy,
        "auto_shape_count": len(auto_placements),
        "can_force_mask": False,
        "forced_shape_count": None,
        "forced_iou": None,
    }
    if return_placements:
        result["_auto_placements"] = auto_placements

    if rectilinear:
        forced = _rectilinear_placements(target_mask, resolution, "force")
        if forced is not None and forced[1] == "stencil":
            result["can_force_mask"] = True
            result["forced_shape_count"] = len(forced[0])
            result["forced_iou"] = 1.0  # exact cover, same as the direct-fill path
            if return_placements:
                result["_forced_placements"] = forced[0]
        return result

    if not curved_force_check:
        bbox = _residual_bbox(target_mask)
        if bbox is not None:
            x0, y0, x1, y1 = bbox
            result["can_force_mask"] = bool((~target_mask[y0:y1 + 1, x0:x1 + 1]).any())
        return result

    forced_curved = _curved_stencil_placements(
        target_mask, resolution=resolution, max_layers=max_layers,
        quality_target=quality_target, compute_backend=compute_backend)
    if forced_curved:
        result["can_force_mask"] = True
        result["forced_shape_count"] = len(forced_curved)
        covered = np.zeros_like(target_mask)
        for p in forced_curved:
            shape_mask = render_candidate(PRIMITIVE_CATALOG[p.shape_id], p.cx, p.cy,
                                           p.scale_x, p.scale_y, p.rotation_deg, resolution)
            covered = (covered & ~shape_mask) if p.is_mask else (covered | shape_mask)
        intersection = int(np.count_nonzero(covered & target_mask))
        union = int(np.count_nonzero(covered | target_mask))
        result["forced_iou"] = intersection / union if union else 1.0
        if return_placements:
            result["_forced_placements"] = forced_curved
    return result
