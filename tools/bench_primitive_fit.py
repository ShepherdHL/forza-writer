"""Repeatable CPU-generation benchmark for `forza_writer.primitive_fit`.

This is Gate 1 of `docs/RUST_CPU_ACCELERATION.md`: a baseline measurement
taken *before* any Rust kernel exists, so later work has something concrete
to beat. Run it, save the JSON, and diff future runs against it — a Rust
port only clears the gate if it matches `mask_sha256`/`shapes_sha256`
exactly and meaningfully improves `elapsed_seconds` end-to-end (not just in
a microbenchmark), per the doc's gate 3/4.

Usage:
    python tools/bench_primitive_fit.py [--out bench_baseline.json]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import tracemalloc
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
if str(_ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(_ROOT / "tools"))

from gen_modelbin import extract_contours, normalize_to_128  # noqa: E402

from forza_writer.generation_policy import GenerationStats  # noqa: E402
from forza_writer.primitive_fit import (  # noqa: E402
    DEFAULT_RESOLUTION,
    fit_placements,
    rasterize_contours,
)

LATIN_FONT = _ROOT / "assets" / "fonts" / "LiberationSans-Regular.ttf"
CJK_FONT = _ROOT / "assets" / "fonts" / "NotoSansCJKjp-Regular.otf"

# Representative inputs per docs/RUST_CPU_ACCELERATION.md gate 1: Latin,
# CJK, curved, and high-layer-count cases. "H"/"B" are rectilinear-ish
# baselines (mostly routed to the exact rect_decompose path, not the
# primitive search); "O"/"S" force the curved greedy search; the CJK
# characters and "@" are the highest-detail/most-candidates cases, standing
# in for "high-layer-count" since no bundled font reliably needs many
# primitive layers on plain Latin letters.
CASES: list[tuple[str, Path, str]] = [
    ("latin_H", LATIN_FONT, "H"),
    ("latin_B", LATIN_FONT, "B"),
    ("latin_O_curved", LATIN_FONT, "O"),
    ("latin_S_curved", LATIN_FONT, "S"),
    ("latin_at_high_detail", LATIN_FONT, "@"),
    ("cjk_kanji_simple", CJK_FONT, "一"),  # 一 (one stroke)
    ("cjk_kanji_complex", CJK_FONT, "龍"),  # 龍 (dragon, high stroke count)
    ("cjk_hiragana_curved", CJK_FONT, "あ"),  # あ
]


def _sha256_of(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()


def run_case(name: str, font_path: Path, char: str, resolution: int = DEFAULT_RESOLUTION) -> dict:
    if not font_path.exists():
        return {"case": name, "skipped": f"font not found: {font_path}"}

    contours, upm = extract_contours(char, font_path, curve_segments=8)
    contours_norm = normalize_to_128(contours, upm)
    target_mask = rasterize_contours(contours_norm, resolution)
    mask_hash = hashlib.sha256(target_mask.tobytes()).hexdigest()

    stats = GenerationStats()
    tracemalloc.start()
    t0 = time.perf_counter()
    placements, strategy = fit_placements(
        contours_norm, resolution=resolution, compute_backend="cpu", stats=stats)
    elapsed = time.perf_counter() - t0
    _current, peak_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    shapes_repr = [
        (p.shape_id, round(p.cx, 3), round(p.cy, 3), round(p.scale_x, 3),
         round(p.scale_y, 3), round(p.rotation_deg, 3), round(p.skew_x, 3), p.is_mask)
        for p in placements
    ]

    return {
        "case": name,
        "char": char,
        "strategy": strategy,
        "elapsed_seconds": elapsed,
        "stats_elapsed_seconds": stats.elapsed_seconds,
        "candidates_tested": stats.candidates_tested,
        "candidates_rejected": stats.candidates_rejected,
        "shapes_placed": len(placements),
        "iou": stats.iou,
        "peak_memory_bytes": peak_bytes,
        "mask_sha256": mask_hash,
        "shapes_sha256": _sha256_of(shapes_repr),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=_ROOT / "tools" / "bench_baseline.json")
    parser.add_argument("--resolution", type=int, default=DEFAULT_RESOLUTION)
    args = parser.parse_args()

    results = [run_case(name, font, char, args.resolution) for name, font, char in CASES]

    for r in results:
        if r.get("skipped"):
            print(f"  SKIP {r['case']}: {r['skipped']}")
            continue
        print(f"  {r['case']:24s} strategy={r['strategy']:16s} "
              f"time={r['elapsed_seconds']*1000:8.1f}ms candidates={r['candidates_tested']:6d} "
              f"shapes={r['shapes_placed']:3d} iou={r['iou']:.3f} "
              f"peak_mem={r['peak_memory_bytes']/1e6:6.2f}MB")

    payload = {"resolution": args.resolution, "results": results}
    args.out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"\nWrote {args.out}")


if __name__ == "__main__":
    main()
