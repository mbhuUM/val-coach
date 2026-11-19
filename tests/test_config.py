from __future__ import annotations

from pathlib import Path

import pytest

from coach import config


def test_rejects_missing_data_dir(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        config.data_dir(tmp_path / "nope")


def test_rejects_data_dir_inside_project(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake_project = tmp_path / "proj"
    data = fake_project / "data"
    (data / "val").mkdir(parents=True)
    (data / "val" / "series.csv").write_text("series_id\n")
    monkeypatch.setattr(config, "PROJECT_ROOT", fake_project)
    with pytest.raises(RuntimeError):
        config.data_dir(data)


def test_accepts_valid_external_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    data = tmp_path / "grid"
    (data / "val").mkdir(parents=True)
    (data / "val" / "series.csv").write_text("series_id\n")
    monkeypatch.setattr(config, "PROJECT_ROOT", tmp_path / "proj")
    assert config.data_dir(data) == data
