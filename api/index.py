"""Vercel entrypoint: Vercel's Python runtime auto-detects the `app` ASGI
callable in this file and serves it. Kept as a thin re-export so the actual
application lives in the package (`tfrefactor/web/app.py`) alongside its
tests, not duplicated here.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tfrefactor.web.app import app  # noqa: E402

__all__ = ["app"]
