import sys
from pathlib import Path

from towereye import paths


def test_dev_defaults_to_cwd(monkeypatch, tmp_path):
    monkeypatch.delenv("TOWEREYE_DATA", raising=False)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    assert paths.data_dir() == tmp_path
    assert paths.templates_dir() == tmp_path / "templates"
    assert paths.dataset_dir() == tmp_path / "dataset"
    assert paths.pid_file().name == ".towereye-watch.pid"
    assert paths.log_file().name == ".towereye-watch.log"


def test_frozen_uses_application_support(monkeypatch):
    monkeypatch.delenv("TOWEREYE_DATA", raising=False)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert paths.data_dir() == Path.home() / "Library" / "Application Support" / "towereye"


def test_env_override_wins(monkeypatch, tmp_path):
    monkeypatch.setenv("TOWEREYE_DATA", str(tmp_path / "x"))
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert paths.data_dir() == tmp_path / "x"
