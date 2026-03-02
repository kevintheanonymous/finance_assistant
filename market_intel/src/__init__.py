# ═══════════════════════════════════════════════════════════════════════════════
# MARKET INTELLIGENCE ENGINE - SOURCE PACKAGE
# ═══════════════════════════════════════════════════════════════════════════════
"""
Core source package for the Market Intelligence Engine.
Import commonly used components for convenience.
"""

from .config import (
    APIKeys,
    AlertConfig,
    DatabaseConfig,
    ScoringWeights,
    Thresholds,
    SchedulerConfig,
    Watchlist,
    setup_logging,
    validate_config
)

__version__ = "1.0.0"
__author__ = "Market Intelligence Engine"
