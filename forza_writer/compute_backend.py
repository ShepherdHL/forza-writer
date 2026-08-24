"""Compute-backend discovery and CUDA batch scoring for primitive fitting.

The CUDA path deliberately accelerates the hot operation only: scoring a
large portfolio of already-rasterized primitive candidates.  Pillow creates
each unique (shape, scale, aspect, rotation) template once; CUDA then places
and scores thousands of those templates concurrently without transferring
candidate masks back to the CPU.
"""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal

import numpy as np

BackendChoice = Literal["auto", "cuda", "directml", "cpu"]


@dataclass(frozen=True)
class BackendInfo:
    requested: str
    resolved: str
    available: bool
    device: str = ""
    detail: str = ""


def _prepare_cupy_cache() -> None:
    if "CUPY_CACHE_DIR" not in os.environ:
        root = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "forza-writer" / "cupy-cache"
        os.environ["CUPY_CACHE_DIR"] = str(root)


@lru_cache(maxsize=1)
def cuda_info() -> BackendInfo:
    try:
        _prepare_cupy_cache()
        import cupy as cp
        count = cp.cuda.runtime.getDeviceCount()
        if count < 1:
            return BackendInfo("cuda", "cpu", False, detail="no CUDA device detected")
        best = max(range(count), key=lambda i: cp.cuda.runtime.getDeviceProperties(i)["totalGlobalMem"])
        props = cp.cuda.runtime.getDeviceProperties(best)
        name = props["name"].decode(errors="replace")
        with cp.cuda.Device(best):
            cp.asarray([1], dtype=cp.int32).sum().get()
        return BackendInfo("cuda", "cuda", True, name,
                           f"CUDA device {best}; {props['totalGlobalMem'] / (1024 ** 3):.1f} GB VRAM")
    except Exception as exc:
        return BackendInfo("cuda", "cpu", False, detail=f"CUDA unavailable: {exc}")


@lru_cache(maxsize=1)
def directml_info() -> BackendInfo:
    """Probe for an AMD/Intel/NVIDIA GPU reachable through DirectML.

    Experimental: never selected by 'auto'. Unlike the CUDA path, this has
    not been run against real DirectML hardware (see
    docs/DIRECTML_ACCELERATION.md) — it must be chosen explicitly, and the
    GUI shows a disclaimer before every generation run that uses it.
    """
    try:
        import torch  # noqa: F401 (import error here means "unavailable", not a real dependency use)
        import torch_directml
        count = torch_directml.device_count()
        if count < 1:
            return BackendInfo("directml", "cpu", False, detail="no DirectML device detected")
        name = torch_directml.device_name(0)
        return BackendInfo("directml", "directml", True, name, f"DirectML device 0 of {count}")
    except Exception as exc:
        return BackendInfo("directml", "cpu", False, detail=f"DirectML unavailable: {exc}")


def resolve_backend(requested: BackendChoice = "auto") -> BackendInfo:
    if requested not in ("auto", "cuda", "directml", "cpu"):
        raise ValueError(f"unknown compute backend: {requested!r}")
    if requested == "cpu":
        return BackendInfo("cpu", "cpu", True, "CPU", "explicit CPU selection")
    if requested == "directml":
        info = directml_info()
        if info.available:
            return BackendInfo("directml", "directml", True, info.device, info.detail)
        return BackendInfo("directml", "cpu", False, detail=info.detail)
    info = cuda_info()
    if info.available:
        return BackendInfo(requested, "cuda", True, info.device, info.detail)
    if requested == "cuda":
        return BackendInfo("cuda", "cpu", False, detail=info.detail)
    return BackendInfo("auto", "cpu", True, "CPU", info.detail)


_SCORE_KERNEL = r'''
extern "C" __global__
void score_candidates(
    const unsigned char* templates,
    const int* offsets,
    const int* widths,
    const int* heights,
    const int* candidate_template,
    const int* candidate_x,
    const int* candidate_y,
    const unsigned char* residual,
    const unsigned char* target,
    const int resolution,
    const float overshoot_penalty,
    float* gains)
{
    int candidate = blockIdx.x;
    int tid = threadIdx.x;
    int template_id = candidate_template[candidate];
    int width = widths[template_id];
    int height = heights[template_id];
    int offset = offsets[template_id];
    int px = candidate_x[candidate];
    int py = candidate_y[candidate];
    int local_new = 0;
    int local_over = 0;
    for (int p = tid; p < width * height; p += blockDim.x) {
        if (!templates[offset + p]) continue;
        int lx = p % width;
        int ly = p / width;
        int x = px + lx;
        int y = py + ly;
        if (x < 0 || y < 0 || x >= resolution || y >= resolution) continue;
        int canvas = y * resolution + x;
        local_new += residual[canvas] ? 1 : 0;
        local_over += target[canvas] ? 0 : 1;
    }
    __shared__ int new_sum[256];
    __shared__ int over_sum[256];
    new_sum[tid] = local_new;
    over_sum[tid] = local_over;
    __syncthreads();
    for (int stride = blockDim.x / 2; stride > 0; stride >>= 1) {
        if (tid < stride) {
            new_sum[tid] += new_sum[tid + stride];
            over_sum[tid] += over_sum[tid + stride];
        }
        __syncthreads();
    }
    if (tid == 0) gains[candidate] = (float)new_sum[0] - overshoot_penalty * (float)over_sum[0];
}
'''


class CudaCandidateScorer:
    """Persistent per-resolution CUDA scorer with exact Pillow templates."""

    def __init__(self, resolution: int):
        _prepare_cupy_cache()
        import cupy as cp
        self.cp = cp
        self.resolution = resolution
        self.kernel = cp.RawKernel(_SCORE_KERNEL, "score_candidates")
        self._template_keys: dict[tuple, int] = {}
        self._templates: list[np.ndarray] = []
        self._gpu_templates = None
        self._lock = threading.RLock()

    def template_id(self, key: tuple, mask: np.ndarray) -> int:
        with self._lock:
            existing = self._template_keys.get(key)
            if existing is not None:
                return existing
            idx = len(self._templates)
            self._template_keys[key] = idx
            self._templates.append(np.ascontiguousarray(mask, dtype=np.uint8))
            self._gpu_templates = None
            return idx

    def get_or_create_template(self, key: tuple, factory) -> tuple[int, tuple[int, int]]:
        with self._lock:
            template_id = self._template_keys.get(key)
            if template_id is None:
                template_id = self.template_id(key, factory())
            return template_id, self._templates[template_id].shape

    def find_template(self, key: tuple) -> int | None:
        return self._template_keys.get(key)

    def template_shape(self, template_id: int) -> tuple[int, int]:
        return self._templates[template_id].shape

    def _upload_templates(self):
        cp = self.cp
        offsets, widths, heights, flat = [], [], [], []
        cursor = 0
        for mask in self._templates:
            offsets.append(cursor)
            heights.append(mask.shape[0])
            widths.append(mask.shape[1])
            values = mask.ravel()
            flat.append(values)
            cursor += values.size
        self._gpu_templates = (
            cp.asarray(np.concatenate(flat), dtype=cp.uint8),
            cp.asarray(offsets, dtype=cp.int32),
            cp.asarray(widths, dtype=cp.int32),
            cp.asarray(heights, dtype=cp.int32),
        )

    def score(self, template_ids: list[int], xs: list[int], ys: list[int],
              residual: np.ndarray, target: np.ndarray, overshoot_penalty: float) -> np.ndarray:
        with self._lock:
            if self._gpu_templates is None:
                self._upload_templates()
            cp = self.cp
            templates, offsets, widths, heights = self._gpu_templates
            ids_gpu = cp.asarray(template_ids, dtype=cp.int32)
            xs_gpu = cp.asarray(xs, dtype=cp.int32)
            ys_gpu = cp.asarray(ys, dtype=cp.int32)
            residual_gpu = cp.asarray(np.ascontiguousarray(residual, dtype=np.uint8))
            target_gpu = cp.asarray(np.ascontiguousarray(target, dtype=np.uint8))
            gains = cp.empty(len(template_ids), dtype=cp.float32)
            self.kernel((len(template_ids),), (256,), (
                templates, offsets, widths, heights, ids_gpu, xs_gpu, ys_gpu,
                residual_gpu, target_gpu, np.int32(self.resolution), np.float32(overshoot_penalty), gains))
            return cp.asnumpy(gains)


_CUDA_SCORERS: dict[int, CudaCandidateScorer] = {}


def cuda_scorer(resolution: int) -> CudaCandidateScorer:
    scorer = _CUDA_SCORERS.get(resolution)
    if scorer is None:
        scorer = CudaCandidateScorer(resolution)
        _CUDA_SCORERS[resolution] = scorer
    return scorer


class DirectMLCandidateScorer:
    """Persistent per-resolution DirectML scorer — same interface and same
    reward/overshoot math as CudaCandidateScorer, expressed as batched torch
    tensor ops instead of a raw kernel (DirectML has no RawKernel equivalent).

    EXPERIMENTAL: written without access to AMD/DirectML hardware. The math
    has been checked by running these tensor ops on torch's CPU backend and
    comparing against candidate_gain() in primitive_fit.py, but nothing here
    has executed on real DirectML silicon. See docs/DIRECTML_ACCELERATION.md.
    """

    def __init__(self, resolution: int):
        import torch
        import torch_directml
        self.torch = torch
        self.device = torch_directml.device()
        self.resolution = resolution
        self._template_keys: dict[tuple, int] = {}
        self._templates: list[np.ndarray] = []
        self._gpu_templates = None  # (templates[T,Hmax,Wmax] bool, Hmax, Wmax)
        self._lock = threading.RLock()

    def template_id(self, key: tuple, mask: np.ndarray) -> int:
        with self._lock:
            existing = self._template_keys.get(key)
            if existing is not None:
                return existing
            idx = len(self._templates)
            self._template_keys[key] = idx
            self._templates.append(np.ascontiguousarray(mask, dtype=bool))
            self._gpu_templates = None
            return idx

    def get_or_create_template(self, key: tuple, factory) -> tuple[int, tuple[int, int]]:
        with self._lock:
            template_id = self._template_keys.get(key)
            if template_id is None:
                template_id = self.template_id(key, factory())
            return template_id, self._templates[template_id].shape

    def find_template(self, key: tuple) -> int | None:
        return self._template_keys.get(key)

    def template_shape(self, template_id: int) -> tuple[int, int]:
        return self._templates[template_id].shape

    def _upload_templates(self):
        torch = self.torch
        h_max = max(mask.shape[0] for mask in self._templates)
        w_max = max(mask.shape[1] for mask in self._templates)
        padded = np.zeros((len(self._templates), h_max, w_max), dtype=bool)
        for i, mask in enumerate(self._templates):
            h, w = mask.shape
            padded[i, :h, :w] = mask
        templates = torch.from_numpy(padded).to(self.device)
        self._gpu_templates = (templates, h_max, w_max)

    def score(self, template_ids: list[int], xs: list[int], ys: list[int],
              residual: np.ndarray, target: np.ndarray, overshoot_penalty: float) -> np.ndarray:
        with self._lock:
            if self._gpu_templates is None:
                self._upload_templates()
            torch = self.torch
            device = self.device
            templates, h_max, w_max = self._gpu_templates
            n = len(template_ids)
            if n == 0:
                return np.empty(0, dtype=np.float32)

            # Pad the canvases by one template's worth of border on every side
            # so every candidate window is a plain in-bounds slice. Padding
            # residual with False (never scores as "new coverage") and target
            # with True (never scores as "overshoot") reproduces the raw
            # kernel's per-pixel bounds check, which simply skips out-of-
            # canvas pixels rather than penalizing or rewarding them.
            pad_h, pad_w = h_max, w_max
            residual_pad = torch.zeros((self.resolution + 2 * pad_h, self.resolution + 2 * pad_w),
                                        dtype=torch.bool, device=device)
            residual_pad[pad_h:pad_h + self.resolution, pad_w:pad_w + self.resolution] = \
                torch.from_numpy(np.ascontiguousarray(residual, dtype=bool)).to(device)
            target_pad = torch.ones((self.resolution + 2 * pad_h, self.resolution + 2 * pad_w),
                                     dtype=torch.bool, device=device)
            target_pad[pad_h:pad_h + self.resolution, pad_w:pad_w + self.resolution] = \
                torch.from_numpy(np.ascontiguousarray(target, dtype=bool)).to(device)

            ids_t = torch.as_tensor(template_ids, dtype=torch.long, device=device)
            py = torch.as_tensor(ys, dtype=torch.long, device=device) + pad_h
            px = torch.as_tensor(xs, dtype=torch.long, device=device) + pad_w
            rows = py.unsqueeze(1) + torch.arange(h_max, device=device).unsqueeze(0)  # (n, h_max)
            cols = px.unsqueeze(1) + torch.arange(w_max, device=device).unsqueeze(0)  # (n, w_max)
            row_idx = rows.unsqueeze(2).expand(n, h_max, w_max)
            col_idx = cols.unsqueeze(1).expand(n, h_max, w_max)

            residual_windows = residual_pad[row_idx, col_idx]
            target_windows = target_pad[row_idx, col_idx]
            template_windows = templates[ids_t]

            new_coverage = (residual_windows & template_windows).sum(dim=(1, 2))
            overshoot = ((~target_windows) & template_windows).sum(dim=(1, 2))
            gains = new_coverage.to(torch.float32) - overshoot_penalty * overshoot.to(torch.float32)
            return gains.cpu().numpy()


_DIRECTML_SCORERS: dict[int, DirectMLCandidateScorer] = {}


def directml_scorer(resolution: int) -> DirectMLCandidateScorer:
    scorer = _DIRECTML_SCORERS.get(resolution)
    if scorer is None:
        scorer = DirectMLCandidateScorer(resolution)
        _DIRECTML_SCORERS[resolution] = scorer
    return scorer
