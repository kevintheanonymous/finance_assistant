# ═══════════════════════════════════════════════════════════════════════════════
# MARKET INTELLIGENCE ENGINE - SCORING ENGINE (ENHANCED WITH LEARNING)
# ═══════════════════════════════════════════════════════════════════════════════
"""
Central scoring engine that aggregates all component scores into final signals.
This is the brain of the system.

ENHANCED FEATURES:
- 10+ data components (up from 6)
- Dynamic weight adjustment from learning system  
- Asymmetric scoring for equity vs crypto
- Congressional trading integration
- Dark pool and short interest analysis
"""

from datetime import datetime
from typing import Dict, List, Optional, Tuple
import json

from loguru import logger

from .config import ScoringWeights, Thresholds, Watchlist
from .database import DatabaseOperations

# ─────────────────────────────────────────────────────────────────────────────────
# SIGNAL DATA CLASS
# ─────────────────────────────────────────────────────────────────────────────────

class Signal:
    """
    Represents a scored signal for an asset.
    Enhanced with all 10 component scores.
    """
    
    # Default weights (overridden by learned weights when available)
    DEFAULT_WEIGHTS = {
        "insider_cluster": 0.12,
        "options_anomaly": 0.10,
        "whale_movement": 0.12,
        "stablecoin_mint": 0.05,
        "sentiment_score": 0.12,
        "fear_index": 0.08,
        "dark_pool": 0.10,
        "short_interest": 0.08,
        "congressional": 0.08,
        "social_momentum": 0.08,
        "macro": 0.07
    }
    
    # Learned weights (populated from database)
    LEARNED_WEIGHTS: Optional[Dict[str, float]] = None
    
    def __init__(
        self,
        asset_symbol: str,
        asset_type: str,  # "equity" or "crypto"
        component_scores: Dict[str, float],
        raw_data: Optional[Dict] = None
    ):
        self.asset_symbol = asset_symbol
        self.asset_type = asset_type
        self.component_scores = component_scores
        self.raw_data = raw_data or {}
        
        # Calculate final score
        self.final_score = self._calculate_final_score()
        
        # Determine signal type
        self.signal_type = self._determine_signal_type()
        
        # Count confirmations (components scoring > 50)
        self.confirmation_count = self._count_confirmations()
        
        # Check validity
        self.is_valid = self._validate_signal()
        
        # Timestamp
        self.detected_at = datetime.utcnow()
    
    def _calculate_final_score(self) -> float:
        """Calculate weighted sum of component scores using learned or default weights"""
        # Use learned weights if available, otherwise defaults
        weights = self.LEARNED_WEIGHTS or self.DEFAULT_WEIGHTS
        
        total_weight = 0
        total_score = 0
        
        for component, default_weight in self.DEFAULT_WEIGHTS.items():
            score = self.component_scores.get(component, 50)  # Default to neutral
            weight = weights.get(component, default_weight)
            
            # Skip zero weights (component disabled)
            if weight > 0:
                total_score += score * weight
                total_weight += weight
        
        # Normalize to 0-100 scale
        if total_weight > 0:
            return round(total_score / total_weight, 2)
        return 50.0
    
    def _determine_signal_type(self) -> str:
        """Classify signal based on score"""
        if self.final_score >= Thresholds.HIGH_CONFIDENCE_SCORE:
            return "high_confidence"
        elif self.final_score >= Thresholds.MIN_ALERT_SCORE:
            return "moderate"
        elif self.final_score >= 40:
            return "weak"
        else:
            return "noise"
    
    def _count_confirmations(self) -> int:
        """Count how many components scored above 50"""
        return sum(1 for score in self.component_scores.values() if score > 50)
    
    def _validate_signal(self) -> bool:
        """
        Check if signal passes validation rules:
        1. Score must meet minimum threshold
        2. Must have minimum number of confirmations
        """
        if self.final_score < Thresholds.MIN_ALERT_SCORE:
            return False
        
        if self.confirmation_count < Thresholds.MIN_CONFIRMATIONS:
            return False
        
        return True
    
    def to_dict(self) -> Dict:
        """Convert signal to dictionary for storage/serialization"""
        return {
            "asset_symbol": self.asset_symbol,
            "asset_type": self.asset_type,
            "signal_score": self.final_score,
            "signal_type": self.signal_type,
            # Core components
            "insider_score": self.component_scores.get("insider_cluster", 0),
            "options_score": self.component_scores.get("options_anomaly", 0),
            "whale_score": self.component_scores.get("whale_movement", 0),
            "stablecoin_score": self.component_scores.get("stablecoin_mint", 0),
            "sentiment_score": self.component_scores.get("sentiment_score", 0),
            "fear_index_score": self.component_scores.get("fear_index", 0),
            # Advanced components
            "dark_pool_score": self.component_scores.get("dark_pool", 0),
            "short_interest_score": self.component_scores.get("short_interest", 0),
            "congressional_score": self.component_scores.get("congressional", 0),
            "social_momentum_score": self.component_scores.get("social_momentum", 0),
            "macro_score": self.component_scores.get("macro", 0),
            # Metadata
            "confirmation_count": self.confirmation_count,
            "raw_data": json.dumps(self.raw_data),
            "detected_at": self.detected_at
        }
    
    def __repr__(self):
        return f"<Signal {self.asset_symbol} score={self.final_score} type={self.signal_type} valid={self.is_valid}>"


# ─────────────────────────────────────────────────────────────────────────────────
# SCORING ENGINE CLASS (ENHANCED)
# ─────────────────────────────────────────────────────────────────────────────────

class ScoringEngine:
    """
    Aggregates component scores and generates final signals.
    
    ENHANCED: Now supports 10+ data components with learned weight optimization.
    
    How it works:
    1. Receives scores from all fetchers (core + advanced)
    2. Maps scores to the appropriate assets
    3. Calculates weighted final score (using learned or default weights)
    4. Validates against minimum thresholds
    5. Checks cooldowns before allowing alerts
    """
    
    def __init__(self, use_learned_weights: bool = True):
        # Core component scores
        self.insider_scores: Dict[str, float] = {}
        self.options_scores: Dict[str, float] = {}
        self.whale_scores: Dict[str, float] = {}
        self.stablecoin_scores: Dict[str, float] = {}
        self.sentiment_scores: Dict[str, float] = {}
        self.fear_index_scores: Dict[str, float] = {}
        
        # Advanced component scores
        self.dark_pool_scores: Dict[str, float] = {}
        self.short_interest_scores: Dict[str, float] = {}
        self.congressional_scores: Dict[str, float] = {}
        self.social_momentum_scores: Dict[str, float] = {}
        self.macro_scores: Dict[str, float] = {}
        self.on_chain_scores: Dict[str, float] = {}
        
        # Raw data for debugging
        self.raw_data: Dict[str, Dict] = {}
        
        # Load learned weights if enabled
        if use_learned_weights:
            self._load_learned_weights()
    
    def _load_learned_weights(self):
        """Load optimized weights from learning system"""
        try:
            from .learning import WeightOptimizer
            optimizer = WeightOptimizer()
            weights = optimizer.get_active_weights()
            
            # Map learning system weight names to component names
            Signal.LEARNED_WEIGHTS = {
                "insider_cluster": weights.get("insider_score", 0.12),
                "options_anomaly": weights.get("options_score", 0.10),
                "whale_movement": weights.get("whale_score", 0.12),
                "stablecoin_mint": weights.get("stablecoin_score", 0.05),
                "sentiment_score": weights.get("sentiment_score", 0.12),
                "fear_index": weights.get("fear_index_score", 0.08),
                "dark_pool": weights.get("dark_pool_score", 0.10),
                "short_interest": weights.get("short_interest_score", 0.08),
                "congressional": weights.get("congressional_score", 0.08),
                "social_momentum": weights.get("social_momentum_score", 0.08),
                "macro": weights.get("macro_score", 0.07)
            }
            
            logger.info(f"Loaded learned weights: {Signal.LEARNED_WEIGHTS}")
        except Exception as e:
            logger.warning(f"Could not load learned weights, using defaults: {e}")
            Signal.LEARNED_WEIGHTS = None
    
    # ─────────────────────────────────────────────────────────────────────────────
    # SCORE UPDATES (CORE COMPONENTS)
    # ─────────────────────────────────────────────────────────────────────────────
    
    def update_insider_scores(self, scores: Dict[str, float], raw: Optional[Dict] = None):
        """Update insider cluster scores"""
        self.insider_scores = scores
        if raw:
            self.raw_data["insider"] = raw
        logger.debug(f"Updated insider scores for {len(scores)} tickers")
    
    def update_options_scores(self, scores: Dict[str, float], raw: Optional[Dict] = None):
        """Update options anomaly scores"""
        self.options_scores = scores
        if raw:
            self.raw_data["options"] = raw
        logger.debug(f"Updated options scores for {len(scores)} tickers")
    
    def update_whale_scores(self, scores: Dict[str, float], raw: Optional[Dict] = None):
        """Update whale movement scores"""
        self.whale_scores = scores
        if raw:
            self.raw_data["whale"] = raw
        logger.debug(f"Updated whale scores for {len(scores)} symbols")
    
    def update_stablecoin_scores(self, scores: Dict[str, float], raw: Optional[Dict] = None):
        """Update stablecoin minting scores"""
        self.stablecoin_scores = scores
        if raw:
            self.raw_data["stablecoin"] = raw
        logger.debug(f"Updated stablecoin scores")
    
    def update_sentiment_scores(self, scores: Dict[str, float], raw: Optional[Dict] = None):
        """Update sentiment analysis scores"""
        self.sentiment_scores = scores
        if raw:
            self.raw_data["sentiment"] = raw
        logger.debug(f"Updated sentiment scores for {len(scores)} assets")
    
    def update_fear_index_scores(self, scores: Dict[str, float], raw: Optional[Dict] = None):
        """Update fear index scores"""
        self.fear_index_scores = scores
        if raw:
            self.raw_data["fear_index"] = raw
        logger.debug(f"Updated fear index scores")
    
    # ─────────────────────────────────────────────────────────────────────────────
    # SCORE UPDATES (ADVANCED COMPONENTS)
    # ─────────────────────────────────────────────────────────────────────────────
    
    def update_dark_pool_scores(self, scores: Dict[str, float], raw: Optional[Dict] = None):
        """Update dark pool trading scores"""
        self.dark_pool_scores = scores
        if raw:
            self.raw_data["dark_pool"] = raw
        logger.debug(f"Updated dark pool scores for {len(scores)} tickers")
    
    def update_short_interest_scores(self, scores: Dict[str, float], raw: Optional[Dict] = None):
        """Update short interest/squeeze scores"""
        self.short_interest_scores = scores
        if raw:
            self.raw_data["short_interest"] = raw
        logger.debug(f"Updated short interest scores for {len(scores)} tickers")
    
    def update_congressional_scores(self, scores: Dict[str, float], raw: Optional[Dict] = None):
        """Update congressional trading scores"""
        self.congressional_scores = scores
        if raw:
            self.raw_data["congressional"] = raw
        logger.debug(f"Updated congressional scores for {len(scores)} tickers")
    
    def update_social_momentum_scores(self, scores: Dict[str, float], raw: Optional[Dict] = None):
        """Update social momentum (Reddit/StockTwits) scores"""
        self.social_momentum_scores = scores
        if raw:
            self.raw_data["social_momentum"] = raw
        logger.debug(f"Updated social momentum scores for {len(scores)} assets")
    
    def update_macro_scores(self, scores: Dict[str, float], raw: Optional[Dict] = None):
        """Update macro indicator scores (DXY, yields, etc.)"""
        self.macro_scores = scores
        if raw:
            self.raw_data["macro"] = raw
        logger.debug(f"Updated macro scores")
    
    def update_on_chain_scores(self, scores: Dict[str, float], raw: Optional[Dict] = None):
        """Update on-chain analytics scores (DeFi, gas, etc.)"""
        self.on_chain_scores = scores
        if raw:
            self.raw_data["on_chain"] = raw
        logger.debug(f"Updated on-chain scores for {len(scores)} assets")
    
    # ─────────────────────────────────────────────────────────────────────────────
    # SIGNAL GENERATION
    # ─────────────────────────────────────────────────────────────────────────────
    
    def generate_signals(self) -> List[Signal]:
        """
        Generate signals for all assets based on current scores.
        
        Returns:
            List of Signal objects (valid signals only)
        """
        signals = []
        
        # Process equities
        for ticker in Watchlist.EQUITIES:
            signal = self._generate_equity_signal(ticker)
            if signal and signal.is_valid:
                signals.append(signal)
        
        # Process crypto
        for symbol in Watchlist.CRYPTO:
            signal = self._generate_crypto_signal(symbol)
            if signal and signal.is_valid:
                signals.append(signal)
        
        # Sort by score descending
        signals.sort(key=lambda s: s.final_score, reverse=True)
        
        logger.info(f"Generated {len(signals)} valid signals")
        return signals
    
    def _generate_equity_signal(self, ticker: str) -> Optional[Signal]:
        """Generate signal for an equity ticker with all 10+ components"""
        # Get equity fear index
        fear_score = self.fear_index_scores.get("EQUITY_FEAR", 50)
        macro_regime = self.macro_scores.get("regime_score", 50)
        
        # Equities use all relevant components
        component_scores = {
            # Core components
            "insider_cluster": self.insider_scores.get(ticker, 50),
            "options_anomaly": self.options_scores.get(ticker, 50),
            "whale_movement": 50,  # Neutral for equities (crypto-specific)
            "stablecoin_mint": 50,  # Neutral for equities (crypto-specific)
            "sentiment_score": self.sentiment_scores.get(ticker, 50),
            "fear_index": fear_score,
            # Advanced components
            "dark_pool": self.dark_pool_scores.get(ticker, 50),
            "short_interest": self.short_interest_scores.get(ticker, 50),
            "congressional": self.congressional_scores.get(ticker, 50),
            "social_momentum": self.social_momentum_scores.get(ticker, 50),
            "macro": macro_regime
        }
        
        raw_data = {
            "ticker": ticker,
            "insider_raw": self.raw_data.get("insider", {}).get(ticker),
            "options_raw": self.raw_data.get("options", {}).get(ticker),
            "sentiment_raw": self.raw_data.get("sentiment", {}).get(ticker),
            "dark_pool_raw": self.raw_data.get("dark_pool", {}).get(ticker),
            "short_interest_raw": self.raw_data.get("short_interest", {}).get(ticker),
            "congressional_raw": self.raw_data.get("congressional", {}).get(ticker)
        }
        
        return Signal(
            asset_symbol=ticker,
            asset_type="equity",
            component_scores=component_scores,
            raw_data=raw_data
        )
    
    def _generate_crypto_signal(self, symbol: str) -> Optional[Signal]:
        """Generate signal for a crypto symbol with all 10+ components"""
        # Get crypto fear index
        fear_score = self.fear_index_scores.get("CRYPTO_FEAR", 50)
        macro_regime = self.macro_scores.get("regime_score", 50)
        
        # Crypto uses different component mix
        component_scores = {
            # Core components
            "insider_cluster": 50,  # Neutral for crypto (equity-specific)
            "options_anomaly": 50,  # Neutral for crypto (equity-specific)
            "whale_movement": self.whale_scores.get(symbol, 50),
            "stablecoin_mint": self.stablecoin_scores.get("combined", 50),
            "sentiment_score": self.sentiment_scores.get(symbol, 50),
            "fear_index": fear_score,
            # Advanced components (crypto-specific)
            "dark_pool": 50,  # Neutral for crypto
            "short_interest": 50,  # Neutral for crypto
            "congressional": 50,  # Neutral for crypto
            "social_momentum": self.social_momentum_scores.get(symbol, 50),
            "macro": macro_regime,
            # On-chain specific scores (weighted into whale_movement for crypto)
            "on_chain": self.on_chain_scores.get(symbol, 50)
        }
        
        # Integrate on-chain data into whale movement for crypto
        on_chain = self.on_chain_scores.get(symbol, 50)
        if on_chain != 50:
            # Blend on-chain with whale movement
            component_scores["whale_movement"] = (
                component_scores["whale_movement"] * 0.6 + on_chain * 0.4
            )
        
        raw_data = {
            "symbol": symbol,
            "whale_raw": self.raw_data.get("whale", {}).get(symbol),
            "sentiment_raw": self.raw_data.get("sentiment", {}).get(symbol),
            "on_chain_raw": self.raw_data.get("on_chain", {}).get(symbol)
        }
        
        return Signal(
            asset_symbol=symbol,
            asset_type="crypto",
            component_scores=component_scores,
            raw_data=raw_data
        )
    
    # ─────────────────────────────────────────────────────────────────────────────
    # SIGNAL FILTERING
    # ─────────────────────────────────────────────────────────────────────────────
    
    def filter_for_alerting(self, signals: List[Signal]) -> List[Signal]:
        """
        Filter signals that should trigger alerts.
        Removes signals on cooldown.
        
        Args:
            signals: List of valid signals
            
        Returns:
            List of signals that should be alerted
        """
        alertable = []
        
        for signal in signals:
            # Check cooldown
            if DatabaseOperations.is_on_cooldown(signal.asset_symbol):
                logger.debug(f"Skipping {signal.asset_symbol} - on cooldown")
                continue
            
            alertable.append(signal)
        
        return alertable
    
    def save_signals(self, signals: List[Signal]) -> None:
        """
        Save signals to database for audit trail.
        
        Args:
            signals: List of signals to save
        """
        for signal in signals:
            DatabaseOperations.save_signal(signal.to_dict())
    
    # ─────────────────────────────────────────────────────────────────────────────
    # SUMMARY
    # ─────────────────────────────────────────────────────────────────────────────
    
    def get_market_summary(self) -> Dict:
        """
        Generate a summary of current market conditions.
        
        Returns:
            Dict with overall market state
        """
        # Calculate average scores by asset type
        equity_scores = [
            self._generate_equity_signal(t).final_score 
            for t in Watchlist.EQUITIES
        ]
        crypto_scores = [
            self._generate_crypto_signal(s).final_score 
            for s in Watchlist.CRYPTO
        ]
        
        avg_equity = sum(equity_scores) / max(len(equity_scores), 1)
        avg_crypto = sum(crypto_scores) / max(len(crypto_scores), 1)
        
        # Determine regimes
        equity_regime = self._score_to_regime(avg_equity)
        crypto_regime = self._score_to_regime(avg_crypto)
        
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "equity": {
                "average_score": round(avg_equity, 2),
                "regime": equity_regime,
                "top_tickers": self._get_top_assets("equity", 5)
            },
            "crypto": {
                "average_score": round(avg_crypto, 2),
                "regime": crypto_regime,
                "top_assets": self._get_top_assets("crypto", 3)
            },
            "fear_indices": {
                "vix_score": self.fear_index_scores.get("EQUITY_FEAR", 50),
                "crypto_fg_score": self.fear_index_scores.get("CRYPTO_FEAR", 50)
            }
        }
    
    def _score_to_regime(self, score: float) -> str:
        """Convert average score to regime classification"""
        if score >= 70:
            return "bullish"
        elif score >= 55:
            return "slightly_bullish"
        elif score >= 45:
            return "neutral"
        elif score >= 30:
            return "slightly_bearish"
        else:
            return "bearish"
    
    def _get_top_assets(self, asset_type: str, count: int) -> List[Tuple[str, float]]:
        """Get top N assets by score"""
        if asset_type == "equity":
            signals = [self._generate_equity_signal(t) for t in Watchlist.EQUITIES]
        else:
            signals = [self._generate_crypto_signal(s) for s in Watchlist.CRYPTO]
        
        signals.sort(key=lambda s: s.final_score, reverse=True)
        return [(s.asset_symbol, s.final_score) for s in signals[:count]]
