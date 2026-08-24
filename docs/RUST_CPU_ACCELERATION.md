# Rust CPU Acceleration Plan

Rust should be introduced as an optional, measured acceleration layer—not as
a rewrite of Forza Writer or its Python orchestration.

## Boundary

- Keep the GUI, settings, file routing, font discovery, and generation policy
  in Python.
- Keep the existing CUDA/CuPy path. Rust does not make an already-GPU-bound
  kernel faster, although it may later reduce CPU preparation overhead.
- Move only CPU kernels whose profiles show substantial time in Python loops
  or repeatedly allocated temporary arrays.
- Preserve the Python implementation as a compatibility fallback initially.

## Candidate order

1. Candidate scoring and mask/coverage comparison in `primitive_fit.py`.
2. Raster and rectangle-processing loops used by pixel/image tracing.
3. Contour and geometry preparation where profiling shows Python overhead.
4. Modelbin serialization only if benchmarks show it is material; file writes
   are unlikely to be the main bottleneck.

## Integration

- Build a Python extension with PyO3 and maturin.
- Exchange NumPy-compatible buffers without per-element Python conversion.
- Select the Rust implementation only for CPU generation; retain the current
  CUDA dispatch and public Python APIs.
- Package wheels for supported Windows/Python versions. A missing extension
  must produce a clear fallback status, not prevent Forza Writer from opening.

## Gates

1. Add repeatable benchmarks for representative Latin, CJK, curved, and
   high-layer-count inputs.
2. Record current CPU time, candidate count, memory use, and output hashes.
3. Port one isolated kernel.
4. Require output/accuracy parity plus a meaningful end-to-end speedup—not
   merely a faster microbenchmark whose gains disappear at the Python boundary.
5. Expand only after the first kernel proves that packaging and maintenance
   costs are justified.

The first target should ideally improve CPU generation for users without CUDA
while leaving GPU users and existing integrations behaviorally unchanged.
