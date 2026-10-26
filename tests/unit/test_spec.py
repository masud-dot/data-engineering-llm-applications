from pathlib import Path

import pytest

from llmdata.pipeline import spec

ROOT = Path("pipelines")


@pytest.mark.chapter(3)
def test_skeleton_pipeline_has_one_stage() -> None:
    stages = spec.load(ROOT, "documents", "ch03")
    assert [s.name for s in stages] == ["00-smoke"]


@pytest.mark.chapter(11)
def test_overlay_replaces_params_but_keeps_chapter() -> None:
    ingest = {s.name: s for s in spec.load(ROOT, "documents", "ch11")}
    stage = ingest["10-ingest"]
    assert stage.chapter == 4
    assert stage.params["source"].endswith("WatermarkSource")


@pytest.mark.chapter(12)
def test_policies_follow_until() -> None:
    assert spec.policy(ROOT, "ch11").retries == 0
    assert spec.policy(ROOT, "ch12").retries == 2


def test_overlay_files_sort_after_their_base(tmp_path: Path) -> None:
    folder = tmp_path / "p"
    folder.mkdir()
    (folder / "10-a.toml").write_text(
        'chapter = 4\ncallable = "m:f"\nparams.x = 1\n'
    )
    (folder / "10-a+late.toml").write_text(
        "chapter = 9\nparams.x = 2\n"
    )
    assert spec.load(tmp_path, "p")[0].params == {"x": 2}
    assert spec.load(tmp_path, "p", "ch08")[0].params == {"x": 1}
