# ═══════════════════════════════════════════════════════════════════════════════
# MARKET INTELLIGENCE ENGINE - OPTIONS FLOW FETCHER
# ═══════════════════════════════════════════════════════════════════════════════
"""
Fetches unusual options activity data.
Detects large call volume spikes that may indicate smart money positioning.
"""

from datetime import datetime, timedelta
from typing import Dict, Optional, List
import asyncio

import httpx
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from ..config import APIKeys, Thresholds, Watchlist

# ─────────────────────────────────────────────────────────────────────────────────
# OPTIONS DATA CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────────

# Finnhub API (free tier)
FINNHUB_BASE_URL = "https://finnhub.io/api/v1"

# Unusual Whales API (premium)
UNUSUAL_WHALES_BASE_URL = "https://api.unusualwhales.com/api"

# ─────────────────────────────────────────────────────────────────────────────────
# OPTIONS FLOW FETCHER CLASS
# ─────────────────────────────────────────────────────────────────────────────────

class OptionsFlowFetcher:
    """
    Fetches options volume data and detects unusual activity.
    
    How it works:
    1. Fetch current options volume for watchlist tickers
    2. Compare against 30-day average volume
    3. Flag tickers where call volume significantly exceeds baseline
    4. Score based on multiplier (>3x baseline = max score)
    """
    
    def __init__(self):
        self.finnhub_key = APIKeys.FINNHUB
        self.unusual_whales_key = APIKeys.UNUSUAL_WHALES
        self.client = httpx.AsyncClient(timeout=30.0)
        
        # Cache for baseline volumes (refreshed daily)
        self._baseline_cache: Dict[str, Dict] = {}
        self._cache_timestamp: Optional[datetime] = None
    
    async def close(self):
        """Close the HTTP client"""
        await self.client.aclose()
    
    # ─────────────────────────────────────────────────────────────────────────────
    # MAIN FETCH METHODS
    # ─────────────────────────────────────────────────────────────────────────────
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def fetch_options_volume(self, ticker: str) -> Optional[Dict]:
        """
        Fetch current options volume for a ticker.
        
        Args:
            ticker: Stock ticker symbol
            
        Returns:
            Dict with volume data or None on error
        """
        # Try Unusual Whales first (more detailed data)
        if self.unusual_whales_key:
            data = await self._fetch_unusual_whales(ticker)
            if data:
                return data
        
        # Fall back to Finnhub
        if self.finnhub_key:
            data = await self._fetch_finnhub_options(ticker)
            if data:
                return data
        
        # Use mock data if no API keys
        logger.warning(f"No options API configured for {ticker}, using mock data")
        return self._get_mock_options_data(ticker)
    
    async def _fetch_unusual_whales(self, ticker: str) -> Optional[Dict]:
        """Fetch from Unusual Whales API"""
        try:
            headers = {"Authorization": f"Bearer {self.unusual_whales_key}"}
            url = f"{UNUSUAL_WHALES_BASE_URL}/stock/{ticker}/options-volume"
            
            response = await self.client.get(url, headers=headers)
            
            if response.status_code == 401:
                logger.warning("Invalid Unusual Whales API key")
                return None
            
            response.raise_for_status()
            data = response.json()
            
            return {
                "ticker": ticker,
                "call_volume": data.get("call_volume", 0),
                "put_volume": data.get("put_volume", 0),
                "total_volume": data.get("total_volume", 0),
                "call_put_ratio": data.get("call_volume", 0) / max(data.get("put_volume", 1), 1),
                "avg_30d_volume": data.get("avg_30d_volume", 0),
                "source": "unusual_whales"
            }
            
        except Exception as e:
            logger.debug(f"Unusual Whales fetch failed for {ticker}: {e}")
            return None
    
    async def _fetch_finnhub_options(self, ticker: str) -> Optional[Dict]:
        """Fetch from Finnhub API (basic options data)"""
        try:
            params = {
                "symbol": ticker,
                "token": self.finnhub_key
            }
            
            # Get quote for volume reference
            quote_url = f"{FINNHUB_BASE_URL}/quote"
            response = await self.client.get(quote_url, params=params)
            response.raise_for_status()
            quote = response.json()
            
            # Finnhub doesn't have direct options volume in free tier
            # Use stock volume as a proxy indicator
            current_volume = quote.get("v", 0)  # Today's volume
            previous_close = quote.get("pc", 0)
            current_price = quote.get("c", 0)
            
            # Estimate options activity based on price movement and volume
            # This is a simplified approach - premium APIs have actual options data
            volume_ratio = current_volume / max(quote.get("t", current_volume), 1)  # vs avg
            
            return {
                "ticker": ticker,
                "stock_volume": current_volume,
                "volume_ratio": volume_ratio,
                "price_change_pct": ((current_price - previous_close) / max(previous_close, 1)) * 100,
                "source": "finnhub_estimate"
            }
            
        except Exception as e:
            logger.debug(f"Finnhub fetch failed for {ticker}: {e}")
            return None
    
    # ─────────────────────────────────────────────────────────────────────────────
    # BASELINE COMPARISON
    # ─────────────────────────────────────────────────────────────────────────────
    
    async def _get_baseline_volume(self, ticker: str) -> float:
        """
        Get 30-day average options volume for comparison.
        Uses cached values to avoid excessive API calls.
        
        Args:
            ticker: Stock ticker symbol
            
        Returns:
            Average daily options volume
        """
        # Check cache freshness
        if self._cache_timestamp and (datetime.utcnow() - self._cache_timestamp).hours < 24:
            if ticker in self._baseline_cache:
                return self._baseline_cache[ticker].get("avg_volume", 0)
        
        # Fetch fresh baseline
        try:
            if self.unusual_whales_key:
                headers = {"Authorization": f"Bearer {self.unusual_whales_key}"}
                url = f"{UNUSUAL_WHALES_BASE_URL}/stock/{ticker}/options-volume/historical"
                params = {"days": Thresholds.OPTIONS_VOLUME_BASELINE_DAYS}
                
                response = await self.client.get(url, headers=headers, params=params)
                if response.status_code == 200:
                    data = response.json()
                    avg_volume = data.get("average_volume", 0)
                    self._baseline_cache[ticker] = {"avg_volume": avg_volume}
                    self._cache_timestamp = datetime.utcnow()
                    return avg_volume
        except Exception as e:
            logger.debug(f"Baseline fetch failed: {e}")
        
        # Return default if no data
        return 100000  # Conservative default
    
    # ─────────────────────────────────────────────────────────────────────────────
    # ANOMALY DETECTION
    # ─────────────────────────────────────────────────────────────────────────────
    
    async def detect_unusual_activity(self) -> Dict[str, Dict]:
        """
        Scan all watchlist tickers for unusual options activity.
        
        Returns:
            Dict mapping ticker to anomaly data:
            {
                "NVDA": {
                    "current_volume": 500000,
                    "baseline_volume": 120000,
                    "volume_multiplier": 4.2,
                    "is_unusual": True,
                    "score": 100
                }
            }
        """
        results = {}
        
        logger.info("Scanning for unusual options activity...")
        
        for ticker in Watchlist.EQUITIES:
            try:
                # Add small delay to avoid rate limits
                await asyncio.sleep(0.1)
                
                data = await self.fetch_options_volume(ticker)
                if not data:
                    continue
                
                # Get baseline for comparison
                baseline = await self._get_baseline_volume(ticker)
                
                # Calculate multiplier
                current_volume = data.get("call_volume", data.get("stock_volume", 0))
                
                if baseline > 0:
                    multiplier = current_volume / baseline
                else:
                    multiplier = 0
                
                # Check if unusual
                is_unusual = multiplier >= Thresholds.OPTIONS_WEAK_MULTIPLIER
                
                # Calculate score
                score = self._calculate_options_score(multiplier)
                
                results[ticker] = {
                    "current_volume": current_volume,
                    "baseline_volume": baseline,
                    "volume_multiplier": round(multiplier, 2),
                    "is_unusual": is_unusual,
                    "call_put_ratio": data.get("call_put_ratio", 0),
                    "score": score
                }
                
                if is_unusual:
                    logger.info(f"Unusual options: {ticker} - {multiplier:.1f}x average (score: {score})")
                    
            except Exception as e:
                logger.warning(f"Error processing options for {ticker}: {e}")
                continue
        
        return results
    
    def _calculate_options_score(self, multiplier: float) -> float:
        """
        Calculate component score based on volume multiplier.
        
        Args:
            multiplier: Current volume / baseline volume
            
        Returns:
            Score from 0-100
        """
        if multiplier < 1.0:
            # Below average
            return 0
        elif multiplier >= Thresholds.OPTIONS_STRONG_MULTIPLIER:
            # Very unusual (>3x)
            return 100
        elif multiplier >= Thresholds.OPTIONS_WEAK_MULTIPLIER:
            # Moderately unusual (1.5x - 3x)
            normalized = (multiplier - Thresholds.OPTIONS_WEAK_MULTIPLIER) / \
                        (Thresholds.OPTIONS_STRONG_MULTIPLIER - Thresholds.OPTIONS_WEAK_MULTIPLIER)
            return 50 + (normalized * 50)
        else:
            # Slightly elevated (1x - 1.5x)
            normalized = (multiplier - 1.0) / (Thresholds.OPTIONS_WEAK_MULTIPLIER - 1.0)
            return normalized * 50
    
    # ─────────────────────────────────────────────────────────────────────────────
    # SCORING METHOD
    # ─────────────────────────────────────────────────────────────────────────────
    
    async def get_component_scores(self) -> Dict[str, float]:
        """
        Get options anomaly scores for all watched equities.
        
        Returns:
            Dict mapping ticker to score (0-100)
        """
        unusual_activity = await self.detect_unusual_activity()
        return {ticker: data["score"] for ticker, data in unusual_activity.items()}
    
    # ─────────────────────────────────────────────────────────────────────────────
    # MOCK DATA
    # ─────────────────────────────────────────────────────────────────────────────
    
    def _get_mock_options_data(self, ticker: str) -> Dict:
        """Generate mock options data for testing"""
        import random
        
        baseline = random.randint(50000, 200000)
        # 20% chance of unusual activity
        if random.random() < 0.2:
            multiplier = random.uniform(2.0, 5.0)
        else:
            multiplier = random.uniform(0.5, 1.5)
        
        current = int(baseline * multiplier)
        
        return {
            "ticker": ticker,
            "call_volume": current,
            "put_volume": int(current * random.uniform(0.3, 0.7)),
            "total_volume": int(current * 1.5),
            "call_put_ratio": random.uniform(1.0, 3.0),
            "avg_30d_volume": baseline,
            "source": "mock"
        }
