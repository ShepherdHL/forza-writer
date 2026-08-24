//! Fused render+score kernel for `forza_writer.primitive_fit`'s primitive
//! search (see `docs/RUST_CPU_ACCELERATION.md`, candidate order item 1).
//!
//! This replicates -- pixel-for-pixel -- the transform pipeline Python's
//! `_candidate_image`/`render_candidate` build from Pillow (`resize`,
//! `transform(AFFINE)` for skew, `rotate(expand=True)`), all using Pillow's
//! NEAREST sampling convention: for each destination pixel, map its center
//! through the inverse transform and floor to the source index. That
//! convention was verified empirically against real Pillow output (resize
//! and rotate/skew both sample `floor((dst + 0.5) * scale)` in their
//! respective coordinate systems) before writing this, since Gate 3 in the
//! plan doc requires bit-exact output parity with the Python path, not just
//! a similar-looking result.
//!
//! Two entry points are exposed:
//! - `score_candidate`: one placement, full skew/rotation support. Used by
//!   `refine_candidate`'s local hill-climb (one trial at a time).
//! - `best_over_grid`: the coarse per-shape sweep over
//!   scale x aspect x rotation x position. Skew is always 0 here (matches
//!   the Python coarse loop, which never passes skew), so each
//!   scale/aspect/rotation combination's resized+rotated template is built
//!   once and reused across every position in the grid -- the same
//!   template-caching idea `compute_backend.py`'s CUDA path already uses,
//!   applied here to cut down on redundant Pillow-equivalent resampling.
//!
//! Both keep the exact Python fallback in `primitive_fit.py` as the
//! reference implementation; this module is opt-in and never the only
//! implementation of the algorithm.

use numpy::PyReadonlyArray2;
use pyo3::prelude::*;

/// Python's `round()`: round-half-to-even on the actual f64 value.
/// Rust's `f64::round()` rounds half away from zero, which disagrees with
/// Python at exact `.5` boundaries -- and `_candidate_image` calls
/// `round()` on scale/position math where ties are reachable, so this must
/// match or the composited pixel grid can be off by one row/column.
fn py_round(x: f64) -> i64 {
    let floor = x.floor();
    let diff = x - floor;
    let fl = floor as i64;
    if diff < 0.5 {
        fl
    } else if diff > 0.5 {
        fl + 1
    } else if fl % 2 == 0 {
        fl
    } else {
        fl + 1
    }
}

/// A row-major boolean-as-u8 raster with explicit dimensions, mirroring the
/// numpy arrays Python passes across (via `.view(np.uint8)`, zero-copy).
struct Raster {
    data: Vec<u8>,
    w: usize,
    h: usize,
}

impl Raster {
    fn get(&self, x: i64, y: i64) -> u8 {
        if x < 0 || y < 0 || x as usize >= self.w || y as usize >= self.h {
            0
        } else {
            self.data[y as usize * self.w + x as usize]
        }
    }
}

/// Nearest-neighbor resize, matching Pillow's `ImagingScaleAffine` (the
/// fast path `Image.resize(..., NEAREST)` actually takes at the C level --
/// *not* a per-pixel `floor((dst+0.5)*src/dst)` formula, but a running
/// double accumulator: `xo = a0*0.5; for x: xin = trunc(xo); xo += a0`,
/// where `a0 = src_w/dst_w`. This must be replicated as an accumulation,
/// not a direct multiply -- the two disagree by up to one pixel at the
/// floating-point boundaries floating-point drift lands on, and the plan's
/// gate 3 requires bit-exact output parity, not "usually matches".
/// (Verified against `Geometry.c`'s `ImagingScaleAffine` in the Pillow
/// source and cross-checked against live `PIL.Image.resize` output.)
fn resize_nearest(src: &Raster, dst_w: usize, dst_h: usize) -> Raster {
    let a0 = src.w as f64 / dst_w as f64;
    let a4 = src.h as f64 / dst_h as f64;

    let mut xtab = vec![-1i64; dst_w];
    let mut xo = a0 * 0.5;
    for x in 0..dst_w {
        let xin = if xo < 0.0 { -1 } else { xo as i64 };
        if xin >= 0 && (xin as usize) < src.w {
            xtab[x] = xin;
        }
        xo += a0;
    }

    let mut data = vec![0u8; dst_w * dst_h];
    let mut yo = a4 * 0.5;
    for y in 0..dst_h {
        let yin = if yo < 0.0 { -1 } else { yo as i64 };
        if yin >= 0 && (yin as usize) < src.h {
            for x in 0..dst_w {
                if xtab[x] >= 0 {
                    data[y * dst_w + x] = src.get(xtab[x], yin);
                }
            }
        }
        yo += a4;
    }
    Raster { data, w: dst_w, h: dst_h }
}

/// Pillow's 16.16 fixed-point NEAREST affine sampler (`Geometry.c`'s
/// `affine_fixed`), the path `Image.transform(AFFINE, ..., NEAREST)` and
/// `Image.rotate(..., NEAREST)` actually take whenever the transform isn't
/// a pure axis-aligned scale (i.e. whenever shear or rotation is present --
/// exactly our skew and rotate cases). `matrix` is `(a, b, c, d, e, f)` for
/// `(sx, sy) = (a*x + b*y + c, d*x + e*y + f)`. Coefficients are quantized
/// to 16.16 fixed point *once*, then accumulated with integer addition per
/// row/column (`xx += a0_fixed`, row start `a2_fixed += a1_fixed`) --
/// that integer accumulation, not a per-pixel float recomputation, is what
/// must be replicated for bit-exact parity.
fn affine_fixed_nearest(
    src: &Raster,
    matrix: (f64, f64, f64, f64, f64, f64),
    out_w: usize,
    out_h: usize,
) -> Raster {
    let (a, b, c, d, e, f) = matrix;
    let fix = |v: f64| -> i64 { (v * 65536.0 + 0.5).floor() as i64 };

    let a0 = fix(a);
    let a1 = fix(b);
    let a3 = fix(d);
    let a4 = fix(e);
    let mut row_c = fix(c + a * 0.5 + b * 0.5);
    let mut row_f = fix(f + d * 0.5 + e * 0.5);

    let mut data = vec![0u8; out_w * out_h];
    for oy in 0..out_h {
        let mut xx = row_c;
        let mut yy = row_f;
        for ox in 0..out_w {
            let xin = xx >> 16;
            if xin >= 0 && (xin as usize) < src.w {
                let yin = yy >> 16;
                if yin >= 0 && (yin as usize) < src.h {
                    data[oy * out_w + ox] = src.get(xin, yin);
                }
            }
            xx += a0;
            yy += a3;
        }
        row_c += a1;
        row_f += a4;
    }
    Raster { data, w: out_w, h: out_h }
}

/// Horizontal shear, matching `primitive_fit._candidate_image`'s skew
/// branch: `img.transform((out_w, h), AFFINE, (1, -skew_x, skew_x*h/2-pad,
/// 0, 1, 0), NEAREST, fillcolor=0)`.
fn apply_skew(src: &Raster, skew_x: f64) -> Raster {
    if skew_x == 0.0 {
        return Raster { data: src.data.clone(), w: src.w, h: src.h };
    }
    let h = src.h;
    let extra = (skew_x.abs() * h as f64).ceil() as usize;
    let out_w = src.w + extra;
    let pad = (out_w as f64 - src.w as f64) / 2.0;
    let c = skew_x * h as f64 / 2.0 - pad;
    affine_fixed_nearest(src, (1.0, -skew_x, c, 0.0, 1.0, 0.0), out_w, h)
}

/// Rotation with `expand=True`, matching `PIL.Image.rotate`'s affine-matrix
/// construction (see `PIL.Image.rotate` source: reverse rotation matrix
/// around the image center, output bbox from the four transformed corners
/// computed in plain double precision -- only the final NEAREST sampling
/// pass uses the fixed-point accumulator). `rotation_deg` is in degrees,
/// counter-clockwise, same convention Pillow uses.
fn apply_rotate(src: &Raster, rotation_deg: f64) -> Raster {
    if rotation_deg == 0.0 {
        return Raster { data: src.data.clone(), w: src.w, h: src.h };
    }
    let w = src.w as f64;
    let h = src.h as f64;
    let cx = w / 2.0;
    let cy = h / 2.0;
    let angle = -(rotation_deg.rem_euclid(360.0)).to_radians();
    let (sin_a, cos_a) = angle.sin_cos();
    let a = cos_a;
    let b = sin_a;
    let d = -sin_a;
    let e = cos_a;
    let transform = |x: f64, y: f64, a: f64, b: f64, c: f64, d: f64, e: f64, f: f64| {
        (a * x + b * y + c, d * x + e * y + f)
    };
    let (mut c, mut f) = transform(-cx, -cy, a, b, 0.0, d, e, 0.0);
    c += cx;
    f += cy;

    // Output bbox from the four corners of the source image (plain double
    // math, matching PIL.Image.rotate's Python-level bbox computation).
    let mut xs = Vec::with_capacity(4);
    let mut ys = Vec::with_capacity(4);
    for &(x, y) in &[(0.0, 0.0), (w, 0.0), (w, h), (0.0, h)] {
        let (tx, ty) = transform(x, y, a, b, c, d, e, f);
        xs.push(tx);
        ys.push(ty);
    }
    let nw = (xs.iter().cloned().fold(f64::MIN, f64::max).ceil()
        - xs.iter().cloned().fold(f64::MAX, f64::min).floor()) as usize;
    let nh = (ys.iter().cloned().fold(f64::MIN, f64::max).ceil()
        - ys.iter().cloned().fold(f64::MAX, f64::min).floor()) as usize;

    let (tx, ty) = transform(-(nw as f64 - w) / 2.0, -(nh as f64 - h) / 2.0, a, b, c, d, e, f);
    c = tx;
    f = ty;

    affine_fixed_nearest(src, (a, b, c, d, e, f), nw, nh)
}

/// Build the final transformed candidate footprint, matching
/// `_candidate_image`'s resize -> skew -> rotate pipeline exactly.
fn build_template(
    shape_mask: &Raster,
    scale_x: f64,
    scale_y: f64,
    rotation_deg: f64,
    skew_x: f64,
    canvas_res: usize,
    rotationally_symmetric: bool,
) -> Raster {
    let w = (py_round(canvas_res as f64 * scale_x)).max(1) as usize;
    let h = (py_round(canvas_res as f64 * scale_y)).max(1) as usize;
    let resized = resize_nearest(shape_mask, w, h);
    let skewed = if skew_x != 0.0 { apply_skew(&resized, skew_x) } else { resized };
    if rotation_deg != 0.0 && !rotationally_symmetric {
        apply_rotate(&skewed, rotation_deg)
    } else {
        skewed
    }
}

/// Composite `template` centered at `(cx_px, cy_px)` on a `canvas_res` x
/// `canvas_res` canvas (matching `render_candidate`'s placement math
/// exactly, including its `round()` calls) and score it in the same pass:
/// `count(candidate & residual) - overshoot_penalty * count(candidate &
/// ~target)`, without ever materializing the full canvas array.
fn composite_and_score(
    template: &Raster,
    cx_px: f64,
    cy_px: f64,
    canvas_res: usize,
    residual: &Raster,
    target: &Raster,
    overshoot_penalty: f64,
) -> f64 {
    let pw = template.w as i64;
    let ph = template.h as i64;
    let px = py_round(cx_px - pw as f64 / 2.0);
    let py = py_round(cy_px - ph as f64 / 2.0);
    let res = canvas_res as i64;

    let dst_x0 = px.max(0);
    let dst_y0 = py.max(0);
    let dst_x1 = (px + pw).min(res);
    let dst_y1 = (py + ph).min(res);
    if dst_x1 <= dst_x0 || dst_y1 <= dst_y0 {
        return 0.0;
    }

    let mut new_coverage: i64 = 0;
    let mut overshoot: i64 = 0;
    for cy in dst_y0..dst_y1 {
        let ty = cy - py;
        for cx in dst_x0..dst_x1 {
            let tx = cx - px;
            if template.get(tx, ty) != 0 {
                if residual.get(cx, cy) != 0 {
                    new_coverage += 1;
                }
                if target.get(cx, cy) == 0 {
                    overshoot += 1;
                }
            }
        }
    }
    new_coverage as f64 - overshoot_penalty * overshoot as f64
}

fn raster_from_u8(arr: &PyReadonlyArray2<u8>) -> Raster {
    let view = arr.as_array();
    let (h, w) = (view.shape()[0], view.shape()[1]);
    let data: Vec<u8> = view.iter().cloned().collect();
    Raster { data, w, h }
}

/// Score exactly one candidate placement. `shape_mask`, `residual`, and
/// `target_mask` are boolean numpy arrays viewed as `uint8` on the Python
/// side (zero-copy) so no per-element conversion happens crossing the FFI
/// boundary.
#[pyfunction]
#[pyo3(signature = (shape_mask, rotationally_symmetric, scale_x, scale_y, rotation_deg, skew_x,
                     cx_px, cy_px, canvas_res, residual, target_mask, overshoot_penalty))]
#[allow(clippy::too_many_arguments)]
fn score_candidate(
    shape_mask: PyReadonlyArray2<u8>,
    rotationally_symmetric: bool,
    scale_x: f64,
    scale_y: f64,
    rotation_deg: f64,
    skew_x: f64,
    cx_px: f64,
    cy_px: f64,
    canvas_res: usize,
    residual: PyReadonlyArray2<u8>,
    target_mask: PyReadonlyArray2<u8>,
    overshoot_penalty: f64,
) -> f64 {
    let shape_raster = raster_from_u8(&shape_mask);
    let residual_raster = raster_from_u8(&residual);
    let target_raster = raster_from_u8(&target_mask);
    let template = build_template(
        &shape_raster, scale_x, scale_y, rotation_deg, skew_x, canvas_res, rotationally_symmetric);
    composite_and_score(&template, cx_px, cy_px, canvas_res, &residual_raster, &target_raster, overshoot_penalty)
}

/// Coarse per-shape sweep over scale x aspect x rotation x position,
/// returning the single best-scoring placement. `scales`/`aspects` follow
/// `primitive_fit.py`'s convention: `scale_x = scale*aspect, scale_y =
/// scale/aspect`. Skew is always 0 here, matching the Python coarse loop.
/// Returns `(best_gain, cx, cy, scale_x, scale_y, rotation_deg,
/// candidates_evaluated)`; `best_gain` is `f64::NEG_INFINITY` if the grid
/// was empty (callers should treat that as "no candidate").
#[pyfunction]
#[pyo3(signature = (shape_mask, rotationally_symmetric, scales, aspects, rotations, positions,
                     canvas_res, residual, target_mask, overshoot_penalty))]
#[allow(clippy::too_many_arguments)]
fn best_over_grid(
    shape_mask: PyReadonlyArray2<u8>,
    rotationally_symmetric: bool,
    scales: Vec<f64>,
    aspects: Vec<f64>,
    rotations: Vec<f64>,
    positions: Vec<(f64, f64)>,
    canvas_res: usize,
    residual: PyReadonlyArray2<u8>,
    target_mask: PyReadonlyArray2<u8>,
    overshoot_penalty: f64,
) -> (f64, f64, f64, f64, f64, f64, u64) {
    let shape_raster = raster_from_u8(&shape_mask);
    let residual_raster = raster_from_u8(&residual);
    let target_raster = raster_from_u8(&target_mask);

    let mut best_gain = f64::NEG_INFINITY;
    let mut best = (0.0f64, 0.0f64, 0.0f64, 0.0f64, 0.0f64);
    let mut evaluated: u64 = 0;

    for &scale in &scales {
        for &aspect in &aspects {
            let scale_x = scale * aspect;
            let scale_y = scale / aspect;
            for &rot in &rotations {
                let template = build_template(
                    &shape_raster, scale_x, scale_y, rot, 0.0, canvas_res, rotationally_symmetric);
                for &(cx, cy) in &positions {
                    let gain = composite_and_score(
                        &template, cx, cy, canvas_res, &residual_raster, &target_raster, overshoot_penalty);
                    evaluated += 1;
                    if gain > best_gain {
                        best_gain = gain;
                        best = (cx, cy, scale_x, scale_y, rot);
                    }
                }
            }
        }
    }

    (best_gain, best.0, best.1, best.2, best.3, best.4, evaluated)
}

#[pymodule]
fn primitive_fit_rs(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(score_candidate, m)?)?;
    m.add_function(wrap_pyfunction!(best_over_grid, m)?)?;
    Ok(())
}
