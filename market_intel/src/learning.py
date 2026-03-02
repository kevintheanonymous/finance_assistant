# ═══════════════════════════════════════════════════════════════════════════════
# MARKET INTELLIGENCE ENGINE - MACHINE LEARNING & BACKTESTING
# ═══════════════════════════════════════════════════════════════════════════════
"""
Self-improving system that:
1. Tracks every prediction/signal
2. Waits for outcome (price at T+1d, T+3d, T+7d)
3. Calculates which components predicted correctly
4. Automatically adjusts weights to maximize accuracy
5. Generates performance reports
"""

import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from pathlib import Path
import statistics

from sqlalchemy import Column, Integer, Float, String, DateTime, Boolean, Text
from loguru import logger
import httpx

from .database import Base, engine, SessionLocal, DatabaseOperations
from .config import ScoringWeights, Watchlist, APIKeys

# ─────────────────────────────────────────────────────────────────────────────────
# DATABASE MODELS FOR LEARNING
# ─────────────────────────────────────────────────────────────────────────────────

class PredictionOutcome(Base):
    """
    Tracks the outcome of each signal for learning.
    Links signal score to actual price movement.
    """
    __tablename__ = "prediction_outcomes"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Link to original signal
    signal_id = Column(Integer, nullable=False, index=True)
    asset_symbol = Column(String(20), nullable=False, index=True)
    asset_type = Column(String(10), nullable=False)
    
    # Signal data at time of prediction
    signal_score = Column(Float, nullable=False)
    signal_type = Column(String(30), nullable=False)
    
    # Component scores (for weight learning)
    insider_score = Column(Float, default=0)
    options_score = Column(Float, default=0)
    whale_score = Column(Float, default=0)
    stablecoin_score = Column(Float, default=0)
    sentiment_score = Column(Float, default=0)
    fear_index_score = Column(Float, default=0)
    dark_pool_score = Column(Float, default=0)
    short_interest_score = Column(Float, default=0)
    social_momentum_score = Column(Float, default=0)
    macro_score = Column(Float, default=0)
    
    # Price data
    price_at_signal = Column(Float, nullable=True)
    price_1d_later = Column(Float, nullable=True)
    price_3d_later = Column(Float, nullable=True)
    price_7d_later = Column(Float, nullable=True)
    price_30d_later = Column(Float, nullable=True)
    
    # Calculated outcomes
    return_1d = Column(Float, nullable=True)
    return_3d = Column(Float, nullable=True)
    return_7d = Column(Float, nullable=True)
    return_30d = Column(Float, nullable=True)
    
    # Was the prediction correct? (positive return)
    correct_1d = Column(Boolean, nullable=True)
    correct_3d = Column(Boolean, nullable=True)
    correct_7d = Column(Boolean, nullable=True)
    correct_30d = Column(Boolean, nullable=True)
    
    # Timestamps
    signal_time = Column(DateTime, nullable=False)
    outcome_checked_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f"<PredictionOutcome {self.asset_symbol} score={self.signal_score} return_7d={self.return_7d}>"


class LearnedWeights(Base):
    """
    Stores the learned optimal weights over time.
    System adjusts weights based on historical performance.
    """
    __tablename__ = "learned_weights"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # The weights
    insider_weight = Column(Float, default=0.20)
    options_weight = Column(Float, default=0.15)
    whale_weight = Column(Float, default=0.20)
    stablecoin_weight = Column(Float, default=0.10)
    sentiment_weight = Column(Float, default=0.20)
    fear_index_weight = Column(Float, default=0.15)
    dark_pool_weight = Column(Float, default=0.0)
    short_interest_weight = Column(Float, default=0.0)
    social_momentum_weight = Column(Float, default=0.0)
    macro_weight = Column(Float, default=0.0)
    
    # Performance metrics when these weights were calculated
    accuracy_1d = Column(Float, nullable=True)
    accuracy_7d = Column(Float, nullable=True)
    avg_return = Column(Float, nullable=True)
    sharpe_ratio = Column(Float, nullable=True)
    
    # Sample size
    predictions_analyzed = Column(Integer, default=0)
    
    # Is this the active weight set?
    is_active = Column(Boolean, default=False)
    
    # Timestamps
    calculated_at = Column(DateTime, default=datetime.utcnow)
    activated_at = Column(DateTime, nullable=True)
    
    def __repr__(self):
        return f"<LearnedWeights accuracy_7d={self.accuracy_7d} active={self.is_active}>"


class PerformanceLog(Base):
    """
    Daily performance log for tracking system effectiveness.
    """
    __tablename__ = "performance_logs"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    date = Column(DateTime, nullable=False, unique=True, index=True)
    
    # Signal counts
    total_signals = Column(Integer, default=0)
    high_confidence_signals = Column(Integer, default=0)
    alerts_sent = Column(Integer, default=0)
    
    # Accuracy (from past signals now matured)
    accuracy_rate = Column(Float, nullable=True)  # % of signals that were correct
    avg_return = Column(Float, nullable=True)     # Average return of signaled assets
    
    # Best and worst
    best_signal = Column(String(20), nullable=True)
    best_return = Column(Float, nullable=True)
    worst_signal = Column(String(20), nullable=True)
    worst_return = Column(Float, nullable=True)
    
    # Current weights used
    weights_snapshot = Column(Text, nullable=True)  # JSON
    
    created_at = Column(DateTime, default=datetime.utcnow)


# Create tables
Base.metadata.create_all(engine)


# ─────────────────────────────────────────────────────────────────────────────────
# PRICE FETCHER FOR OUTCOMES
# ─────────────────────────────────────────────────────────────────────────────────

class PriceFetcher:
    """Fetches historical and current prices for outcome tracking"""
    
    def __init__(self):
        self.client = httpx.AsyncClient(timeout=30.0, headers={"User-Agent": "Mozilla/5.0"})
    
    async def close(self):
        await self.client.aclose()
    
    async def get_price(self, symbol: str, asset_type: str) -> Optional[float]:
        """Get current price for an asset"""
        try:
            if asset_type == "equity":
                return await self._get_stock_price(symbol)
            else:
                return await self._get_crypto_price(symbol)
        except Exception as e:
            logger.warning(f"Price fetch failed for {symbol}: {e}")
            return None
    
    async def _get_stock_price(self, ticker: str) -> Optional[float]:
        """Get stock price from Yahoo Finance"""
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
        response = await self.client.get(url)
        
        if response.status_code == 200:
            data = response.json()
            return data.get("chart", {}).get("result", [{}])[0].get("meta", {}).get("regularMarketPrice")
        return None
    
    async def _get_crypto_price(self, symbol: str) -> Optional[float]:
        """Get crypto price from CoinGecko (free)"""
        # Map symbols to CoinGecko IDs
        id_map = {
            "BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana",
            "AVAX": "avalanche-2", "MATIC": "matic-network",
            "DOT": "polkadot", "ATOM": "cosmos"
        }
        
        coin_id = id_map.get(symbol, symbol.lower())
        url = f"https://api.coingecko.com/api/v3/simple/price?ids={coin_id}&vs_currencies=usd"
        
        response = await self.client.get(url)
        if response.status_code == 200:
            data = response.json()
            return data.get(coin_id, {}).get("usd")
        return None
    
    async def get_historical_price(self, symbol: str, asset_type: str, days_ago: int) -> Optional[float]:
        """Get price from N days ago"""
        try:
            if asset_type == "equity":
                return await self._get_historical_stock_price(symbol, days_ago)
            else:
                return await self._get_historical_crypto_price(symbol, days_ago)
        except Exception as e:
            logger.warning(f"Historical price fetch failed: {e}")
            return None
    
    async def _get_historical_stock_price(self, ticker: str, days_ago: int) -> Optional[float]:
        """Get historical stock price"""
        end = datetime.utcnow()
        start = end - timedelta(days=days_ago + 5)  # Buffer for weekends
        
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
        params = {
            "period1": int(start.timestamp()),
            "period2": int(end.timestamp()),
            "interval": "1d"
        }
        
        response = await self.client.get(url, params=params)
        if response.status_code == 200:
            data = response.json()
            quotes = data.get("chart", {}).get("result", [{}])[0].get("indicators", {}).get("quote", [{}])[0]
            closes = quotes.get("close", [])
            
            if closes and len(closes) >= days_ago:
                return closes[-(days_ago + 1)]  # Price from N days ago
        return None
    
    async def _get_historical_crypto_price(self, symbol: str, days_ago: int) -> Optional[float]:
        """Get historical crypto price from CoinGecko"""
        id_map = {
            "BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana",
            "AVAX": "avalanche-2", "MATIC": "matic-network"
        }
        
        coin_id = id_map.get(symbol, symbol.lower())
        target_date = (datetime.utcnow() - timedelta(days=days_ago)).strftime("%d-%m-%Y")
        
        url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/history"
        params = {"date": target_date}
        
        response = await self.client.get(url, params=params)
        if response.status_code == 200:
            data = response.json()
            return data.get("market_data", {}).get("current_price", {}).get("usd")
        return None


# ─────────────────────────────────────────────────────────────────────────────────
# OUTCOME TRACKER
# ─────────────────────────────────────────────────────────────────────────────────

class OutcomeTracker:
    """
    Tracks prediction outcomes by:
    1. Recording price at signal time
    2. Checking back after 1d, 3d, 7d, 30d
    3. Calculating if prediction was correct
    """
    
    def __init__(self):
        self.price_fetcher = PriceFetcher()
    
    async def close(self):
        await self.price_fetcher.close()
    
    async def record_signal(self, signal_data: Dict) -> int:
        """
        Record a new signal for outcome tracking.
        Returns the prediction_outcome ID.
        """
        session = SessionLocal()
        try:
            # Get current price
            price = await self.price_fetcher.get_price(
                signal_data["asset_symbol"],
                signal_data["asset_type"]
            )
            
            outcome = PredictionOutcome(
                signal_id=signal_data.get("id", 0),
                asset_symbol=signal_data["asset_symbol"],
                asset_type=signal_data["asset_type"],
                signal_score=signal_data["signal_score"],
                signal_type=signal_data["signal_type"],
                insider_score=signal_data.get("insider_score", 0),
                options_score=signal_data.get("options_score", 0),
                whale_score=signal_data.get("whale_score", 0),
                stablecoin_score=signal_data.get("stablecoin_score", 0),
                sentiment_score=signal_data.get("sentiment_score", 0),
                fear_index_score=signal_data.get("fear_index_score", 0),
                dark_pool_score=signal_data.get("dark_pool_score", 0),
                short_interest_score=signal_data.get("short_interest_score", 0),
                social_momentum_score=signal_data.get("social_momentum_score", 0),
                macro_score=signal_data.get("macro_score", 0),
                price_at_signal=price,
                signal_time=datetime.utcnow()
            )
            
            session.add(outcome)
            session.commit()
            session.refresh(outcome)
            
            logger.info(f"Recorded prediction for {signal_data['asset_symbol']} at ${price}")
            return outcome.id
            
        finally:
            session.close()
    
    async def check_outcomes(self):
        """
        Check outcomes for predictions that have matured.
        Should be run daily.
        """
        session = SessionLocal()
        try:
            now = datetime.utcnow()
            
            # Get predictions needing 1-day check
            one_day_ago = now - timedelta(days=1)
            predictions_1d = session.query(PredictionOutcome).filter(
                PredictionOutcome.signal_time <= one_day_ago,
                PredictionOutcome.return_1d.is_(None),
                PredictionOutcome.price_at_signal.isnot(None)
            ).all()
            
            for pred in predictions_1d:
                await self._update_outcome(session, pred, days=1)
            
            # Get predictions needing 3-day check
            three_days_ago = now - timedelta(days=3)
            predictions_3d = session.query(PredictionOutcome).filter(
                PredictionOutcome.signal_time <= three_days_ago,
                PredictionOutcome.return_3d.is_(None),
                PredictionOutcome.price_at_signal.isnot(None)
            ).all()
            
            for pred in predictions_3d:
                await self._update_outcome(session, pred, days=3)
            
            # Get predictions needing 7-day check
            seven_days_ago = now - timedelta(days=7)
            predictions_7d = session.query(PredictionOutcome).filter(
                PredictionOutcome.signal_time <= seven_days_ago,
                PredictionOutcome.return_7d.is_(None),
                PredictionOutcome.price_at_signal.isnot(None)
            ).all()
            
            for pred in predictions_7d:
                await self._update_outcome(session, pred, days=7)
            
            # Get predictions needing 30-day check
            thirty_days_ago = now - timedelta(days=30)
            predictions_30d = session.query(PredictionOutcome).filter(
                PredictionOutcome.signal_time <= thirty_days_ago,
                PredictionOutcome.return_30d.is_(None),
                PredictionOutcome.price_at_signal.isnot(None)
            ).all()
            
            for pred in predictions_30d:
                await self._update_outcome(session, pred, days=30)
            
            session.commit()
            logger.info(f"Checked outcomes: 1d={len(predictions_1d)}, 3d={len(predictions_3d)}, 7d={len(predictions_7d)}, 30d={len(predictions_30d)}")
            
        finally:
            session.close()
    
    async def _update_outcome(self, session, prediction: PredictionOutcome, days: int):
        """Update a single prediction with price outcome"""
        try:
            current_price = await self.price_fetcher.get_price(
                prediction.asset_symbol,
                prediction.asset_type
            )
            
            if current_price and prediction.price_at_signal:
                price_return = ((current_price - prediction.price_at_signal) / prediction.price_at_signal) * 100
                is_correct = price_return > 0
                
                if days == 1:
                    prediction.price_1d_later = current_price
                    prediction.return_1d = price_return
                    prediction.correct_1d = is_correct
                elif days == 3:
                    prediction.price_3d_later = current_price
                    prediction.return_3d = price_return
                    prediction.correct_3d = is_correct
                elif days == 7:
                    prediction.price_7d_later = current_price
                    prediction.return_7d = price_return
                    prediction.correct_7d = is_correct
                elif days == 30:
                    prediction.price_30d_later = current_price
                    prediction.return_30d = price_return
                    prediction.correct_30d = is_correct
                
                prediction.outcome_checked_at = datetime.utcnow()
                
                logger.debug(f"{prediction.asset_symbol} {days}d outcome: {price_return:.2f}% ({'✓' if is_correct else '✗'})")
                
        except Exception as e:
            logger.warning(f"Failed to update outcome for {prediction.asset_symbol}: {e}")


# ─────────────────────────────────────────────────────────────────────────────────
# WEIGHT OPTIMIZER
# ─────────────────────────────────────────────────────────────────────────────────

class WeightOptimizer:
    """
    Analyzes historical predictions and optimizes component weights
    to maximize prediction accuracy and returns.
    """
    
    def __init__(self):
        self.min_predictions = 30  # Minimum sample size before adjusting
    
    def calculate_optimal_weights(self, timeframe: str = "7d") -> Dict[str, float]:
        """
        Calculate optimal weights based on historical performance.
        Uses correlation between component scores and actual returns.
        
        Args:
            timeframe: "1d", "3d", "7d", or "30d"
            
        Returns:
            Dict of optimal weights
        """
        session = SessionLocal()
        try:
            # Get predictions with outcomes
            if timeframe == "1d":
                predictions = session.query(PredictionOutcome).filter(
                    PredictionOutcome.return_1d.isnot(None)
                ).all()
                return_attr = "return_1d"
            elif timeframe == "3d":
                predictions = session.query(PredictionOutcome).filter(
                    PredictionOutcome.return_3d.isnot(None)
                ).all()
                return_attr = "return_3d"
            elif timeframe == "30d":
                predictions = session.query(PredictionOutcome).filter(
                    PredictionOutcome.return_30d.isnot(None)
                ).all()
                return_attr = "return_30d"
            else:  # 7d default
                predictions = session.query(PredictionOutcome).filter(
                    PredictionOutcome.return_7d.isnot(None)
                ).all()
                return_attr = "return_7d"
            
            if len(predictions) < self.min_predictions:
                logger.info(f"Insufficient data for optimization ({len(predictions)} < {self.min_predictions})")
                return self._get_default_weights()
            
            # Calculate correlation of each component with returns
            components = [
                "insider_score", "options_score", "whale_score", "stablecoin_score",
                "sentiment_score", "fear_index_score", "dark_pool_score",
                "short_interest_score", "social_momentum_score", "macro_score"
            ]
            
            correlations = {}
            for component in components:
                scores = [getattr(p, component) for p in predictions]
                returns = [getattr(p, return_attr) for p in predictions]
                
                if len(set(scores)) > 1:  # Need variance
                    corr = self._calculate_correlation(scores, returns)
                    correlations[component] = max(0, corr)  # Only positive correlations
                else:
                    correlations[component] = 0
            
            # Normalize to create weights
            total_corr = sum(correlations.values())
            if total_corr > 0:
                weights = {k: v / total_corr for k, v in correlations.items()}
            else:
                weights = self._get_default_weights()
            
            logger.info(f"Calculated optimal weights from {len(predictions)} predictions")
            logger.info(f"Component correlations: {correlations}")
            
            return weights
            
        finally:
            session.close()
    
    def _calculate_correlation(self, x: List[float], y: List[float]) -> float:
        """Calculate Pearson correlation coefficient"""
        n = len(x)
        if n < 3:
            return 0
        
        mean_x = sum(x) / n
        mean_y = sum(y) / n
        
        numerator = sum((x[i] - mean_x) * (y[i] - mean_y) for i in range(n))
        
        var_x = sum((xi - mean_x) ** 2 for xi in x)
        var_y = sum((yi - mean_y) ** 2 for yi in y)
        
        denominator = (var_x * var_y) ** 0.5
        
        if denominator == 0:
            return 0
        
        return numerator / denominator
    
    def _get_default_weights(self) -> Dict[str, float]:
        """Return default weights when insufficient data"""
        return {
            "insider_score": 0.15,
            "options_score": 0.12,
            "whale_score": 0.15,
            "stablecoin_score": 0.05,
            "sentiment_score": 0.15,
            "fear_index_score": 0.10,
            "dark_pool_score": 0.08,
            "short_interest_score": 0.05,
            "social_momentum_score": 0.10,
            "macro_score": 0.05
        }
    
    def save_learned_weights(self, weights: Dict[str, float], metrics: Dict) -> int:
        """Save new learned weights to database"""
        session = SessionLocal()
        try:
            learned = LearnedWeights(
                insider_weight=weights.get("insider_score", 0.15),
                options_weight=weights.get("options_score", 0.12),
                whale_weight=weights.get("whale_score", 0.15),
                stablecoin_weight=weights.get("stablecoin_score", 0.05),
                sentiment_weight=weights.get("sentiment_score", 0.15),
                fear_index_weight=weights.get("fear_index_score", 0.10),
                dark_pool_weight=weights.get("dark_pool_score", 0.08),
                short_interest_weight=weights.get("short_interest_score", 0.05),
                social_momentum_weight=weights.get("social_momentum_score", 0.10),
                macro_weight=weights.get("macro_score", 0.05),
                accuracy_1d=metrics.get("accuracy_1d"),
                accuracy_7d=metrics.get("accuracy_7d"),
                avg_return=metrics.get("avg_return"),
                sharpe_ratio=metrics.get("sharpe_ratio"),
                predictions_analyzed=metrics.get("predictions_analyzed", 0),
                is_active=False
            )
            
            session.add(learned)
            session.commit()
            session.refresh(learned)
            
            return learned.id
            
        finally:
            session.close()
    
    def activate_weights(self, weights_id: int):
        """Activate a specific weight set"""
        session = SessionLocal()
        try:
            # Deactivate all
            session.query(LearnedWeights).update({"is_active": False})
            
            # Activate selected
            weights = session.query(LearnedWeights).filter(
                LearnedWeights.id == weights_id
            ).first()
            
            if weights:
                weights.is_active = True
                weights.activated_at = datetime.utcnow()
                session.commit()
                logger.info(f"Activated weight set {weights_id}")
            
        finally:
            session.close()
    
    def get_active_weights(self) -> Dict[str, float]:
        """Get currently active weights"""
        session = SessionLocal()
        try:
            active = session.query(LearnedWeights).filter(
                LearnedWeights.is_active == True
            ).first()
            
            if active:
                return {
                    "insider_score": active.insider_weight,
                    "options_score": active.options_weight,
                    "whale_score": active.whale_weight,
                    "stablecoin_score": active.stablecoin_weight,
                    "sentiment_score": active.sentiment_weight,
                    "fear_index_score": active.fear_index_weight,
                    "dark_pool_score": active.dark_pool_weight,
                    "short_interest_score": active.short_interest_weight,
                    "social_momentum_score": active.social_momentum_weight,
                    "macro_score": active.macro_weight
                }
            
            return self._get_default_weights()
            
        finally:
            session.close()


# ─────────────────────────────────────────────────────────────────────────────────
# PERFORMANCE ANALYZER
# ─────────────────────────────────────────────────────────────────────────────────

class PerformanceAnalyzer:
    """
    Analyzes system performance and generates reports.
    """
    
    def get_accuracy_report(self, days: int = 30) -> Dict:
        """
        Generate accuracy report for the last N days.
        """
        session = SessionLocal()
        try:
            cutoff = datetime.utcnow() - timedelta(days=days)
            
            # Get predictions with 7d outcomes
            predictions = session.query(PredictionOutcome).filter(
                PredictionOutcome.signal_time >= cutoff,
                PredictionOutcome.return_7d.isnot(None)
            ).all()
            
            if not predictions:
                return {"error": "No predictions with outcomes in this period"}
            
            # Calculate metrics
            total = len(predictions)
            correct = sum(1 for p in predictions if p.correct_7d)
            accuracy = (correct / total) * 100 if total > 0 else 0
            
            returns = [p.return_7d for p in predictions if p.return_7d is not None]
            avg_return = statistics.mean(returns) if returns else 0
            
            # By signal type
            high_conf = [p for p in predictions if p.signal_type == "high_confidence"]
            high_conf_correct = sum(1 for p in high_conf if p.correct_7d)
            high_conf_accuracy = (high_conf_correct / len(high_conf)) * 100 if high_conf else 0
            
            # By asset type
            equity_preds = [p for p in predictions if p.asset_type == "equity"]
            crypto_preds = [p for p in predictions if p.asset_type == "crypto"]
            
            equity_accuracy = (sum(1 for p in equity_preds if p.correct_7d) / len(equity_preds)) * 100 if equity_preds else 0
            crypto_accuracy = (sum(1 for p in crypto_preds if p.correct_7d) / len(crypto_preds)) * 100 if crypto_preds else 0
            
            # Best and worst
            best_pred = max(predictions, key=lambda p: p.return_7d or 0)
            worst_pred = min(predictions, key=lambda p: p.return_7d or 0)
            
            # Component contribution (which components predicted correctly most often)
            component_performance = self._analyze_component_performance(predictions)
            
            return {
                "period_days": days,
                "total_predictions": total,
                "correct_predictions": correct,
                "accuracy_7d": round(accuracy, 2),
                "avg_return_7d": round(avg_return, 2),
                "high_confidence": {
                    "count": len(high_conf),
                    "accuracy": round(high_conf_accuracy, 2)
                },
                "by_asset_type": {
                    "equity": {"count": len(equity_preds), "accuracy": round(equity_accuracy, 2)},
                    "crypto": {"count": len(crypto_preds), "accuracy": round(crypto_accuracy, 2)}
                },
                "best_prediction": {
                    "asset": best_pred.asset_symbol,
                    "return": round(best_pred.return_7d, 2) if best_pred.return_7d else 0,
                    "score": best_pred.signal_score
                },
                "worst_prediction": {
                    "asset": worst_pred.asset_symbol,
                    "return": round(worst_pred.return_7d, 2) if worst_pred.return_7d else 0,
                    "score": worst_pred.signal_score
                },
                "component_performance": component_performance
            }
            
        finally:
            session.close()
    
    def _analyze_component_performance(self, predictions: List[PredictionOutcome]) -> Dict:
        """Analyze which components predicted correctly"""
        components = [
            ("insider_score", "Insider Activity"),
            ("options_score", "Options Flow"),
            ("whale_score", "Whale Movement"),
            ("sentiment_score", "AI Sentiment"),
            ("fear_index_score", "Fear Index"),
            ("dark_pool_score", "Dark Pool"),
            ("short_interest_score", "Short Interest"),
            ("social_momentum_score", "Social Momentum"),
            ("macro_score", "Macro Indicators")
        ]
        
        results = {}
        
        for attr, name in components:
            # Get predictions where this component scored high (>60)
            high_score_preds = [p for p in predictions if getattr(p, attr, 0) > 60]
            
            if high_score_preds:
                correct = sum(1 for p in high_score_preds if p.correct_7d)
                accuracy = (correct / len(high_score_preds)) * 100
                avg_return = statistics.mean([p.return_7d for p in high_score_preds if p.return_7d is not None]) if high_score_preds else 0
                
                results[name] = {
                    "predictions": len(high_score_preds),
                    "accuracy": round(accuracy, 2),
                    "avg_return": round(avg_return, 2)
                }
            else:
                results[name] = {"predictions": 0, "accuracy": 0, "avg_return": 0}
        
        return results
    
    def log_daily_performance(self):
        """Log daily performance metrics"""
        session = SessionLocal()
        try:
            today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
            
            # Check if already logged today
            existing = session.query(PerformanceLog).filter(
                PerformanceLog.date == today
            ).first()
            
            if existing:
                return
            
            # Get today's signals
            from .database import Signal
            today_signals = session.query(Signal).filter(
                Signal.detected_at >= today
            ).all() if hasattr(Signal, '__table__') else []
            
            # Get 7-day-old predictions that matured today
            seven_days_ago = today - timedelta(days=7)
            matured = session.query(PredictionOutcome).filter(
                PredictionOutcome.signal_time >= seven_days_ago,
                PredictionOutcome.signal_time < seven_days_ago + timedelta(days=1),
                PredictionOutcome.return_7d.isnot(None)
            ).all()
            
            accuracy = (sum(1 for m in matured if m.correct_7d) / len(matured)) * 100 if matured else None
            avg_return = statistics.mean([m.return_7d for m in matured if m.return_7d]) if matured else None
            
            # Get current weights
            optimizer = WeightOptimizer()
            current_weights = optimizer.get_active_weights()
            
            log = PerformanceLog(
                date=today,
                total_signals=len(today_signals) if today_signals else 0,
                high_confidence_signals=sum(1 for s in today_signals if hasattr(s, 'signal_type') and s.signal_type == "high_confidence") if today_signals else 0,
                accuracy_rate=accuracy,
                avg_return=avg_return,
                weights_snapshot=json.dumps(current_weights)
            )
            
            session.add(log)
            session.commit()
            logger.info(f"Logged daily performance for {today.date()}")
            
        finally:
            session.close()
    
    def get_cumulative_stats(self) -> Dict:
        """Get cumulative all-time statistics"""
        session = SessionLocal()
        try:
            # All predictions with outcomes
            all_predictions = session.query(PredictionOutcome).filter(
                PredictionOutcome.return_7d.isnot(None)
            ).all()
            
            if not all_predictions:
                return {"total_predictions": 0, "message": "No predictions with outcomes yet"}
            
            correct = sum(1 for p in all_predictions if p.correct_7d)
            returns = [p.return_7d for p in all_predictions if p.return_7d is not None]
            
            # Calculate Sharpe ratio (simplified)
            if len(returns) > 1:
                avg_return = statistics.mean(returns)
                std_return = statistics.stdev(returns)
                sharpe = (avg_return / std_return) * (252 ** 0.5) if std_return > 0 else 0  # Annualized
            else:
                sharpe = 0
            
            # Profit factor
            gains = [r for r in returns if r > 0]
            losses = [abs(r) for r in returns if r < 0]
            profit_factor = (sum(gains) / sum(losses)) if losses else float('inf')
            
            return {
                "total_predictions": len(all_predictions),
                "correct_predictions": correct,
                "accuracy_rate": round((correct / len(all_predictions)) * 100, 2),
                "avg_return_7d": round(statistics.mean(returns), 2),
                "best_return": round(max(returns), 2),
                "worst_return": round(min(returns), 2),
                "sharpe_ratio": round(sharpe, 2),
                "profit_factor": round(profit_factor, 2) if profit_factor != float('inf') else "∞",
                "win_rate": round((len(gains) / len(returns)) * 100, 2) if returns else 0
            }
            
        finally:
            session.close()
