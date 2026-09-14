"""Where towereye keeps its data: the repo checkout in dev, Application
Support when running as the frozen binary inside the Mac app."""
import os
import sys
from pathlib import Path

APP_NAME = "towereye"


def frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def data_dir() -> Path:
    override = os.environ.get("TOWEREYE_DATA")
    if override:
        return Path(override).expanduser()
    if frozen():
        return Path.home() / "Library" / "Application Support" / APP_NAME
    return Path.cwd()


def templates_dir() -> Path:
    return data_dir() / "templates"


def dataset_dir() -> Path:
    return data_dir() / "dataset"


def pid_file() -> Path:
    return data_dir() / ".towereye-watch.pid"


def log_file() -> Path:
    return data_dir() / ".towereye-watch.log"
