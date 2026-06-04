"""Enumerations shared across all engines.

Keeping the vocabulary centralised guarantees that the labels emitted by the
engines exactly match the contract described in the "Engine Outputs" document
and that downstream consumers (UI, RMS, audit log) never see free-form strings.
"""
from __future__ import annotations

from enum import Enum


class Asset(str, Enum):
    """Five supported asset classes."""

    STOCK = "STOCK"
    FNO = "FNO"
    INDEX = "INDEX"
    FOREX = "FOREX"
    COMMODITY = "COMMODITY"


# ---- Suitability / access -------------------------------------------------
class SuitabilityStatus(str, Enum):
    ELIGIBLE = "Eligible"
    LIMITED_ACCESS = "Limited Access"
    EDUCATION_REQUIRED = "Education Required"
    HIGH_RISK = "High Risk"
    NOT_SUITABLE = "Not Suitable"


class SegmentAccess(str, Enum):
    ENABLED = "enabled"
    RESTRICTED = "restricted"
    WATCH_ONLY = "watch-only"
    BLOCKED = "blocked"


class EligibilityTag(str, Enum):
    TRADABLE = "tradable"
    AVOID = "avoid"
    WAIT = "wait"
    MONITOR = "monitor"


# ---- Regime / trend -------------------------------------------------------
class Regime(str, Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    SIDEWAYS = "sideways"
    VOLATILE = "volatile"
    BREAKOUT = "breakout"
    REVERSAL = "reversal zone"


class TrendDirection(str, Enum):
    UPTREND = "uptrend"
    DOWNTREND = "downtrend"
    SIDEWAYS = "sideways"
    WEAK = "weak trend"
    MIXED = "mixed trend"


class StrategyTag(str, Enum):
    TREND_FOLLOWING = "trend-following"
    PULLBACK = "pullback"
    BREAKOUT = "breakout"
    HEDGED = "hedged"
    AVOID = "avoid"


# ---- Generic decision verbs ----------------------------------------------
class RiskUtilisation(str, Enum):
    SAFE = "safe"
    MODERATE = "moderate"
    STRETCHED = "stretched"
    OVEREXPOSED = "overexposed"


class GlobalSentiment(str, Enum):
    RISK_ON = "risk-on"
    RISK_OFF = "risk-off"
    MIXED = "mixed"
    PANIC = "panic"
    RECOVERY = "recovery"


class ApprovalStatus(str, Enum):
    APPROVED = "approved"
    CONDITIONAL = "conditionally approved"
    WAIT = "wait"
    HEDGE_REQUIRED = "hedge required"
    REJECTED = "rejected"


class ExecutionPriority(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    NO_TRADE = "no-trade"


# Severity used for warning flags everywhere.
class Severity(str, Enum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    EXTREME = "extreme"
