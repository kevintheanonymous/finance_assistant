# ═══════════════════════════════════════════════════════════════════════════════
# MARKET INTELLIGENCE ENGINE - ADVANCED DATA SOURCES
# ═══════════════════════════════════════════════════════════════════════════════
"""
Additional data vectors for maximum signal accuracy:
- Dark Pool activity
- Short Interest data
- Earnings calendar (blackout detection)
- Congressional trading (STOCK Act)
- Institutional 13F filings
- On-chain analytics (DeFi TVL, NFT volume, gas fees)
- Social momentum (Reddit, StockTwits)
- Macro indicators (Fed funds, yield curve, DXY)
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional
import asyncio

import httpx
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from ..config import APIKeys, Watchlist

# ─────────────────────────────────────────────────────────────────────────────────
# DARK POOL TRACKER
# ─────────────────────────────────────────────────────────────────────────────────

class DarkPoolTracker:
    """
    Tracks dark pool (off-exchange) trading activity.
    Large dark pool prints often precede significant moves.
    
    Data sources:
    - FINRA ADF (free, delayed)
    - Unusual Whales Dark Pool flow (premium)
    """
    
    def __init__(self):
        self.client = httpx.AsyncClient(timeout=30.0)
    
    async def close(self):
        await self.client.aclose()
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def fetch_dark_pool_activity(self, ticker: str) -> Dict:
        """
        Fetch dark pool activity for a ticker.
        Returns volume, sentiment (buy/sell ratio), and large block trades.
        """
        try:
            # Try Unusual Whales dark pool endpoint if available
            if APIKeys.UNUSUAL_WHALES:
                headers = {"Authorization": f"Bearer {APIKeys.UNUSUAL_WHALES}"}
                url = f"https://api.unusualwhales.com/api/darkpool/{ticker}"
                
                response = await self.client.get(url, headers=headers)
                if response.status_code == 200:
                    data = response.json()
                    return self._parse_unusual_whales_dp(data)
            
            # Fallback to FINRA ADF (public, delayed data)
            return await self._fetch_finra_data(ticker)
            
        except Exception as e:
            logger.warning(f"Dark pool fetch failed for {ticker}: {e}")
            return {"score": 50, "volume": 0, "sentiment": "neutral"}
    
    def _parse_unusual_whales_dp(self, data: Dict) -> Dict:
        """Parse Unusual Whales dark pool response"""
        dp_volume = data.get("total_volume", 0)
        avg_volume = data.get("avg_30d_volume", 1)
        buy_volume = data.get("buy_volume", 0)
        sell_volume = data.get("sell_volume", 0)
        
        # Calculate metrics
        volume_ratio = dp_volume / max(avg_volume, 1)
        
        if buy_volume + sell_volume > 0:
            buy_ratio = buy_volume / (buy_volume + sell_volume)
        else:
            buy_ratio = 0.5
        
        # Score: high volume + bullish sentiment = high score
        volume_score = min(100, volume_ratio * 30)
        sentiment_score = buy_ratio * 100
        
        combined_score = (volume_score * 0.4) + (sentiment_score * 0.6)
        
        return {
            "score": combined_score,
            "volume": dp_volume,
            "volume_ratio": volume_ratio,
            "buy_ratio": buy_ratio,
            "sentiment": "bullish" if buy_ratio > 0.55 else "bearish" if buy_ratio < 0.45 else "neutral",
            "large_prints": data.get("block_trades", [])
        }
    
    async def _fetch_finra_data(self, ticker: str) -> Dict:
        """Fetch from FINRA ADF (free but limited)"""
        # FINRA data requires registration - return mock for now
        return {"score": 50, "volume": 0, "sentiment": "neutral", "source": "unavailable"}
    
    async def get_component_scores(self) -> Dict[str, float]:
        """Get dark pool scores for all equities"""
        scores = {}
        for ticker in Watchlist.EQUITIES:
            try:
                await asyncio.sleep(0.2)  # Rate limiting
                data = await self.fetch_dark_pool_activity(ticker)
                scores[ticker] = data.get("score", 50)
            except Exception as e:
                logger.warning(f"Dark pool score failed for {ticker}: {e}")
                scores[ticker] = 50
        return scores


# ─────────────────────────────────────────────────────────────────────────────────
# SHORT INTEREST TRACKER
# ─────────────────────────────────────────────────────────────────────────────────

class ShortInterestTracker:
    """
    Tracks short interest and days-to-cover.
    High short interest + positive catalyst = potential squeeze.
    """
    
    def __init__(self):
        self.client = httpx.AsyncClient(timeout=30.0)
    
    async def close(self):
        await self.client.aclose()
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def fetch_short_interest(self, ticker: str) -> Dict:
        """Fetch short interest data"""
        try:
            if APIKeys.FINNHUB:
                params = {"symbol": ticker, "token": APIKeys.FINNHUB}
                url = "https://finnhub.io/api/v1/stock/short-interest"
                
                response = await self.client.get(url, params=params)
                if response.status_code == 200:
                    data = response.json()
                    return self._parse_short_interest(data, ticker)
            
            return {"score": 50, "short_ratio": 0, "days_to_cover": 0}
            
        except Exception as e:
            logger.warning(f"Short interest fetch failed for {ticker}: {e}")
            return {"score": 50, "short_ratio": 0, "days_to_cover": 0}
    
    def _parse_short_interest(self, data: Dict, ticker: str) -> Dict:
        """Parse Finnhub short interest response"""
        if not data.get("data"):
            return {"score": 50, "short_ratio": 0, "days_to_cover": 0}
        
        latest = data["data"][0] if data["data"] else {}
        
        short_interest = latest.get("shortInterest", 0)
        avg_volume = latest.get("avgVolume", 1)
        
        # Days to cover calculation
        days_to_cover = short_interest / max(avg_volume, 1)
        
        # Short ratio (% of float)
        short_ratio = latest.get("shortPercentFloat", 0) * 100
        
        # High short interest is a contrarian bullish indicator
        # (potential squeeze if stock moves up)
        if short_ratio > 20:
            score = 80 + min(20, (short_ratio - 20))  # Extra points for extreme shorts
        elif short_ratio > 10:
            score = 60 + (short_ratio - 10) * 2
        else:
            score = 50 + short_ratio
        
        return {
            "score": min(100, score),
            "short_ratio": short_ratio,
            "days_to_cover": days_to_cover,
            "short_interest_shares": short_interest,
            "squeeze_potential": "high" if short_ratio > 20 and days_to_cover > 5 else "moderate" if short_ratio > 10 else "low"
        }
    
    async def get_component_scores(self) -> Dict[str, float]:
        """Get short interest scores for all equities"""
        scores = {}
        for ticker in Watchlist.EQUITIES:
            try:
                await asyncio.sleep(0.2)
                data = await self.fetch_short_interest(ticker)
                scores[ticker] = data.get("score", 50)
            except Exception:
                scores[ticker] = 50
        return scores


# ─────────────────────────────────────────────────────────────────────────────────
# CONGRESSIONAL TRADING TRACKER (STOCK Act)
# ─────────────────────────────────────────────────────────────────────────────────

class CongressionalTracker:
    """
    Tracks Congressional trading disclosures.
    Politicians often have early access to policy information.
    Source: house.gov / senate.gov / quiverquant.com
    """
    
    def __init__(self):
        self.client = httpx.AsyncClient(timeout=30.0)
    
    async def close(self):
        await self.client.aclose()
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def fetch_congressional_trades(self, days: int = 30) -> List[Dict]:
        """
        Fetch recent Congressional trading activity.
        Uses QuiverQuant free endpoint.
        """
        try:
            # QuiverQuant has a free API for congressional trades
            url = "https://api.quiverquant.com/beta/live/congresstrading"
            headers = {"accept": "application/json"}
            
            response = await self.client.get(url, headers=headers)
            if response.status_code == 200:
                trades = response.json()
                
                # Filter to recent trades
                cutoff = datetime.utcnow() - timedelta(days=days)
                recent = []
                
                for trade in trades[:100]:  # Limit to most recent
                    trade_date = datetime.strptime(trade.get("TransactionDate", "2000-01-01"), "%Y-%m-%d")
                    if trade_date >= cutoff:
                        recent.append({
                            "ticker": trade.get("Ticker", "").upper(),
                            "politician": trade.get("Representative", "Unknown"),
                            "party": trade.get("Party", ""),
                            "transaction": trade.get("Transaction", "").lower(),
                            "amount": trade.get("Range", ""),
                            "date": trade_date
                        })
                
                return recent
            
            return []
            
        except Exception as e:
            logger.warning(f"Congressional trades fetch failed: {e}")
            return []
    
    async def get_component_scores(self) -> Dict[str, float]:
        """Get congressional trading scores by ticker"""
        scores = {}
        
        try:
            trades = await self.fetch_congressional_trades(days=30)
            
            # Count buys vs sells per ticker
            ticker_activity = {}
            for trade in trades:
                ticker = trade.get("ticker")
                if not ticker or ticker not in Watchlist.EQUITIES:
                    continue
                
                if ticker not in ticker_activity:
                    ticker_activity[ticker] = {"buys": 0, "sells": 0}
                
                if "purchase" in trade.get("transaction", ""):
                    ticker_activity[ticker]["buys"] += 1
                elif "sale" in trade.get("transaction", ""):
                    ticker_activity[ticker]["sells"] += 1
            
            # Calculate scores
            for ticker in Watchlist.EQUITIES:
                if ticker in ticker_activity:
                    buys = ticker_activity[ticker]["buys"]
                    sells = ticker_activity[ticker]["sells"]
                    
                    if buys + sells > 0:
                        buy_ratio = buys / (buys + sells)
                        # More congressional buys = higher score
                        score = 50 + (buy_ratio - 0.5) * 100
                        # Bonus for high activity
                        if buys + sells >= 3:
                            score += 10
                        scores[ticker] = min(100, max(0, score))
                    else:
                        scores[ticker] = 50
                else:
                    scores[ticker] = 50  # No data = neutral
            
        except Exception as e:
            logger.error(f"Congressional scoring failed: {e}")
            for ticker in Watchlist.EQUITIES:
                scores[ticker] = 50
        
        return scores


# ─────────────────────────────────────────────────────────────────────────────────
# ON-CHAIN ANALYTICS (DeFi, NFT, Gas)
# ─────────────────────────────────────────────────────────────────────────────────

class OnChainAnalytics:
    """
    Deep on-chain analytics for crypto:
    - DeFi Total Value Locked (TVL)
    - NFT trading volume
    - Gas fees (network activity)
    - Active addresses
    - Staking ratios
    """
    
    def __init__(self):
        self.client = httpx.AsyncClient(timeout=30.0)
    
    async def close(self):
        await self.client.aclose()
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def fetch_defi_tvl(self) -> Dict:
        """Fetch DeFi TVL from DeFiLlama (free API)"""
        try:
            url = "https://api.llama.fi/protocols"
            response = await self.client.get(url)
            
            if response.status_code == 200:
                data = response.json()
                
                total_tvl = sum(p.get("tvl", 0) for p in data if p.get("tvl"))
                
                # Top chains TVL
                chain_tvl = {}
                for protocol in data[:100]:  # Top protocols
                    chain = protocol.get("chain", "Other")
                    if chain not in chain_tvl:
                        chain_tvl[chain] = 0
                    chain_tvl[chain] += protocol.get("tvl", 0)
                
                return {
                    "total_tvl_usd": total_tvl,
                    "chain_breakdown": chain_tvl,
                    "source": "defillama"
                }
            
            return {"total_tvl_usd": 0, "source": "error"}
            
        except Exception as e:
            logger.warning(f"DeFi TVL fetch failed: {e}")
            return {"total_tvl_usd": 0, "source": "error"}
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def fetch_gas_fees(self) -> Dict:
        """Fetch Ethereum gas fees (activity indicator)"""
        try:
            url = "https://api.etherscan.io/api?module=gastracker&action=gasoracle"
            response = await self.client.get(url)
            
            if response.status_code == 200:
                data = response.json()
                result = data.get("result", {})
                
                gas_price = float(result.get("ProposeGasPrice", 30))
                
                # High gas = high activity = bullish
                if gas_price > 100:
                    score = 80
                elif gas_price > 50:
                    score = 65
                elif gas_price > 20:
                    score = 50
                else:
                    score = 40  # Low activity
                
                return {
                    "gas_price_gwei": gas_price,
                    "activity_score": score,
                    "activity_level": "high" if gas_price > 50 else "moderate" if gas_price > 20 else "low"
                }
            
            return {"gas_price_gwei": 30, "activity_score": 50}
            
        except Exception as e:
            logger.warning(f"Gas fee fetch failed: {e}")
            return {"gas_price_gwei": 30, "activity_score": 50}
    
    async def get_comprehensive_onchain(self) -> Dict:
        """Get all on-chain metrics"""
        tvl_data, gas_data = await asyncio.gather(
            self.fetch_defi_tvl(),
            self.fetch_gas_fees()
        )
        
        # Combined score
        gas_score = gas_data.get("activity_score", 50)
        
        # TVL trend would need historical data - for now use gas as proxy
        combined_score = gas_score
        
        return {
            "defi_tvl": tvl_data,
            "gas_fees": gas_data,
            "combined_score": combined_score
        }
    
    async def get_component_scores(self) -> Dict[str, float]:
        """Get on-chain scores for crypto assets"""
        onchain = await self.get_comprehensive_onchain()
        score = onchain.get("combined_score", 50)
        
        # Apply same score to all crypto (network-level metric)
        return {symbol: score for symbol in Watchlist.CRYPTO}


# ─────────────────────────────────────────────────────────────────────────────────
# SOCIAL MOMENTUM TRACKER
# ─────────────────────────────────────────────────────────────────────────────────

class SocialMomentumTracker:
    """
    Tracks social media momentum:
    - Reddit mentions (r/wallstreetbets, r/stocks, r/cryptocurrency)
    - StockTwits sentiment
    - Twitter/X velocity
    """
    
    def __init__(self):
        self.client = httpx.AsyncClient(timeout=30.0)
    
    async def close(self):
        await self.client.aclose()
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def fetch_reddit_mentions(self, ticker: str) -> Dict:
        """
        Fetch Reddit mention data.
        Uses free APIs like tradestie or apewisdom.
        """
        try:
            # ApeWisdom tracks WSB mentions (free)
            url = f"https://apewisdom.io/api/v1.0/filter/all-stocks/{ticker}"
            
            response = await self.client.get(url)
            if response.status_code == 200:
                data = response.json()
                
                mentions = data.get("mentions", 0)
                rank = data.get("rank", 999)
                upvotes = data.get("upvotes", 0)
                
                # Score based on rank and mentions
                if rank <= 10:
                    score = 90 + (10 - rank)
                elif rank <= 50:
                    score = 70 + (50 - rank) * 0.4
                elif rank <= 100:
                    score = 50 + (100 - rank) * 0.4
                else:
                    score = max(30, 50 - (rank - 100) * 0.1)
                
                return {
                    "score": min(100, score),
                    "mentions_24h": mentions,
                    "rank": rank,
                    "upvotes": upvotes,
                    "trending": rank <= 25
                }
            
            return {"score": 50, "mentions_24h": 0, "rank": 999, "trending": False}
            
        except Exception as e:
            logger.warning(f"Reddit mentions fetch failed for {ticker}: {e}")
            return {"score": 50, "mentions_24h": 0, "rank": 999, "trending": False}
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def fetch_stocktwits_sentiment(self, ticker: str) -> Dict:
        """Fetch StockTwits sentiment"""
        try:
            url = f"https://api.stocktwits.com/api/2/streams/symbol/{ticker}.json"
            
            response = await self.client.get(url)
            if response.status_code == 200:
                data = response.json()
                
                messages = data.get("messages", [])
                
                # Count sentiment
                bullish = sum(1 for m in messages if m.get("entities", {}).get("sentiment", {}).get("basic") == "Bullish")
                bearish = sum(1 for m in messages if m.get("entities", {}).get("sentiment", {}).get("basic") == "Bearish")
                
                total = bullish + bearish
                if total > 0:
                    bullish_ratio = bullish / total
                    score = bullish_ratio * 100
                else:
                    score = 50
                
                return {
                    "score": score,
                    "bullish_count": bullish,
                    "bearish_count": bearish,
                    "bullish_ratio": bullish_ratio if total > 0 else 0.5,
                    "message_count": len(messages)
                }
            
            return {"score": 50, "bullish_ratio": 0.5}
            
        except Exception as e:
            logger.warning(f"StockTwits fetch failed for {ticker}: {e}")
            return {"score": 50, "bullish_ratio": 0.5}
    
    async def get_social_momentum(self, ticker: str) -> Dict:
        """Get combined social momentum score"""
        reddit, stocktwits = await asyncio.gather(
            self.fetch_reddit_mentions(ticker),
            self.fetch_stocktwits_sentiment(ticker)
        )
        
        # Weighted average
        reddit_weight = 0.6 if reddit.get("trending") else 0.4
        stocktwits_weight = 1 - reddit_weight
        
        combined_score = (reddit["score"] * reddit_weight) + (stocktwits["score"] * stocktwits_weight)
        
        return {
            "combined_score": combined_score,
            "reddit": reddit,
            "stocktwits": stocktwits,
            "is_trending": reddit.get("trending", False)
        }
    
    async def get_component_scores(self) -> Dict[str, float]:
        """Get social momentum scores for all equities"""
        scores = {}
        for ticker in Watchlist.EQUITIES:
            try:
                await asyncio.sleep(0.3)  # Rate limiting
                data = await self.get_social_momentum(ticker)
                scores[ticker] = data.get("combined_score", 50)
            except Exception:
                scores[ticker] = 50
        return scores


# ─────────────────────────────────────────────────────────────────────────────────
# MACRO INDICATORS
# ─────────────────────────────────────────────────────────────────────────────────

class MacroIndicators:
    """
    Tracks macro-economic indicators:
    - Dollar Index (DXY)
    - Treasury yields
    - Fed funds rate expectations
    - Yield curve (inversion detection)
    """
    
    def __init__(self):
        self.client = httpx.AsyncClient(timeout=30.0)
    
    async def close(self):
        await self.client.aclose()
    
    async def fetch_dxy(self) -> Dict:
        """Fetch Dollar Index"""
        try:
            # Use Yahoo Finance
            url = "https://query1.finance.yahoo.com/v8/finance/chart/DX-Y.NYB"
            response = await self.client.get(url, headers={"User-Agent": "Mozilla/5.0"})
            
            if response.status_code == 200:
                data = response.json()
                result = data.get("chart", {}).get("result", [{}])[0]
                meta = result.get("meta", {})
                
                current = meta.get("regularMarketPrice", 100)
                previous = meta.get("previousClose", 100)
                
                change_pct = ((current - previous) / previous) * 100
                
                # Strong dollar is generally bearish for risk assets
                # So we invert: weak dollar = high score
                if change_pct < -0.5:
                    score = 80  # Dollar weakening = bullish for risk
                elif change_pct < 0:
                    score = 60
                elif change_pct < 0.5:
                    score = 40
                else:
                    score = 20  # Dollar strengthening = bearish for risk
                
                return {
                    "value": current,
                    "change_pct": change_pct,
                    "score": score,
                    "direction": "weakening" if change_pct < 0 else "strengthening"
                }
            
            return {"value": 100, "score": 50}
            
        except Exception as e:
            logger.warning(f"DXY fetch failed: {e}")
            return {"value": 100, "score": 50}
    
    async def fetch_treasury_yields(self) -> Dict:
        """Fetch Treasury yields (10Y, 2Y) for yield curve"""
        try:
            # Fetch 10Y
            url_10y = "https://query1.finance.yahoo.com/v8/finance/chart/%5ETNX"
            response_10y = await self.client.get(url_10y, headers={"User-Agent": "Mozilla/5.0"})
            
            # Fetch 2Y
            url_2y = "https://query1.finance.yahoo.com/v8/finance/chart/%5ETWO"
            response_2y = await self.client.get(url_2y, headers={"User-Agent": "Mozilla/5.0"})
            
            yield_10y = 4.0
            yield_2y = 4.5
            
            if response_10y.status_code == 200:
                data = response_10y.json()
                yield_10y = data.get("chart", {}).get("result", [{}])[0].get("meta", {}).get("regularMarketPrice", 4.0)
            
            if response_2y.status_code == 200:
                data = response_2y.json()
                yield_2y = data.get("chart", {}).get("result", [{}])[0].get("meta", {}).get("regularMarketPrice", 4.5)
            
            # Yield curve spread
            spread = yield_10y - yield_2y
            
            # Inverted yield curve is bearish signal
            if spread < -0.5:
                score = 20  # Deeply inverted = very bearish
            elif spread < 0:
                score = 35  # Inverted = bearish
            elif spread < 0.5:
                score = 50  # Flat = neutral
            elif spread < 1.0:
                score = 65  # Normal = slightly bullish
            else:
                score = 80  # Steep = bullish
            
            return {
                "yield_10y": yield_10y,
                "yield_2y": yield_2y,
                "spread": spread,
                "curve_status": "inverted" if spread < 0 else "flat" if spread < 0.5 else "normal",
                "score": score
            }
            
        except Exception as e:
            logger.warning(f"Treasury yields fetch failed: {e}")
            return {"spread": 0, "curve_status": "unknown", "score": 50}
    
    async def get_macro_analysis(self) -> Dict:
        """Get comprehensive macro analysis"""
        dxy, yields = await asyncio.gather(
            self.fetch_dxy(),
            self.fetch_treasury_yields()
        )
        
        # Combined score (equal weight)
        combined_score = (dxy["score"] + yields["score"]) / 2
        
        return {
            "dxy": dxy,
            "treasury": yields,
            "combined_score": combined_score,
            "regime": "risk_on" if combined_score > 60 else "risk_off" if combined_score < 40 else "neutral"
        }
    
    async def get_component_scores(self) -> Dict[str, float]:
        """Get macro scores (applies to all assets)"""
        macro = await self.get_macro_analysis()
        score = macro.get("combined_score", 50)
        
        # Same macro score for equities and crypto
        scores = {}
        for ticker in Watchlist.EQUITIES:
            scores[ticker] = score
        for symbol in Watchlist.CRYPTO:
            scores[symbol] = score
        
        return scores
