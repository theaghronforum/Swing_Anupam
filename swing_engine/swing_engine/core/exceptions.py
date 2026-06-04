"""Typed exceptions so the pipeline can distinguish data problems from bugs."""
from __future__ import annotations


class SwingEngineError(Exception):
    """Base class for all engine errors."""


class InsufficientDataError(SwingEngineError):
    """Raised when an engine cannot run because mandatory data is missing.

    The pipeline catches this and records a skipped/degraded result rather than
    crashing the whole run.
    """


class ConfigurationError(SwingEngineError):
    """Raised for invalid engine configuration."""
