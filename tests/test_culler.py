from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from photopicker.culler import CullResult, cull


def _distinct_folder(root: Path, count: int, size: tuple[int, int] = (900, 900)) -> Path:
    folder = root / "shoot"
    folder.mkdir()
    h, w = size
    for i in range(count):
        arr = np.full((h, w, 3), 128, dtype=np.uint8)
        # Sharpen: unique quadrant + shifting checkerboard so composite score varies.
        row_off = (i * 90) % h
        col_off = (i * 71) % w
        arr[row_off : row_off + 200, col_off : col_off + 200] = 255
        for r in range(0, h, 32):
            for c in range(0, w, 32):
                if (r // 32 + c // 32) % 2 == 0:
                    arr[r : r + 16, c : c + 16] = min(255, 200 + i * 5)
        Image.fromarray(arr).save(folder / f"img_{i:02d}.png")
    return folder


def _sorted_by_name(folder: Path) -> list[Path]:
    return sorted(p for p in folder.iterdir() if p.suffix.lower() == ".png")


def test_cull_returns_top_n_from_folder(tmp_path: Path):
    folder = _distinct_folder(tmp_path, 20)
    paths = _sorted_by_name(folder)

    result = cull(paths, top_n=5)

    assert isinstance(result, CullResult)
    assert len(result.keepers) == 5
    # All keepers are real, distinct paths.
    assert len(set(result.keepers)) == 5
    for p in result.keepers:
        assert p.exists()
        assert p in paths
    # Scores stored for every keeper.
    assert set(result.scores.keys()) == set(result.keepers)


def test_cull_rejects_blurry_images(tmp_path: Path):
    folder = tmp_path / "shoot"
    folder.mkdir()
    # 5 sharp checkers
    for i in range(5):
        arr = np.full((900, 900, 3), 128, dtype=np.uint8)
        for r in range(0, 900, 16):
            for c in range(0, 900, 16):
                if (r // 16 + c // 16) % 2 == 0:
                    arr[r : r + 16, c : c + 16] = 255
        Image.fromarray(arr).save(folder / f"sharp_{i}.png")
    # 5 dead-flat solids (very low Laplacian variance → blurry)
    for i in range(5):
        arr = np.full((900, 900, 3), 128, dtype=np.uint8)
        Image.fromarray(arr).save(folder / f"flat_{i}.png")

    result = cull(_sorted_by_name(folder), top_n=5)

    # Sharp survives, flat is either blurry-rejected or scored below sharp.
    for p in result.keepers:
        assert p.name.startswith("sharp_")


def test_cull_reject_counts_reports_reasons(tmp_path: Path):
    folder = tmp_path / "shoot"
    folder.mkdir()
    # 1 too-small (unique content so dedup doesn't eat it first)
    arr = np.full((300, 300, 3), 200, dtype=np.uint8)
    arr[50:100, :] = 40
    for r in range(0, 300, 16):
        for c in range(0, 300, 16):
            if (r // 16 + c // 16) % 2 == 0:
                arr[r : r + 16, c : c + 16] = 255
    Image.fromarray(arr).save(folder / "tiny_unique.png")
    # 5 sharp large
    for i in range(5):
        arr = np.full((900, 900, 3), 128, dtype=np.uint8)
        row_off = (i * 100) % 900
        arr[row_off : row_off + 100, :] = 255
        for r in range(0, 900, 16):
            for c in range(0, 900, 16):
                if (r // 16 + c // 16) % 2 == 0:
                    arr[r : r + 16, c : c + 16] = min(255, 200 + i * 5)
        Image.fromarray(arr).save(folder / f"big_{i}.png")

    result = cull(_sorted_by_name(folder), top_n=5)

    # The tiny file is rejected somewhere in the pipeline — either dedup
    # (near-duplicate collapse) or quality gate (too_small). Either lands it
    # out of the keepers.
    all_reject_paths: list[str] = []
    for reason_paths in result.rejected.values():
        all_reject_paths.extend(p.name for p in reason_paths)
    assert "tiny_unique.png" in all_reject_paths
    for i in range(5):
        assert any(p.name == f"big_{i}.png" for p in result.keepers)


def test_cull_empty_input_returns_empty_result():
    result = cull([], top_n=10)
    assert result.keepers == []
    assert result.scores == {}
    assert result.total_input == 0


def test_cull_progress_callback_fires_for_each_stage(tmp_path: Path):
    folder = _distinct_folder(tmp_path, 10)
    stages_seen: list[str] = []

    def progress(stage: str, done: int, total: int) -> None:
        stages_seen.append(stage)

    cull(_sorted_by_name(folder), top_n=3, progress=progress)

    for stage in ("dedup", "quality-gate", "scoring"):
        assert stage in stages_seen


def test_cull_summary_lists_ranked_keepers(tmp_path: Path):
    folder = _distinct_folder(tmp_path, 8)
    result = cull(_sorted_by_name(folder), top_n=3)

    summary = result.summary()
    assert "Culled" in summary
    assert "Top keepers" in summary
    for p in result.keepers:
        assert p.name in summary


def test_cull_keepers_are_ordered_by_score_desc(tmp_path: Path):
    folder = _distinct_folder(tmp_path, 12)
    result = cull(_sorted_by_name(folder), top_n=6)

    scores = [result.scores[p] for p in result.keepers]
    assert scores == sorted(scores, reverse=True)


def test_cull_top_n_larger_than_input_returns_all_survivors(tmp_path: Path):
    folder = _distinct_folder(tmp_path, 5)
    result = cull(_sorted_by_name(folder), top_n=100)

    assert len(result.keepers) <= 5
    assert len(result.keepers) == len(set(result.keepers))


def test_cull_total_input_matches_paths(tmp_path: Path):
    folder = _distinct_folder(tmp_path, 10)
    result = cull(_sorted_by_name(folder), top_n=3)

    assert result.total_input == 10


def test_cull_result_reject_counts_hide_empty_reasons(tmp_path: Path):
    folder = _distinct_folder(tmp_path, 6)
    result = cull(_sorted_by_name(folder), top_n=6)

    for _reason, count in result.reject_counts().items():
        assert count > 0


def test_cull_sort_name_orders_by_filename(tmp_path: Path):
    folder = _distinct_folder(tmp_path, 8)
    result = cull(_sorted_by_name(folder), top_n=5, sort="name")

    names = [p.name for p in result.keepers]
    assert names == sorted(names)


def test_cull_sort_score_default_is_desc(tmp_path: Path):
    folder = _distinct_folder(tmp_path, 10)
    result = cull(_sorted_by_name(folder), top_n=4)

    scores = [result.scores[p] for p in result.keepers]
    assert scores == sorted(scores, reverse=True)


def test_cull_sort_invalid_raises():
    import pytest
    with pytest.raises(ValueError):
        cull([], top_n=3, sort="alphabetical")


def test_cull_sharpest_per_cluster_wins(tmp_path: Path):
    """Score-then-dedup: within a near-dup cluster, the sharpest survives.

    Build a cluster of 3 near-identical photos by taking the same base image
    and applying progressively stronger Gaussian blur to two of them. All 3
    hash to the same average-hash bucket (same lighting distribution) but
    only one is sharp.
    """
    from PIL import ImageFilter

    folder = tmp_path / "cluster"
    folder.mkdir()

    arr = np.full((900, 900, 3), 128, dtype=np.uint8)
    for r in range(0, 900, 16):
        for c in range(0, 900, 16):
            if (r // 16 + c // 16) % 2 == 0:
                arr[r : r + 16, c : c + 16] = 255
    base = Image.fromarray(arr)

    base.save(folder / "cluster_sharp.png")
    base.filter(ImageFilter.GaussianBlur(radius=4)).save(folder / "cluster_blur_a.png")
    base.filter(ImageFilter.GaussianBlur(radius=6)).save(folder / "cluster_blur_b.png")

    result = cull(_sorted_by_name(folder), top_n=3)

    # Every survivor should be from this cluster, and the sharp one must be
    # in the top slot (sharpest wins score, blurs are dedup dropouts).
    assert result.keepers[0].name == "cluster_sharp.png"


def test_cull_clusters_and_all_scores_keep_public_scores_keepers_only(tmp_path: Path):
    """Burst members must never leak into `result.scores` (the public,
    keepers-only contract) but must still be reachable via `all_scores` so a
    reviewer can see a cluster loser's score without it being a keeper."""
    from PIL import ImageFilter

    folder = tmp_path / "cluster"
    folder.mkdir()

    arr = np.full((900, 900, 3), 128, dtype=np.uint8)
    for r in range(0, 900, 16):
        for c in range(0, 900, 16):
            if (r // 16 + c // 16) % 2 == 0:
                arr[r : r + 16, c : c + 16] = 255
    base = Image.fromarray(arr)

    base.save(folder / "cluster_sharp.png")
    base.filter(ImageFilter.GaussianBlur(radius=4)).save(folder / "cluster_blur_a.png")
    base.filter(ImageFilter.GaussianBlur(radius=6)).save(folder / "cluster_blur_b.png")

    result = cull(_sorted_by_name(folder), top_n=3)

    sharp = folder / "cluster_sharp.png"
    blur_a = folder / "cluster_blur_a.png"
    blur_b = folder / "cluster_blur_b.png"

    # The blurred frames lost the dedup and are not keepers.
    assert blur_a not in result.keepers
    assert blur_b not in result.keepers
    # Public contract: scores holds exactly the keepers, nothing else.
    assert set(result.scores.keys()) == set(result.keepers)
    # Cluster map records the winner -> losers relationship.
    assert result.clusters.get(sharp) == [blur_a, blur_b]
    # But their scores are still visible via all_scores for burst review.
    assert blur_a in result.all_scores
    assert blur_b in result.all_scores
    assert sharp in result.all_scores


def test_cull_all_rejected_dedupes_paths(tmp_path: Path):
    folder = _distinct_folder(tmp_path, 10)
    result = cull(_sorted_by_name(folder), top_n=3)

    all_rej = result.all_rejected()
    assert len(all_rej) == len(set(all_rej))


def test_cull_progress_reports_new_twin_collapse_stage(tmp_path: Path):
    folder = _distinct_folder(tmp_path, 6)
    stages = []
    cull(
        _sorted_by_name(folder), top_n=3,
        progress=lambda s, d, t: stages.append(s),
    )
    assert "twin-collapse" in stages
    assert "scoring" in stages
    assert "dedup" in stages
    assert "quality-gate" in stages
