# ═══════════════════════════════════════════════════════════════════════════════
# MARKET INTELLIGENCE ENGINE - DATA FETCHERS PACKAGE
# ═══════════════════════════════════════════════════════════════════════════════
"""
Data fetching modules for all signal sources.
Each fetcher is responsible for one data vector.

Core Fetchers:
- SECFilingsFetcher: SEC Form 4 insider transactions
- WhaleAlertFetcher: Large crypto movements
- OptionsFlowFetcher: Unusual options activity
- SentimentAnalyzer: AI-powered sentiment analysis
- FearIndexFetcher: VIX + Crypto Fear & Greed

Advanced Fetchers:
- DarkPoolTracker: Off-exchange trading activity
- ShortInterestTracker: Short squeeze detection
- CongressionalTracker: STOCK Act politician trades
- OnChainAnalytics: DeFi TVL, gas fees, whale wallets
- SocialMomentumTracker: Reddit, StockTwits sentiment
- MacroIndicators: DXY, Treasury yields, commodities
"""

# Core fetchers
from .sec_filings import SECFilingsFetcher
from .whale_alert import WhaleAlertFetcher
from .options_flow import OptionsFlowFetcher
from .sentiment import SentimentAnalyzer
from .fear_index import FearIndexFetcher

# Advanced fetchers
from .advanced_sources import (
    DarkPoolTracker,
    ShortInterestTracker,
    CongressionalTracker,
    OnChainAnalytics,
    SocialMomentumTracker,
    MacroIndicators
)

__all__ = [
    # Core
    "SECFilingsFetcher",
    "WhaleAlertFetcher", 
    "OptionsFlowFetcher",
    "SentimentAnalyzer",
    "FearIndexFetcher",
    # Advanced
    "DarkPoolTracker",
    "ShortInterestTracker",
    "CongressionalTracker",
    "OnChainAnalytics",
    "SocialMomentumTracker",
    "MacroIndicators"
]
