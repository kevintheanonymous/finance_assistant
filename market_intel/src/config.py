# ═══════════════════════════════════════════════════════════════════════════════
# MARKET INTELLIGENCE ENGINE - CONFIGURATION MODULE
# ═══════════════════════════════════════════════════════════════════════════════
"""
Central configuration management. Loads all settings from environment variables.
This module is imported by all other modules to access configuration.

FREE PUBLIC APIs USED (NO KEY REQUIRED):
- SEC EDGAR: Insider filings (https://www.sec.gov/cgi-bin/browse-edgar)
- Yahoo Finance: Stock prices, VIX (https://query1.finance.yahoo.com)
- CoinGecko: Crypto prices (https://api.coingecko.com)
- DeFiLlama: DeFi TVL data (https://api.llama.fi)
- Alternative.me: Crypto Fear & Greed (https://api.alternative.me)
- ApeWisdom: Reddit WSB sentiment (https://apewisdom.io/api)
- StockTwits: Social sentiment (https://api.stocktwits.com)
- Blockchair: Bitcoin transactions (https://api.blockchair.com)

FREE TIER APIs (KEY REQUIRED, NO COST):
- Finnhub: Stock data & news
- Etherscan: Ethereum transactions  
- FMP: Financial data
- Polygon: Market data
"""

import os
from pathlib import Path
from dotenv import load_dotenv
from loguru import logger

# ─────────────────────────────────────────────────────────────────────────────────
# LOAD ENVIRONMENT VARIABLES
# ─────────────────────────────────────────────────────────────────────────────────
# Look for .env file in the project root
ENV_PATH = Path(__file__).parent.parent / ".env"
load_dotenv(ENV_PATH)

# ─────────────────────────────────────────────────────────────────────────────────
# API KEYS (All optional - system uses free public APIs as fallback)
# ─────────────────────────────────────────────────────────────────────────────────
class APIKeys:
    """Container for all API credentials"""
    # Core APIs (optional - free fallbacks available)
    OPENAI = os.getenv("OPENAI_API_KEY", "")          # Sentiment (fallback: rule-based)
    FINNHUB = os.getenv("FINNHUB_API_KEY", "")        # Stock data (free tier)
    WHALE_ALERT = os.getenv("WHALE_ALERT_API_KEY", "")# Whales (fallback: Etherscan/Blockchair)
    UNUSUAL_WHALES = os.getenv("UNUSUAL_WHALES_API_KEY", "")  # Skip - paid only
    TWITTER_BEARER = os.getenv("TWITTER_BEARER_TOKEN", "")    # Skip - using Reddit/StockTwits
    
    # Free tier APIs
    QUIVER_QUANT = os.getenv("QUIVER_QUANT_API_KEY", "")      # Congressional trades
    ETHERSCAN = os.getenv("ETHERSCAN_API_KEY", "")            # Ethereum data (free)
    FMP = os.getenv("FMP_API_KEY", "")                         # Financial data (free tier)
    POLYGON = os.getenv("POLYGON_API_KEY", "")                 # Market data (free tier)

# ─────────────────────────────────────────────────────────────────────────────────
# ALERT DELIVERY
# ─────────────────────────────────────────────────────────────────────────────────
class AlertConfig:
    """Discord and Telegram webhook settings"""
    DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# ─────────────────────────────────────────────────────────────────────────────────
# DATABASE
# ─────────────────────────────────────────────────────────────────────────────────
class DatabaseConfig:
    """Database connection settings"""
    URL = os.getenv("DATABASE_URL", "sqlite:///data/signals.db")

# ─────────────────────────────────────────────────────────────────────────────────
# SCORING WEIGHTS (The brain of the system)
# ─────────────────────────────────────────────────────────────────────────────────
class ScoringWeights:
    """
    Default weights for each signal component.
    NOTE: The system now uses LEARNED weights that are optimized automatically.
    These defaults are used as a baseline until sufficient data is collected.
    
    Core Components (6):
    - INSIDER_CLUSTER: SEC Form 4 filings
    - OPTIONS_ANOMALY: Unusual call volume
    - WHALE_MOVEMENT: Crypto whale transactions
    - STABLECOIN_MINT: USDT/USDC minting
    - SENTIMENT_SCORE: AI-analyzed news/social
    - FEAR_INDEX: VIX / Crypto Fear & Greed
    
    Advanced Components (5):
    - DARK_POOL: Off-exchange trading activity
    - SHORT_INTEREST: Squeeze potential detection
    - CONGRESSIONAL: Politician trades (STOCK Act)
    - SOCIAL_MOMENTUM: Reddit/StockTwits buzz
    - MACRO: DXY, yields, commodities
    """
    # Core components
    INSIDER_CLUSTER = 0.12      # SEC Form 4 filings
    OPTIONS_ANOMALY = 0.10      # Unusual call volume
    WHALE_MOVEMENT = 0.12       # Crypto whale transactions
    STABLECOIN_MINT = 0.05      # USDT/USDC minting
    SENTIMENT_SCORE = 0.12      # AI-analyzed news/social
    FEAR_INDEX = 0.08           # VIX / Crypto Fear & Greed
    
    # Advanced components
    DARK_POOL = 0.10            # Off-exchange activity
    SHORT_INTEREST = 0.08       # Squeeze detection
    CONGRESSIONAL = 0.08        # Politician trades
    SOCIAL_MOMENTUM = 0.08      # Reddit/StockTwits
    MACRO = 0.07                # DXY, yields, etc.

    @classmethod
    def validate(cls):
        """Ensure weights sum to 1.0"""
        total = (
            cls.INSIDER_CLUSTER +
            cls.OPTIONS_ANOMALY +
            cls.WHALE_MOVEMENT +
            cls.STABLECOIN_MINT +
            cls.SENTIMENT_SCORE +
            cls.FEAR_INDEX +
            cls.DARK_POOL +
            cls.SHORT_INTEREST +
            cls.CONGRESSIONAL +
            cls.SOCIAL_MOMENTUM +
            cls.MACRO
        )
        if not 0.99 <= total <= 1.01:
            raise ValueError(f"Scoring weights must sum to 1.0, got {total}")
        return True

# ─────────────────────────────────────────────────────────────────────────────────
# THRESHOLDS & RULES
# ─────────────────────────────────────────────────────────────────────────────────
class Thresholds:
    """Alert thresholds and filtering rules"""
    
    # Minimum score to trigger any alert
    MIN_ALERT_SCORE = int(os.getenv("MIN_SIGNAL_SCORE", "60"))
    
    # Score required for "HIGH-CONFIDENCE" classification
    HIGH_CONFIDENCE_SCORE = int(os.getenv("HIGH_CONFIDENCE_THRESHOLD", "80"))
    
    # Hours before same asset can re-alert (prevents spam)
    COOLDOWN_HOURS = int(os.getenv("ALERT_COOLDOWN_HOURS", "24"))
    
    # Minimum number of components that must score >50 to be valid
    MIN_CONFIRMATIONS = 3
    
    # ─────────────────────────────────────────────────────────────────────────────
    # INSIDER DETECTION THRESHOLDS
    # ─────────────────────────────────────────────────────────────────────────────
    INSIDER_LOOKBACK_DAYS = 14          # Window to detect clustering
    INSIDER_MIN_CLUSTER_SIZE = 2        # Minimum buys to flag
    INSIDER_STRONG_CLUSTER_SIZE = 3     # Buys for max score
    
    # ─────────────────────────────────────────────────────────────────────────────
    # OPTIONS FLOW THRESHOLDS
    # ─────────────────────────────────────────────────────────────────────────────
    OPTIONS_VOLUME_BASELINE_DAYS = 30   # Days for average calculation
    OPTIONS_WEAK_MULTIPLIER = 1.5       # Volume multiplier for weak signal
    OPTIONS_STRONG_MULTIPLIER = 3.0     # Volume multiplier for strong signal
    
    # ─────────────────────────────────────────────────────────────────────────────
    # WHALE MOVEMENT THRESHOLDS (in BTC equivalent)
    # ─────────────────────────────────────────────────────────────────────────────
    WHALE_MIN_TRANSACTION_USD = 1_000_000   # Minimum USD value to track
    WHALE_WEAK_OUTFLOW_BTC = 1_000          # BTC/day for weak signal
    WHALE_STRONG_OUTFLOW_BTC = 5_000        # BTC/day for strong signal
    
    # ─────────────────────────────────────────────────────────────────────────────
    # STABLECOIN THRESHOLDS
    # ─────────────────────────────────────────────────────────────────────────────
    STABLECOIN_WEAK_MINT_USD = 100_000_000      # $100M/day weak signal
    STABLECOIN_STRONG_MINT_USD = 500_000_000    # $500M/day strong signal
    
    # ─────────────────────────────────────────────────────────────────────────────
    # FEAR INDEX THRESHOLDS
    # ─────────────────────────────────────────────────────────────────────────────
    VIX_LOW = 15            # VIX below this = bullish
    VIX_HIGH = 25           # VIX above this = bearish
    CRYPTO_FG_GREED = 60    # Crypto F&G above this = greedy
    CRYPTO_FG_FEAR = 40     # Crypto F&G below this = fearful

# ─────────────────────────────────────────────────────────────────────────────────
# SCHEDULER INTERVALS (in minutes)
# ─────────────────────────────────────────────────────────────────────────────────
class SchedulerConfig:
    """How often each data fetcher runs"""
    SEC_FILINGS_INTERVAL = 15       # Check SEC RSS every 15 minutes
    WHALE_ALERT_INTERVAL = 5        # Check whale movements every 5 minutes
    OPTIONS_FLOW_INTERVAL = 30      # Check options every 30 minutes
    SENTIMENT_INTERVAL = 60         # Run sentiment analysis hourly
    FEAR_INDEX_INTERVAL = 60        # Check VIX/Fear & Greed hourly

# ─────────────────────────────────────────────────────────────────────────────────
# WATCHLIST (Tickers to monitor)
# ─────────────────────────────────────────────────────────────────────────────────
class Watchlist:
    """
    Assets to actively monitor.
    The system will scan globally but prioritize these.
    """
    # Top-tier equities (high insider activity historically)
    EQUITIES = [
        "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA",
        "AMD", "INTC", "CRM", "ORCL", "ADBE", "NFLX", "PYPL",
        "SQ", "SHOP", "COIN", "MSTR", "PLTR", "SNOW"
    ]
    
    # Crypto assets (tracked via whale movements)
    CRYPTO = [
        "BTC", "ETH", "SOL", "AVAX", "MATIC", "DOT", "ATOM"
    ]
    
    # Stablecoins to monitor for minting
    STABLECOINS = ["USDT", "USDC", "DAI", "BUSD"]

# ─────────────────────────────────────────────────────────────────────────────────
# LOGGING CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────────
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

def setup_logging():
    """Configure loguru for structured logging"""
    from pathlib import Path
    
    # Ensure logs directory exists
    log_dir = Path(__file__).parent.parent / "logs"
    log_dir.mkdir(exist_ok=True)
    
    # Remove default handler
    logger.remove()
    
    # Add console handler with color
    logger.add(
        lambda msg: print(msg, end=""),
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
               "<level>{level: <8}</level> | "
               "<cyan>{name}</cyan>:<cyan>{function}</cyan> | "
               "<level>{message}</level>",
        level=LOG_LEVEL,
        colorize=True
    )
    
    # Add file handler for persistence
    logger.add(
        log_dir / "market_intel_{time:YYYY-MM-DD}.log",
        rotation="1 day",
        retention="30 days",
        level="DEBUG",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function} | {message}"
    )
    
    return logger

# ─────────────────────────────────────────────────────────────────────────────────
# VALIDATE CONFIGURATION ON IMPORT
# ─────────────────────────────────────────────────────────────────────────────────
def validate_config():
    """Run validation checks on startup"""
    errors = []
    
    # Check required API keys
    if not APIKeys.OPENAI:
        errors.append("OPENAI_API_KEY is required for sentiment analysis")
    
    # Check at least one alert method is configured
    if not AlertConfig.DISCORD_WEBHOOK_URL and not AlertConfig.TELEGRAM_BOT_TOKEN:
        errors.append("At least one alert method (Discord or Telegram) must be configured")
    
    # Validate scoring weights
    try:
        ScoringWeights.validate()
    except ValueError as e:
        errors.append(str(e))
    
    if errors:
        for error in errors:
            logger.warning(f"Config Warning: {error}")
        return False
    
    return True
