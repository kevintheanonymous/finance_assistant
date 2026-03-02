# ═══════════════════════════════════════════════════════════════════════════════
# MARKET INTELLIGENCE ENGINE - SENTIMENT ANALYZER
# ═══════════════════════════════════════════════════════════════════════════════
"""
AI-powered sentiment analysis using OpenAI GPT-4.
Analyzes news headlines and social media for bullish/bearish signals.
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional
import asyncio
import json

import httpx
from openai import AsyncOpenAI
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from ..config import APIKeys, Watchlist

# ─────────────────────────────────────────────────────────────────────────────────
# SENTIMENT CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────────

# Finnhub news endpoint
FINNHUB_NEWS_URL = "https://finnhub.io/api/v1/company-news"
FINNHUB_GENERAL_NEWS_URL = "https://finnhub.io/api/v1/news"

# Sentiment classification prompt
SENTIMENT_PROMPT = """You are a financial sentiment analyzer. Analyze the following news headlines/texts about {asset} and classify the overall sentiment.

Headlines/Texts:
{texts}

Respond with ONLY a JSON object in this exact format:
{{
    "sentiment": "bullish" | "bearish" | "neutral",
    "confidence": 0-100,
    "key_factors": ["factor1", "factor2"],
    "summary": "One sentence summary"
}}

Rules:
- "bullish": Positive outlook, buying signals, good news
- "bearish": Negative outlook, selling signals, bad news  
- "neutral": Mixed or no clear direction
- confidence: How certain you are (0-100)
- Be objective. Ignore hype. Focus on material facts."""

# ─────────────────────────────────────────────────────────────────────────────────
# SENTIMENT ANALYZER CLASS
# ─────────────────────────────────────────────────────────────────────────────────

class SentimentAnalyzer:
    """
    Analyzes news and social sentiment using AI.
    
    How it works:
    1. Fetch recent news headlines for each asset
    2. Feed headlines to GPT-4 for classification
    3. Parse response into structured sentiment data
    4. Score based on sentiment + confidence
    """
    
    def __init__(self):
        self.openai_client = AsyncOpenAI(api_key=APIKeys.OPENAI) if APIKeys.OPENAI else None
        self.http_client = httpx.AsyncClient(timeout=30.0)
        self.finnhub_key = APIKeys.FINNHUB
        
        # Cache to avoid re-analyzing same news
        self._sentiment_cache: Dict[str, Dict] = {}
        self._cache_ttl_hours = 1
    
    async def close(self):
        """Close clients"""
        await self.http_client.aclose()
        if self.openai_client:
            await self.openai_client.close()
    
    # ─────────────────────────────────────────────────────────────────────────────
    # NEWS FETCHING
    # ─────────────────────────────────────────────────────────────────────────────
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def fetch_news(self, ticker: str, days: int = 3) -> List[str]:
        """
        Fetch recent news headlines for a ticker.
        
        Args:
            ticker: Stock/crypto symbol
            days: Number of days to look back
            
        Returns:
            List of headline strings
        """
        if not self.finnhub_key:
            logger.warning(f"No Finnhub API key, using mock news for {ticker}")
            return self._get_mock_news(ticker)
        
        try:
            # Calculate date range
            end_date = datetime.utcnow()
            start_date = end_date - timedelta(days=days)
            
            params = {
                "symbol": ticker,
                "from": start_date.strftime("%Y-%m-%d"),
                "to": end_date.strftime("%Y-%m-%d"),
                "token": self.finnhub_key
            }
            
            response = await self.http_client.get(FINNHUB_NEWS_URL, params=params)
            response.raise_for_status()
            
            articles = response.json()
            
            # Extract headlines
            headlines = []
            for article in articles[:20]:  # Limit to 20 most recent
                headline = article.get("headline", "")
                summary = article.get("summary", "")
                if headline:
                    headlines.append(headline)
                if summary and len(summary) < 500:
                    headlines.append(summary)
            
            logger.debug(f"Fetched {len(headlines)} news items for {ticker}")
            return headlines
            
        except Exception as e:
            logger.warning(f"Error fetching news for {ticker}: {e}")
            return []
    
    async def fetch_crypto_news(self, symbol: str) -> List[str]:
        """
        Fetch crypto news (uses general news endpoint with filtering).
        
        Args:
            symbol: Crypto symbol (BTC, ETH, etc.)
            
        Returns:
            List of relevant headlines
        """
        if not self.finnhub_key:
            return self._get_mock_news(symbol)
        
        try:
            params = {
                "category": "crypto",
                "token": self.finnhub_key
            }
            
            response = await self.http_client.get(FINNHUB_GENERAL_NEWS_URL, params=params)
            response.raise_for_status()
            
            articles = response.json()
            
            # Filter for relevant symbol
            symbol_lower = symbol.lower()
            name_map = {"BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana"}
            name = name_map.get(symbol, symbol_lower)
            
            headlines = []
            for article in articles:
                headline = article.get("headline", "").lower()
                summary = article.get("summary", "").lower()
                
                if symbol_lower in headline or name in headline or \
                   symbol_lower in summary or name in summary:
                    headlines.append(article.get("headline", ""))
                    if article.get("summary"):
                        headlines.append(article.get("summary"))
            
            return headlines[:20]
            
        except Exception as e:
            logger.warning(f"Error fetching crypto news: {e}")
            return []
    
    # ─────────────────────────────────────────────────────────────────────────────
    # AI SENTIMENT ANALYSIS
    # ─────────────────────────────────────────────────────────────────────────────
    
    @retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=2, max=5))
    async def analyze_sentiment(self, asset: str, texts: List[str]) -> Dict:
        """
        Analyze sentiment of texts using GPT-4.
        
        Args:
            asset: Asset symbol being analyzed
            texts: List of news headlines/summaries
            
        Returns:
            Sentiment analysis result dict
        """
        if not texts:
            return {
                "sentiment": "neutral",
                "confidence": 0,
                "key_factors": [],
                "summary": "No news available",
                "score": 50
            }
        
        # Check cache
        cache_key = f"{asset}_{hash(tuple(texts[:5]))}"
        if cache_key in self._sentiment_cache:
            cached = self._sentiment_cache[cache_key]
            if (datetime.utcnow() - cached["timestamp"]).seconds < self._cache_ttl_hours * 3600:
                return cached["data"]
        
        if not self.openai_client:
            logger.warning("OpenAI not configured, using rule-based sentiment")
            return self._rule_based_sentiment(texts)
        
        try:
            # Prepare prompt
            texts_formatted = "\n".join([f"- {t}" for t in texts[:15]])  # Limit for token efficiency
            prompt = SENTIMENT_PROMPT.format(asset=asset, texts=texts_formatted)
            
            # Call GPT-4
            response = await self.openai_client.chat.completions.create(
                model="gpt-4-turbo-preview",
                messages=[
                    {"role": "system", "content": "You are a precise financial sentiment analyzer. Respond only with valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=300
            )
            
            # Parse response
            content = response.choices[0].message.content.strip()
            
            # Handle potential markdown code blocks
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            
            result = json.loads(content)
            
            # Calculate score from sentiment + confidence
            score = self._sentiment_to_score(result["sentiment"], result["confidence"])
            result["score"] = score
            
            # Cache result
            self._sentiment_cache[cache_key] = {
                "data": result,
                "timestamp": datetime.utcnow()
            }
            
            logger.debug(f"Sentiment for {asset}: {result['sentiment']} (confidence: {result['confidence']})")
            return result
            
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse GPT response: {e}")
            return self._rule_based_sentiment(texts)
        except Exception as e:
            logger.error(f"GPT sentiment analysis failed: {e}")
            return self._rule_based_sentiment(texts)
    
    def _sentiment_to_score(self, sentiment: str, confidence: int) -> float:
        """
        Convert sentiment classification to numeric score.
        
        Args:
            sentiment: "bullish", "bearish", or "neutral"
            confidence: 0-100
            
        Returns:
            Score from 0-100 where 100 = very bullish
        """
        base_scores = {
            "bullish": 100,
            "neutral": 50,
            "bearish": 0
        }
        
        base = base_scores.get(sentiment.lower(), 50)
        
        # Adjust based on confidence (less confident = closer to neutral)
        confidence_factor = confidence / 100
        adjusted = 50 + (base - 50) * confidence_factor
        
        return adjusted
    
    def _rule_based_sentiment(self, texts: List[str]) -> Dict:
        """
        Simple keyword-based sentiment when AI not available.
        
        Args:
            texts: List of text to analyze
            
        Returns:
            Sentiment result dict
        """
        bullish_words = [
            "surge", "soar", "rally", "gain", "jump", "rise", "bullish",
            "growth", "record", "high", "buy", "upgrade", "beat", "exceed",
            "positive", "optimistic", "breakout", "momentum", "strong"
        ]
        
        bearish_words = [
            "drop", "fall", "crash", "plunge", "decline", "bearish",
            "loss", "low", "sell", "downgrade", "miss", "weak",
            "negative", "concern", "fear", "risk", "warning", "trouble"
        ]
        
        text_combined = " ".join(texts).lower()
        
        bullish_count = sum(1 for word in bullish_words if word in text_combined)
        bearish_count = sum(1 for word in bearish_words if word in text_combined)
        
        total = bullish_count + bearish_count
        if total == 0:
            sentiment = "neutral"
            confidence = 30
        elif bullish_count > bearish_count * 1.5:
            sentiment = "bullish"
            confidence = min(80, 40 + (bullish_count - bearish_count) * 5)
        elif bearish_count > bullish_count * 1.5:
            sentiment = "bearish"
            confidence = min(80, 40 + (bearish_count - bullish_count) * 5)
        else:
            sentiment = "neutral"
            confidence = 50
        
        score = self._sentiment_to_score(sentiment, confidence)
        
        return {
            "sentiment": sentiment,
            "confidence": confidence,
            "key_factors": [f"Rule-based: {bullish_count} bullish, {bearish_count} bearish words"],
            "summary": f"Basic analysis found {sentiment} sentiment",
            "score": score
        }
    
    # ─────────────────────────────────────────────────────────────────────────────
    # BATCH ANALYSIS
    # ─────────────────────────────────────────────────────────────────────────────
    
    async def analyze_all_assets(self) -> Dict[str, Dict]:
        """
        Analyze sentiment for all watched assets.
        
        Returns:
            Dict mapping symbol to sentiment data
        """
        results = {}
        
        logger.info("Running sentiment analysis for all assets...")
        
        # Analyze equities
        for ticker in Watchlist.EQUITIES:
            try:
                await asyncio.sleep(0.5)  # Rate limiting
                news = await self.fetch_news(ticker)
                sentiment = await self.analyze_sentiment(ticker, news)
                results[ticker] = sentiment
            except Exception as e:
                logger.warning(f"Sentiment analysis failed for {ticker}: {e}")
                results[ticker] = {"sentiment": "neutral", "confidence": 0, "score": 50}
        
        # Analyze crypto
        for symbol in Watchlist.CRYPTO:
            try:
                await asyncio.sleep(0.5)
                news = await self.fetch_crypto_news(symbol)
                sentiment = await self.analyze_sentiment(symbol, news)
                results[symbol] = sentiment
            except Exception as e:
                logger.warning(f"Sentiment analysis failed for {symbol}: {e}")
                results[symbol] = {"sentiment": "neutral", "confidence": 0, "score": 50}
        
        return results
    
    # ─────────────────────────────────────────────────────────────────────────────
    # SCORING METHOD
    # ─────────────────────────────────────────────────────────────────────────────
    
    async def get_component_scores(self) -> Dict[str, float]:
        """
        Get sentiment scores for all watched assets.
        
        Returns:
            Dict mapping symbol to score (0-100)
        """
        all_sentiment = await self.analyze_all_assets()
        return {symbol: data["score"] for symbol, data in all_sentiment.items()}
    
    # ─────────────────────────────────────────────────────────────────────────────
    # MOCK DATA
    # ─────────────────────────────────────────────────────────────────────────────
    
    def _get_mock_news(self, symbol: str) -> List[str]:
        """Generate mock news for testing"""
        import random
        
        bullish_templates = [
            f"{symbol} sees strong institutional interest as buying volume increases",
            f"Analysts upgrade {symbol} citing growth potential",
            f"{symbol} breaks resistance level, momentum traders pile in",
            f"Major fund increases {symbol} position by 15%"
        ]
        
        bearish_templates = [
            f"{symbol} faces headwinds as sector rotation continues",
            f"Concerns mount over {symbol}'s valuation",
            f"{symbol} misses analyst expectations in latest report"
        ]
        
        neutral_templates = [
            f"{symbol} trades sideways as market awaits catalyst",
            f"Mixed signals for {symbol} in current market environment"
        ]
        
        # Randomly select news with slight bullish bias (60/25/15)
        news = []
        for _ in range(5):
            r = random.random()
            if r < 0.6:
                news.append(random.choice(bullish_templates))
            elif r < 0.85:
                news.append(random.choice(bearish_templates))
            else:
                news.append(random.choice(neutral_templates))
        
        return news
