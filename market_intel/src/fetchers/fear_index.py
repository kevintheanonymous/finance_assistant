# ═══════════════════════════════════════════════════════════════════════════════
# MARKET INTELLIGENCE ENGINE - FEAR INDEX FETCHER
# ═══════════════════════════════════════════════════════════════════════════════
"""
Fetches macro fear/greed indicators: VIX and Crypto Fear & Greed Index.
Used to determine overall market regime.
"""

from datetime import datetime
from typing import Dict, Optional

import httpx
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from ..config import Thresholds

# ─────────────────────────────────────────────────────────────────────────────────
# FEAR INDEX CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────────

# Alternative.me Crypto Fear & Greed API (free)
CRYPTO_FEAR_GREED_URL = "https://api.alternative.me/fng/"

# Yahoo Finance VIX (no API key needed)
YAHOO_VIX_URL = "https://query1.finance.yahoo.com/v8/finance/chart/%5EVIX"

# ─────────────────────────────────────────────────────────────────────────────────
# FEAR INDEX FETCHER CLASS
# ─────────────────────────────────────────────────────────────────────────────────

class FearIndexFetcher:
    """
    Fetches macro-level fear indicators.
    
    Indicators:
    - VIX (CBOE Volatility Index): Measures stock market fear
      - Low (<15) = Complacent = Bullish
      - Normal (15-25) = Neutral
      - High (>25) = Fearful = Bearish
      
    - Crypto Fear & Greed Index: 0-100 scale
      - 0-25 = Extreme Fear = Often buying opportunity
      - 25-45 = Fear
      - 45-55 = Neutral
      - 55-75 = Greed
      - 75-100 = Extreme Greed = Often selling territory
    """
    
    def __init__(self):
        self.client = httpx.AsyncClient(
            timeout=30.0,
            headers={"User-Agent": "Mozilla/5.0"}
        )
    
    async def close(self):
        """Close the HTTP client"""
        await self.client.aclose()
    
    # ─────────────────────────────────────────────────────────────────────────────
    # VIX FETCHING
    # ─────────────────────────────────────────────────────────────────────────────
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def fetch_vix(self) -> Dict:
        """
        Fetch current VIX level from Yahoo Finance.
        
        Returns:
            Dict with VIX data and classification
        """
        logger.info("Fetching VIX...")
        
        try:
            response = await self.client.get(YAHOO_VIX_URL)
            response.raise_for_status()
            
            data = response.json()
            
            # Navigate Yahoo's response structure
            result = data.get("chart", {}).get("result", [{}])[0]
            meta = result.get("meta", {})
            
            current_vix = meta.get("regularMarketPrice", 0)
            previous_close = meta.get("previousClose", 0)
            
            # Classify VIX level
            if current_vix < Thresholds.VIX_LOW:
                classification = "complacent"
                regime = "bullish"
            elif current_vix > Thresholds.VIX_HIGH:
                classification = "fearful"
                regime = "bearish"
            else:
                classification = "neutral"
                regime = "neutral"
            
            # Calculate score (inverted - low VIX = high score)
            score = self._calculate_vix_score(current_vix)
            
            result = {
                "value": current_vix,
                "previous_close": previous_close,
                "change": current_vix - previous_close,
                "change_pct": ((current_vix - previous_close) / max(previous_close, 1)) * 100,
                "classification": classification,
                "regime": regime,
                "score": score,
                "timestamp": datetime.utcnow().isoformat()
            }
            
            logger.info(f"VIX: {current_vix:.2f} ({classification}) - Score: {score}")
            return result
            
        except Exception as e:
            logger.error(f"Error fetching VIX: {e}")
            # Return neutral on error
            return {
                "value": 20,
                "classification": "neutral",
                "regime": "neutral",
                "score": 50,
                "error": str(e)
            }
    
    def _calculate_vix_score(self, vix: float) -> float:
        """
        Calculate score from VIX level (inverted).
        Low VIX = High score (bullish regime)
        High VIX = Low score (fearful regime)
        
        Args:
            vix: Current VIX value
            
        Returns:
            Score from 0-100
        """
        if vix <= Thresholds.VIX_LOW:
            # Very low VIX - max score
            return 100
        elif vix >= Thresholds.VIX_HIGH:
            # Very high VIX - low but not zero (fear can mean opportunity)
            return max(0, 30 - (vix - Thresholds.VIX_HIGH))
        else:
            # Normal range - linear interpolation
            normalized = (Thresholds.VIX_HIGH - vix) / (Thresholds.VIX_HIGH - Thresholds.VIX_LOW)
            return 30 + (normalized * 70)
    
    # ─────────────────────────────────────────────────────────────────────────────
    # CRYPTO FEAR & GREED
    # ─────────────────────────────────────────────────────────────────────────────
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def fetch_crypto_fear_greed(self) -> Dict:
        """
        Fetch Crypto Fear & Greed Index from Alternative.me.
        
        Returns:
            Dict with index data and classification
        """
        logger.info("Fetching Crypto Fear & Greed Index...")
        
        try:
            response = await self.client.get(CRYPTO_FEAR_GREED_URL)
            response.raise_for_status()
            
            data = response.json()
            
            current_data = data.get("data", [{}])[0]
            value = int(current_data.get("value", 50))
            classification = current_data.get("value_classification", "Neutral")
            
            # Determine regime (contrarian - extreme fear can be bullish)
            if value <= 25:
                regime = "bullish"  # Extreme fear = buying opportunity
            elif value >= 75:
                regime = "bearish"  # Extreme greed = time for caution
            elif value >= Thresholds.CRYPTO_FG_GREED:
                regime = "greed"
            elif value <= Thresholds.CRYPTO_FG_FEAR:
                regime = "fear"
            else:
                regime = "neutral"
            
            # Calculate score (higher = more bullish signal)
            score = self._calculate_crypto_fg_score(value)
            
            result = {
                "value": value,
                "classification": classification,
                "regime": regime,
                "score": score,
                "timestamp": current_data.get("timestamp", datetime.utcnow().isoformat())
            }
            
            logger.info(f"Crypto F&G: {value} ({classification}) - Score: {score}")
            return result
            
        except Exception as e:
            logger.error(f"Error fetching Crypto Fear & Greed: {e}")
            return {
                "value": 50,
                "classification": "Neutral",
                "regime": "neutral",
                "score": 50,
                "error": str(e)
            }
    
    def _calculate_crypto_fg_score(self, value: int) -> float:
        """
        Calculate score from Crypto Fear & Greed.
        We use a contrarian approach:
        - Extreme fear (0-25) can be bullish (accumulation zone)
        - Extreme greed (75-100) can be bearish (distribution zone)
        - But we also want to capture momentum
        
        Args:
            value: Fear & Greed index (0-100)
            
        Returns:
            Score from 0-100
        """
        if value <= 25:
            # Extreme fear - contrarian bullish
            return 70 + (25 - value)  # 70-95
        elif value >= 75:
            # Extreme greed - contrarian warning
            return max(30, 100 - value)  # 0-25
        elif value >= Thresholds.CRYPTO_FG_GREED:
            # Greed zone - positive but cautious
            return 60 + ((value - Thresholds.CRYPTO_FG_GREED) / (75 - Thresholds.CRYPTO_FG_GREED)) * 15
        elif value <= Thresholds.CRYPTO_FG_FEAR:
            # Fear zone - contrarian positive
            return 55 + ((Thresholds.CRYPTO_FG_FEAR - value) / Thresholds.CRYPTO_FG_FEAR) * 15
        else:
            # Neutral zone
            return 50 + (value - 50) * 0.2
    
    # ─────────────────────────────────────────────────────────────────────────────
    # COMBINED ANALYSIS
    # ─────────────────────────────────────────────────────────────────────────────
    
    async def get_fear_analysis(self) -> Dict:
        """
        Get combined fear index analysis.
        
        Returns:
            Dict with VIX and Crypto F&G data plus combined score
        """
        vix_data = await self.fetch_vix()
        crypto_fg_data = await self.fetch_crypto_fear_greed()
        
        # Calculate combined score (weighted average)
        combined_score = (vix_data["score"] * 0.5) + (crypto_fg_data["score"] * 0.5)
        
        # Determine overall regime
        if vix_data["regime"] == "bullish" and crypto_fg_data["regime"] == "bullish":
            overall_regime = "risk_on"
        elif vix_data["regime"] == "bearish" and crypto_fg_data["regime"] == "bearish":
            overall_regime = "risk_off"
        else:
            overall_regime = "mixed"
        
        return {
            "vix": vix_data,
            "crypto_fear_greed": crypto_fg_data,
            "combined_score": combined_score,
            "overall_regime": overall_regime
        }
    
    # ─────────────────────────────────────────────────────────────────────────────
    # SCORING METHOD
    # ─────────────────────────────────────────────────────────────────────────────
    
    async def get_component_scores(self) -> Dict[str, float]:
        """
        Get fear index scores.
        
        Returns:
            Dict with "EQUITIES" and "CRYPTO" scores
        """
        analysis = await self.get_fear_analysis()
        
        return {
            "EQUITY_FEAR": analysis["vix"]["score"],
            "CRYPTO_FEAR": analysis["crypto_fear_greed"]["score"],
            "COMBINED": analysis["combined_score"]
        }
