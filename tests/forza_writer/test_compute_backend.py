import numpy as np
import pytest

from forza_writer import compute_backend
from forza_writer.primitive_fit import (
    PRIMITIVE_CATALOG, _candidate_image, candidate_gain, render_candidate)


def test_explicit_cpu_never_requires_cuda():
    info = compute_backend.resolve_backend("cpu")
    assert info.available is True
    assert info.resolved == "cpu"
    assert info.device == "CPU"


def test_auto_falls_back_to_cpu_when_cuda_is_unavailable(monkeypatch):
    monkeypatch.setattr(
        compute_backend, "cuda_info",
        lambda: compute_backend.BackendInfo(
            "cuda", "cpu", False, detail="test CUDA failure"))
    info = compute_backend.resolve_backend("auto")
    assert info.available is True
    assert info.resolved == "cpu"
    assert "test CUDA failure" in info.detail


def test_auto_never_selects_directml_even_when_available(monkeypatch):
    # DirectML is experimental and must be chosen explicitly (the GUI warns
    # the user every time it's used); 'auto' should never surface it, even
    # if a DirectML device happens to be present and CUDA is not.
    monkeypatch.setattr(
        compute_backend, "cuda_info",
        lambda: compute_backend.BackendInfo("cuda", "cpu", False, detail="no CUDA"))
    monkeypatch.setattr(
        compute_backend, "directml_info",
        lambda: compute_backend.BackendInfo("directml", "directml", True, "Fake AMD GPU", "ok"))
    info = compute_backend.resolve_backend("auto")
    assert info.resolved == "cpu"


def test_explicit_directml_falls_back_to_cpu_when_unavailable(monkeypatch):
    monkeypatch.setattr(
        compute_backend, "directml_info",
        lambda: compute_backend.BackendInfo(
            "directml", "cpu", False, detail="test DirectML failure"))
    info = compute_backend.resolve_backend("directml")
    assert info.available is False
    assert info.resolved == "cpu"
    assert "test DirectML failure" in info.detail


def test_directml_batch_scores_match_cpu_candidate_gain():
    info = compute_backend.directml_info()
    if not info.available:
        pytest.skip(info.detail)

    resolution = 64
    target = np.zeros((resolution, resolution), dtype=bool)
    target[9:46, 14:51] = True
    residual = target.copy()
    scorer = compute_backend.DirectMLCandidateScorer(resolution)
    template_ids, xs, ys, expected = [], [], [], []

    for shape_id, cx, cy, sx, sy, rotation in (
            ("circle", 20, 20, 0.25, 0.25, 0),
            ("square", 32, 32, 0.5, 0.35, 30),
            ("triangle", 53, 50, 0.75, 0.5, 45)):
        shape = PRIMITIVE_CATALOG[shape_id]
        template = _candidate_image(shape, sx, sy, rotation, resolution)
        template_ids.append(scorer.template_id((shape_id, sx, sy, rotation), template))
        xs.append(round(cx - template.shape[1] / 2))
        ys.append(round(cy - template.shape[0] / 2))
        mask = render_candidate(shape, cx, cy, sx, sy, rotation, resolution)
        expected.append(candidate_gain(mask, residual, target, 0.35))

    actual = scorer.score(template_ids, xs, ys, residual, target, 0.35)
    np.testing.assert_allclose(actual, expected, rtol=0, atol=2e-4)


def test_cuda_batch_scores_match_cpu_candidate_gain():
    info = compute_backend.cuda_info()
    if not info.available:
        pytest.skip(info.detail)

    resolution = 64
    target = np.zeros((resolution, resolution), dtype=bool)
    target[9:46, 14:51] = True
    residual = target.copy()
    scorer = compute_backend.CudaCandidateScorer(resolution)
    template_ids, xs, ys, expected = [], [], [], []

    for shape_id, cx, cy, sx, sy, rotation in (
            ("circle", 20, 20, 0.25, 0.25, 0),
            ("square", 32, 32, 0.5, 0.35, 30),
            ("triangle", 53, 50, 0.75, 0.5, 45)):
        shape = PRIMITIVE_CATALOG[shape_id]
        template = _candidate_image(shape, sx, sy, rotation, resolution)
        template_ids.append(scorer.template_id((shape_id, sx, sy, rotation), template))
        xs.append(round(cx - template.shape[1] / 2))
        ys.append(round(cy - template.shape[0] / 2))
        mask = render_candidate(shape, cx, cy, sx, sy, rotation, resolution)
        expected.append(candidate_gain(mask, residual, target, 0.35))

    actual = scorer.score(template_ids, xs, ys, residual, target, 0.35)
    np.testing.assert_allclose(actual, expected, rtol=0, atol=2e-4)
