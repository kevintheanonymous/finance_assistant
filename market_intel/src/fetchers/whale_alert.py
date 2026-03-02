# ═══════════════════════════════════════════════════════════════════════════════
# MARKET INTELLIGENCE ENGINE - WHALE ALERT FETCHER
# ═══════════════════════════════════════════════════════════════════════════════
"""
Fetches large crypto transactions from Whale Alert API.
Tracks exchange inflows/outflows to detect accumulation patterns.
"""

from datetime import datetime, timedelta
from typing import List, Dict, Optional

import httpx
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from ..config import APIKeys, Thresholds, Watchlist
from ..database import DatabaseOperations

# ─────────────────────────────────────────────────────────────────────────────────
# WHALE ALERT CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────────
WHALE_ALERT_API_URL = "https://api.whale-alert.io/v1/transactions"

# Known exchange wallets (simplified - in production use their full database)
KNOWN_EXCHANGES = [
    "binance", "coinbase", "kraken", "bitfinex", "huobi", "okex", "kucoin",
    "ftx", "bybit", "bitstamp", "gemini", "crypto.com", "bittrex"
]

# ─────────────────────────────────────────────────────────────────────────────────
# WHALE ALERT FETCHER CLASS
# ─────────────────────────────────────────────────────────────────────────────────

class WhaleAlertFetcher:
    """
    Fetches whale transactions and calculates exchange flow metrics.
    
    How it works:
    1. Polls Whale Alert API for transactions above threshold
    2. Classifies each transaction as inflow, outflow, or whale transfer
    3. Stores in database for flow calculation
    4. Calculates net exchange flow to detect accumulation
    """
    
    def __init__(self):
        self.api_key = APIKeys.WHALE_ALERT
        self.client = httpx.AsyncClient(timeout=30.0)
    
    async def close(self):
        """Close the HTTP client"""
        await self.client.aclose()
    
    # ─────────────────────────────────────────────────────────────────────────────
    # MAIN FETCH METHOD
    # ─────────────────────────────────────────────────────────────────────────────
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def fetch_recent_transactions(self, lookback_minutes: int = 60) -> List[Dict]:
        """
        Fetch recent whale transactions from Whale Alert API.
        
        Args:
            lookback_minutes: How far back to fetch (limited by API plan)
            
        Returns:
            List of parsed transaction dictionaries
        """
        if not self.api_key:
            logger.info("Whale Alert API not configured, using free alternatives (Etherscan/Blockchair)")
            return await self._fetch_free_whale_data()
        
        logger.info("Fetching whale transactions...")
        
        try:
            # Calculate time range
            end_time = int(datetime.utcnow().timestamp())
            start_time = end_time - (lookback_minutes * 60)
            
            params = {
                "api_key": self.api_key,
                "start": start_time,
                "min_value": Thresholds.WHALE_MIN_TRANSACTION_USD,
                "cursor": ""  # For pagination
            }
            
            all_transactions = []
            
            # Paginate through results
            while True:
                response = await self.client.get(WHALE_ALERT_API_URL, params=params)
                
                if response.status_code == 429:
                    logger.warning("Whale Alert rate limit hit, waiting...")
                    await asyncio.sleep(60)
                    continue
                
                response.raise_for_status()
                data = response.json()
                
                transactions = data.get("transactions", [])
                for tx in transactions:
                    parsed = self._parse_transaction(tx)
                    if parsed:
                        all_transactions.append(parsed)
                        # Save to database
                        DatabaseOperations.save_whale_transaction(parsed)
                
                # Check for more pages
                cursor = data.get("cursor")
                if not cursor:
                    break
                params["cursor"] = cursor
            
            logger.info(f"Fetched {len(all_transactions)} whale transactions")
            return all_transactions
            
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                logger.error("Invalid Whale Alert API key")
            else:
                logger.error(f"Whale Alert API error: {e}")
            raise
        except Exception as e:
            logger.error(f"Error fetching whale transactions: {e}")
            raise
    
    # ─────────────────────────────────────────────────────────────────────────────
    # TRANSACTION PARSER
    # ─────────────────────────────────────────────────────────────────────────────
    
    def _parse_transaction(self, tx: Dict) -> Optional[Dict]:
        """
        Parse a Whale Alert transaction and classify flow type.
        
        Args:
            tx: Raw transaction from API
            
        Returns:
            Parsed transaction dict with flow classification
        """
        try:
            blockchain = tx.get("blockchain", "").lower()
            symbol = tx.get("symbol", "").upper()
            
            # Only track our watchlist
            if symbol not in Watchlist.CRYPTO:
                return None
            
            amount = tx.get("amount", 0)
            amount_usd = tx.get("amount_usd", 0)
            
            # Get source and destination
            from_data = tx.get("from", {})
            to_data = tx.get("to", {})
            
            from_owner = from_data.get("owner", "unknown").lower()
            to_owner = to_data.get("owner", "unknown").lower()
            
            # Classify flow type
            flow_type = self._classify_flow(from_owner, to_owner)
            
            return {
                "tx_hash": tx.get("hash", tx.get("id", str(datetime.utcnow().timestamp()))),
                "blockchain": blockchain,
                "symbol": symbol,
                "amount": amount,
                "amount_usd": amount_usd,
                "from_address": from_data.get("address"),
                "to_address": to_data.get("address"),
                "from_owner": from_owner,
                "to_owner": to_owner,
                "flow_type": flow_type,
                "tx_timestamp": datetime.fromtimestamp(tx.get("timestamp", datetime.utcnow().timestamp()))
            }
            
        except Exception as e:
            logger.warning(f"Error parsing whale transaction: {e}")
            return None
    
    def _classify_flow(self, from_owner: str, to_owner: str) -> str:
        """
        Classify transaction as exchange inflow, outflow, or transfer.
        
        Args:
            from_owner: Source wallet owner
            to_owner: Destination wallet owner
            
        Returns:
            Flow type: "exchange_inflow", "exchange_outflow", or "whale_transfer"
        """
        from_is_exchange = any(ex in from_owner for ex in KNOWN_EXCHANGES)
        to_is_exchange = any(ex in to_owner for ex in KNOWN_EXCHANGES)
        
        if not from_is_exchange and to_is_exchange:
            # Moving TO exchange = selling pressure (bearish)
            return "exchange_inflow"
        elif from_is_exchange and not to_is_exchange:
            # Moving FROM exchange = accumulation (bullish)
            return "exchange_outflow"
        else:
            # Exchange to exchange or wallet to wallet
            return "whale_transfer"
    
    # ─────────────────────────────────────────────────────────────────────────────
    # FLOW ANALYSIS
    # ─────────────────────────────────────────────────────────────────────────────
    
    def get_flow_analysis(self, hours: int = 24) -> Dict[str, Dict]:
        """
        Analyze exchange flow patterns for all tracked crypto.
        
        Args:
            hours: Lookback period
            
        Returns:
            Dict mapping symbol to flow analysis:
            {
                "BTC": {
                    "inflow_usd": 50000000,
                    "outflow_usd": 150000000,
                    "net_flow_usd": 100000000,
                    "transaction_count": 45,
                    "signal": "accumulation",
                    "score": 85
                }
            }
        """
        analysis = {}
        
        for symbol in Watchlist.CRYPTO:
            flow_data = DatabaseOperations.get_whale_flow_summary(symbol, hours)
            
            net_flow = flow_data["net_flow_usd"]
            
            # Determine signal type
            if net_flow > 0:
                signal = "accumulation"  # Outflow > Inflow = bullish
            elif net_flow < 0:
                signal = "distribution"  # Inflow > Outflow = bearish
            else:
                signal = "neutral"
            
            # Calculate score based on thresholds
            score = self._calculate_flow_score(symbol, net_flow)
            
            analysis[symbol] = {
                **flow_data,
                "signal": signal,
                "score": score
            }
            
            if score > 50:
                logger.info(f"Whale flow signal: {symbol} - {signal} (score: {score})")
        
        return analysis
    
    def _calculate_flow_score(self, symbol: str, net_flow_usd: float) -> float:
        """
        Calculate component score based on net flow.
        
        Args:
            symbol: Crypto symbol
            net_flow_usd: Net USD flow (positive = accumulation)
            
        Returns:
            Score from 0-100
        """
        # Get thresholds in USD terms
        btc_price_estimate = 60000  # Rough estimate, should fetch real price
        
        weak_threshold = Thresholds.WHALE_WEAK_OUTFLOW_BTC * btc_price_estimate
        strong_threshold = Thresholds.WHALE_STRONG_OUTFLOW_BTC * btc_price_estimate
        
        if net_flow_usd <= 0:
            # Distribution or neutral - low score
            return max(0, 50 + (net_flow_usd / weak_threshold) * 25)
        elif net_flow_usd >= strong_threshold:
            # Strong accumulation
            return 100
        elif net_flow_usd >= weak_threshold:
            # Moderate accumulation
            return 50 + ((net_flow_usd - weak_threshold) / (strong_threshold - weak_threshold)) * 50
        else:
            # Weak accumulation
            return (net_flow_usd / weak_threshold) * 50
    
    # ─────────────────────────────────────────────────────────────────────────────
    # SCORING METHOD
    # ─────────────────────────────────────────────────────────────────────────────
    
    async def get_component_scores(self) -> Dict[str, float]:
        """
        Get whale movement scores for all tracked crypto.
        
        Returns:
            Dict mapping symbol to score (0-100)
        """
        # Fetch new transactions
        await self.fetch_recent_transactions()
        
        # Get flow analysis
        analysis = self.get_flow_analysis()
        
        # Return scores
        return {symbol: data["score"] for symbol, data in analysis.items()}
    
    # ─────────────────────────────────────────────────────────────────────────────
    # MOCK DATA (for testing without API key)
    # ─────────────────────────────────────────────────────────────────────────────
    
    def _get_mock_transactions(self) -> List[Dict]:
        """Generate mock transactions for testing"""
        import random
        
        mock_txs = []
        for symbol in ["BTC", "ETH"]:
            for _ in range(5):
                is_outflow = random.random() > 0.4  # Slight bias toward accumulation
                mock_txs.append({
                    "tx_hash": f"mock_{symbol}_{datetime.utcnow().timestamp()}_{random.randint(1000,9999)}",
                    "blockchain": "bitcoin" if symbol == "BTC" else "ethereum",
                    "symbol": symbol,
                    "amount": random.uniform(100, 5000),
                    "amount_usd": random.uniform(1000000, 50000000),
                    "from_owner": "binance" if is_outflow else "unknown",
                    "to_owner": "unknown" if is_outflow else "coinbase",
                    "flow_type": "exchange_outflow" if is_outflow else "exchange_inflow",
                    "tx_timestamp": datetime.utcnow() - timedelta(hours=random.randint(1, 24))
                })
                DatabaseOperations.save_whale_transaction(mock_txs[-1])
        
        return mock_txs
    
    # ─────────────────────────────────────────────────────────────────────────────
    # FREE API FALLBACK (Etherscan + Blockchair)
    # ─────────────────────────────────────────────────────────────────────────────
    
    async def _fetch_free_whale_data(self) -> List[Dict]:
        """
        Fetch whale data using free APIs when Whale Alert key is not available.
        Uses Etherscan for ETH whales and Blockchair for BTC.
        """
        transactions = []
        
        # Try Etherscan for ETH whale transactions (free API)
        if APIKeys.ETHERSCAN:
            try:
                eth_txs = await self._fetch_etherscan_whales()
                transactions.extend(eth_txs)
            except Exception as e:
                logger.warning(f"Etherscan whale fetch failed: {e}")
        
        # Try Blockchair for BTC (free, no key needed)
        try:
            btc_txs = await self._fetch_blockchair_whales()
            transactions.extend(btc_txs)
        except Exception as e:
            logger.warning(f"Blockchair whale fetch failed: {e}")
        
        # If no real data, fall back to mock
        if not transactions:
            return self._get_mock_transactions()
        
        return transactions
    
    async def _fetch_etherscan_whales(self) -> List[Dict]:
        """Fetch large ETH transactions from Etherscan (free API)"""
        # Known exchange addresses (Binance, Coinbase, etc.)
        exchange_addresses = {
            "0x28c6c06298d514db089934071355e5743bf21d60": "binance",
            "0x21a31ee1afc51d94c2efccaa2092ad1028285549": "binance",
            "0xa9d1e08c7793af67e9d92fe308d5697fb81d3e43": "coinbase",
            "0x71660c4005ba85c37ccec55d0c4493e66fe775d3": "coinbase",
        }
        
        url = "https://api.etherscan.io/api"
        params = {
            "module": "account",
            "action": "txlist",
            "address": "0x28c6c06298d514db089934071355e5743bf21d60",  # Binance hot wallet
            "startblock": 0,
            "endblock": 99999999,
            "page": 1,
            "offset": 20,
            "sort": "desc",
            "apikey": APIKeys.ETHERSCAN
        }
        
        response = await self.client.get(url, params=params)
        if response.status_code != 200:
            return []
        
        data = response.json()
        transactions = []
        
        for tx in data.get("result", [])[:10]:
            value_eth = int(tx.get("value", 0)) / 1e18
            if value_eth >= 100:  # Only large transactions (100+ ETH)
                # Determine flow direction
                from_addr = tx.get("from", "").lower()
                to_addr = tx.get("to", "").lower()
                
                from_owner = exchange_addresses.get(from_addr, "unknown")
                to_owner = exchange_addresses.get(to_addr, "unknown")
                
                flow_type = self._classify_flow(from_owner, to_owner)
                
                tx_data = {
                    "tx_hash": tx.get("hash"),
                    "blockchain": "ethereum",
                    "symbol": "ETH",
                    "amount": value_eth,
                    "amount_usd": value_eth * 3000,  # Approximate price
                    "from_owner": from_owner,
                    "to_owner": to_owner,
                    "flow_type": flow_type,
                    "tx_timestamp": datetime.fromtimestamp(int(tx.get("timeStamp", 0)))
                }
                transactions.append(tx_data)
                DatabaseOperations.save_whale_transaction(tx_data)
        
        return transactions
    
    async def _fetch_blockchair_whales(self) -> List[Dict]:
        """Fetch large BTC transactions from Blockchair (free, no key needed)"""
        url = "https://api.blockchair.com/bitcoin/transactions"
        params = {
            "limit": 10,
            "s": "output_total(desc)"
        }
        
        response = await self.client.get(url, params=params)
        if response.status_code != 200:
            return []
        
        data = response.json()
        transactions = []
        
        for tx in data.get("data", []):
            value_btc = tx.get("output_total", 0) / 1e8
            if value_btc >= 10:  # Only large transactions (10+ BTC)
                tx_data = {
                    "tx_hash": tx.get("hash"),
                    "blockchain": "bitcoin",
                    "symbol": "BTC",
                    "amount": value_btc,
                    "amount_usd": value_btc * 60000,  # Approximate price
                    "from_owner": "unknown",
                    "to_owner": "unknown",
                    "flow_type": "whale_transfer",
                    "tx_timestamp": datetime.utcnow()
                }
                transactions.append(tx_data)
                DatabaseOperations.save_whale_transaction(tx_data)
        
        return transactions


# Import asyncio for rate limit handling
import asyncio
