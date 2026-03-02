# ═══════════════════════════════════════════════════════════════════════════════
# MARKET INTELLIGENCE ENGINE - SEC FILINGS FETCHER
# ═══════════════════════════════════════════════════════════════════════════════
"""
Fetches and parses SEC Form 4 insider trading filings from EDGAR.
Detects clusters of insider buying activity.
"""

import re
import asyncio
from datetime import datetime
from typing import List, Dict, Optional

import httpx
import feedparser
from bs4 import BeautifulSoup
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from ..config import Thresholds, Watchlist
from ..database import DatabaseOperations

# ─────────────────────────────────────────────────────────────────────────────────
# SEC EDGAR CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────────
SEC_RSS_FEED = "https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=4&company=&dateb=&owner=include&count=100&output=atom"
SEC_USER_AGENT = "MarketIntelEngine research@example.com"  # SEC requires identification

# ─────────────────────────────────────────────────────────────────────────────────
# SEC FILINGS FETCHER CLASS
# ─────────────────────────────────────────────────────────────────────────────────

class SECFilingsFetcher:
    """
    Fetches SEC Form 4 filings and detects insider buying clusters.
    
    How it works:
    1. Polls SEC EDGAR RSS feed for new Form 4 filings
    2. Parses each filing to extract transaction details
    3. Stores in database for cluster detection
    4. Flags tickers with multiple insider buys in the lookback period
    """
    
    def __init__(self):
        self.client = httpx.AsyncClient(
            headers={"User-Agent": SEC_USER_AGENT},
            timeout=30.0
        )
    
    async def close(self):
        """Close the HTTP client"""
        await self.client.aclose()
    
    # ─────────────────────────────────────────────────────────────────────────────
    # MAIN FETCH METHOD
    # ─────────────────────────────────────────────────────────────────────────────
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def fetch_recent_filings(self) -> List[Dict]:
        """
        Fetch recent Form 4 filings from SEC RSS feed.
        
        Returns:
            List of parsed filing dictionaries
        """
        logger.info("Fetching SEC Form 4 filings...")
        
        try:
            response = await self.client.get(SEC_RSS_FEED)
            response.raise_for_status()
            
            # Parse RSS feed
            feed = feedparser.parse(response.text)
            
            filings = []
            for entry in feed.entries:
                filing = await self._parse_filing_entry(entry)
                if filing:
                    filings.append(filing)
            
            logger.info(f"Fetched {len(filings)} Form 4 filings")
            return filings
            
        except Exception as e:
            logger.error(f"Error fetching SEC filings: {e}")
            raise
    
    # ─────────────────────────────────────────────────────────────────────────────
    # FILING PARSER
    # ─────────────────────────────────────────────────────────────────────────────
    
    async def _parse_filing_entry(self, entry: dict) -> Optional[Dict]:
        """
        Parse a single RSS entry to extract filing details.
        
        Args:
            entry: feedparser entry object
            
        Returns:
            Parsed filing dict or None if not a buy
        """
        try:
            # Extract basic info from RSS entry
            title = entry.get("title", "")
            link = entry.get("link", "")
            
            # Extract ticker from title (format: "4 - COMPANY NAME (0001234567) (Issuer)")
            # We need to fetch the actual filing to get the ticker
            accession_match = re.search(r"/(\d{10}-\d{2}-\d{6})", link)
            if not accession_match:
                return None
            
            accession_number = accession_match.group(1)
            
            # Check if we already have this filing
            if self._is_duplicate(accession_number):
                return None
            
            # Fetch the filing details page to get transaction info
            filing_details = await self._fetch_filing_details(link)
            if not filing_details:
                return None
            
            # Only care about buys
            if filing_details.get("transaction_type") != "buy":
                return None
            
            # Add accession number
            filing_details["accession_number"] = accession_number
            
            # Save to database
            saved = DatabaseOperations.save_insider_filing(filing_details)
            if saved:
                logger.debug(f"Saved insider buy: {filing_details.get('ticker')} by {filing_details.get('insider_name')}")
            
            return filing_details
            
        except Exception as e:
            logger.warning(f"Error parsing filing entry: {e}")
            return None
    
    @retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=1, max=5))
    async def _fetch_filing_details(self, filing_url: str) -> Optional[Dict]:
        """
        Fetch and parse the actual Form 4 filing to extract transaction details.
        
        Args:
            filing_url: URL to the SEC filing page
            
        Returns:
            Dict with transaction details or None
        """
        try:
            # Small delay to respect SEC rate limits
            await asyncio.sleep(0.2)
            
            response = await self.client.get(filing_url)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, "lxml")
            
            # Find the XML link for structured data
            xml_link = None
            for link in soup.find_all("a"):
                href = link.get("href", "")
                if href.endswith(".xml") and "primary_doc" not in href.lower():
                    xml_link = f"https://www.sec.gov{href}"
                    break
            
            if not xml_link:
                # Try to find the document table
                return self._parse_html_filing(soup)
            
            # Fetch and parse XML
            return await self._parse_xml_filing(xml_link)
            
        except Exception as e:
            logger.warning(f"Error fetching filing details: {e}")
            return None
    
    async def _parse_xml_filing(self, xml_url: str) -> Optional[Dict]:
        """Parse Form 4 XML filing"""
        try:
            response = await self.client.get(xml_url)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, "lxml-xml")
            
            # Extract issuer (company) info
            issuer = soup.find("issuer")
            if not issuer:
                return None
            
            ticker_elem = issuer.find("issuerTradingSymbol")
            ticker = ticker_elem.text.strip().upper() if ticker_elem else None
            
            if not ticker:
                return None
            
            company_elem = issuer.find("issuerName")
            company_name = company_elem.text.strip() if company_elem else None
            
            # Extract reporting owner (insider) info
            owner = soup.find("reportingOwner")
            if not owner:
                return None
            
            owner_name_elem = owner.find("rptOwnerName")
            insider_name = owner_name_elem.text.strip() if owner_name_elem else "Unknown"
            
            # Get title/relationship
            relationship = owner.find("reportingOwnerRelationship")
            insider_title = None
            if relationship:
                if relationship.find("isOfficer"):
                    title_elem = relationship.find("officerTitle")
                    insider_title = title_elem.text.strip() if title_elem else "Officer"
                elif relationship.find("isDirector"):
                    insider_title = "Director"
            
            # Extract transaction details
            # Look for non-derivative transactions (Table I)
            transactions = soup.find_all("nonDerivativeTransaction")
            
            total_shares = 0
            total_value = 0
            price_per_share = 0
            tx_type = None
            tx_date = None
            
            for tx in transactions:
                # Get transaction type (A=Acquisition, D=Disposition)
                tx_code = tx.find("transactionAcquiredDisposedCode")
                if tx_code:
                    code = tx_code.find("value")
                    if code and code.text.strip() == "A":
                        tx_type = "buy"
                    elif code and code.text.strip() == "D":
                        tx_type = "sell"
                
                # Only process buys
                if tx_type != "buy":
                    continue
                
                # Get shares
                shares_elem = tx.find("transactionShares")
                if shares_elem:
                    value = shares_elem.find("value")
                    if value:
                        total_shares += float(value.text)
                
                # Get price
                price_elem = tx.find("transactionPricePerShare")
                if price_elem:
                    value = price_elem.find("value")
                    if value:
                        price_per_share = float(value.text)
                
                # Get date
                date_elem = tx.find("transactionDate")
                if date_elem:
                    value = date_elem.find("value")
                    if value:
                        tx_date = datetime.strptime(value.text, "%Y-%m-%d")
            
            if tx_type != "buy" or total_shares == 0:
                return None
            
            total_value = total_shares * price_per_share
            
            return {
                "ticker": ticker,
                "company_name": company_name,
                "insider_name": insider_name,
                "insider_title": insider_title,
                "transaction_type": tx_type,
                "shares_transacted": total_shares,
                "price_per_share": price_per_share,
                "total_value": total_value,
                "transaction_date": tx_date,
                "filing_date": datetime.utcnow()
            }
            
        except Exception as e:
            logger.warning(f"Error parsing XML filing: {e}")
            return None
    
    def _parse_html_filing(self, soup: BeautifulSoup) -> Optional[Dict]:
        """Fallback HTML parser when XML not available"""
        # Simplified HTML parsing - in production you'd make this more robust
        return None
    
    def _is_duplicate(self, accession_number: str) -> bool:
        """Check if filing already exists in database"""
        from ..database import SessionLocal, InsiderFiling
        session = SessionLocal()
        try:
            exists = session.query(InsiderFiling).filter(
                InsiderFiling.accession_number == accession_number
            ).first() is not None
            return exists
        finally:
            session.close()
    
    # ─────────────────────────────────────────────────────────────────────────────
    # CLUSTER DETECTION
    # ─────────────────────────────────────────────────────────────────────────────
    
    def get_insider_clusters(self) -> Dict[str, Dict]:
        """
        Detect tickers with clustered insider buying.
        
        Returns:
            Dict mapping ticker to cluster info:
            {
                "NVDA": {
                    "buy_count": 4,
                    "total_value": 12400000,
                    "insiders": ["Jensen Huang", "Mark Stevens", ...],
                    "score": 100
                }
            }
        """
        clusters = {}
        
        # Check all watchlist tickers
        for ticker in Watchlist.EQUITIES:
            filings = DatabaseOperations.get_insider_cluster(ticker)
            
            if len(filings) >= Thresholds.INSIDER_MIN_CLUSTER_SIZE:
                total_value = sum(f.total_value or 0 for f in filings)
                insiders = list(set(f.insider_name for f in filings))
                
                # Calculate score based on cluster size
                if len(filings) >= Thresholds.INSIDER_STRONG_CLUSTER_SIZE:
                    score = 100
                elif len(filings) >= Thresholds.INSIDER_MIN_CLUSTER_SIZE:
                    score = 50 + (len(filings) - Thresholds.INSIDER_MIN_CLUSTER_SIZE) * 25
                else:
                    score = 20 * len(filings)
                
                clusters[ticker] = {
                    "buy_count": len(filings),
                    "total_value": total_value,
                    "insiders": insiders,
                    "score": min(score, 100)  # Cap at 100
                }
                
                logger.info(f"Insider cluster detected: {ticker} - {len(filings)} buys (${total_value:,.0f})")
        
        return clusters
    
    # ─────────────────────────────────────────────────────────────────────────────
    # SCORING METHOD
    # ─────────────────────────────────────────────────────────────────────────────
    
    async def get_component_scores(self) -> Dict[str, float]:
        """
        Get insider cluster scores for all watched tickers.
        
        Returns:
            Dict mapping ticker to score (0-100)
        """
        # Fetch new filings
        await self.fetch_recent_filings()
        
        # Get clusters
        clusters = self.get_insider_clusters()
        
        # Return scores
        return {ticker: data["score"] for ticker, data in clusters.items()}
