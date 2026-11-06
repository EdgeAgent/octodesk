"""Entry point so PyInstaller (and `python -m octodesk`) can launch the app."""

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
