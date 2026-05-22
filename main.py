"""Entry point for deploy hosts that run `uvicorn main:app`."""

from app.main import app

__all__ = ["app"]
