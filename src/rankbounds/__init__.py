"""Deterministic bounds, not predictions of unknown relevance."""

from .core import BoundsError, audit
from .paired import compare

__version__ = "0.3.0"
__all__ = ["BoundsError", "audit", "compare"]
