from pathlib import Path

from app.core.state import ProjectState


def test_project_state_paths_are_isolated_by_slug(tmp_path: Path) -> None:
    alpha = ProjectState(tmp_path, "alpha")
    beta = ProjectState(tmp_path, "beta")

    assert alpha.events_file == tmp_path / "alpha" / "community-events.jsonl"
    assert alpha.pending_rollups_file == tmp_path / "alpha" / "pending-rollups.json"
    assert alpha.events_file != beta.events_file
    assert alpha.pending_rollups_file != beta.pending_rollups_file


def test_project_state_creates_only_its_own_directory(tmp_path: Path) -> None:
    state = ProjectState(tmp_path, "alpha")

    assert not state.directory.exists()
    state.ensure_directory()

    assert state.directory.is_dir()
    assert not (tmp_path / "beta").exists()
