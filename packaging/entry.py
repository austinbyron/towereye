"""PyInstaller entry point: the same CLI as `python -m towereye`."""
import multiprocessing
import sys

from towereye.cli import main

if __name__ == "__main__":
    multiprocessing.freeze_support()
    sys.exit(main())
