# AMD/Intel DirectML Acceleration — Experimental

This backend exists so that GPU-accelerated generation isn't an NVIDIA-only
feature.
Unfortunately, this has never been tested on DirectML hardware, because I do not own any.

## Why it's separate from the CUDA path

The CUDA path (`forza_writer/compute_backend.py`) is a hand-written raw CUDA
C kernel dispatched through CuPy's `RawKernel`. There is no DirectML
equivalent of a raw kernel — DirectML is reached through a framework
(PyTorch via `torch-directml`, or ONNX Runtime via its DirectML execution
provider), and computation has to be expressed as tensor operations, not
arbitrary device code. `DirectMLCandidateScorer` is therefore a genuine
reimplementation of the scoring math, not a port: it pads every registered
template to a common size, gathers a windowed slice of the residual/target
canvases per candidate via batched tensor indexing, and reduces with
`torch.sum`. See the class docstring in `compute_backend.py` for the padding
convention that reproduces the CUDA kernel's out-of-canvas bounds check.

PyTorch was chosen over ONNX Runtime because its imperative style matches
the existing per-layer candidate-batch code shape; ONNX wants a static graph,
which is awkward for the variable-size candidate batches this scoring loop
produces.

## What Can Be Verified:

- The windowed-tensor math is identical to
  `candidate_gain()` (the reference implementation used by the CPU path),
  including candidates placed partly or fully off-canvas in every direction.
  This was checked by running `DirectMLCandidateScorer`'s tensor ops on
  torch's plain CPU device and comparing against existing reference material. No GPU or
  `torch-directml` install required for this check.

## What Has *Not* Been Verified
- Anything about running on an actual DirectML device.
- Unique driver behaviors & other quirks.
- VRAM sizing for the padded-window approach at realistic
  candidate-batch sizes, numerical precision on real hardware, thermal/power
  stability, or whether `torch_directml.device_count()` /
  `torch_directml.device_name()` behave as documented across AMD driver
  versions.

## Boundary

- This backend is never selected by `auto`. `auto` only ever resolves to
  `cuda` or `cpu` — DirectML must be chosen explicitly in Settings.
- Every generation run that resolves to `directml` shows a disclaimer dialog
  (`shell.py`, `_start_generation`) before the worker starts, stating plainly
  that this hasn't been tested on real AMD/DirectML hardware and instructing
  the user to abort on any sign of system instability.
- `torch` / `torch-directml` are optional dependencies (see
  `requirements.txt`). Their absence must never prevent Forza Writer from
  opening or using the CUDA/CPU paths — `directml_info()` catches any import
  or probe failure and reports "unavailable," exactly like `cuda_info()`
  does for a machine without an NVIDIA GPU.

## Gates Before This Stops Being Experimental

1. Someone with real AMD (or Intel) DirectML-capable hardware runs a full
   fontpack generation and compares output against the CPU path — same
   glyph shapes, same placement, not just "it didn't crash."
2. A basic stability pass: a large generation job (500+ glyphs) completes
   without driver resets, TDR timeouts, or visible slowdown/hang.
3. Memory profiling at realistic candidate-batch sizes. The padded-window
   approach in `DirectMLCandidateScorer.score()` is not memory-optimal — it
   pads every canvas by one full template's worth of border and gathers a
   dense window per candidate rather than sharing overlapping reads. That
   was an acceptable simplification for a correctness-first first pass, but
   it should be measured against actual VRAM budgets before this is anything
   but opt-in.
4. Only after (1)-(3): promote from "explicit opt-in with a warning dialog"
   to a real menu item without the disclaimer, and consider whether `auto`
   should ever prefer it (e.g., on a machine with no NVIDIA GPU at all).

If enough people give it a try and it doesn't seem to make a meaningful difference, then
it is what it is.
