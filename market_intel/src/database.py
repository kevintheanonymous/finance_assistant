# ═══════════════════════════════════════════════════════════════════════════════
# MARKET INTELLIGENCE ENGINE - DATABASE LAYER
# ═══════════════════════════════════════════════════════════════════════════════
"""
Database models and operations for signal storage, deduplication, and cooldown tracking.
Uses SQLAlchemy for ORM with SQLite (local) or PostgreSQL (cloud) support.
"""

import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List

from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Boolean, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from loguru import logger

from .config import DatabaseConfig, Thresholds

# ─────────────────────────────────────────────────────────────────────────────────
# DATABASE SETUP
# ─────────────────────────────────────────────────────────────────────────────────
Base = declarative_base()

def get_engine():
    """Create database engine based on configuration"""
    db_url = DatabaseConfig.URL
    
    # Ensure data directory exists for SQLite
    if db_url.startswith("sqlite"):
        data_dir = Path(__file__).parent.parent / "data"
        data_dir.mkdir(exist_ok=True)
        # Convert relative path to absolute
        if ":///" in db_url:
            db_path = db_url.split("///")[1]
            if not os.path.isabs(db_path):
                db_url = f"sqlite:///{data_dir / Path(db_path).name}"
    
    return create_engine(db_url, echo=False)

engine = get_engine()
SessionLocal = sessionmaker(bind=engine)

# ─────────────────────────────────────────────────────────────────────────────────
# DATABASE MODELS
# ─────────────────────────────────────────────────────────────────────────────────

class Signal(Base):
    """
    Stores every detected signal for audit trail and analysis.
    This is the primary table for tracking what the system has seen.
    """
    __tablename__ = "signals"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Asset identification
    asset_symbol = Column(String(20), nullable=False, index=True)  # e.g., "NVDA", "BTC"
    asset_type = Column(String(10), nullable=False)  # "equity" or "crypto"
    
    # Signal metadata
    signal_score = Column(Float, nullable=False)  # 0-100
    signal_type = Column(String(30), nullable=False)  # "high_confidence", "moderate", "weak"
    
    # Component scores (for debugging and weight tuning)
    insider_score = Column(Float, default=0)
    options_score = Column(Float, default=0)
    whale_score = Column(Float, default=0)
    stablecoin_score = Column(Float, default=0)
    sentiment_score = Column(Float, default=0)
    fear_index_score = Column(Float, default=0)
    
    # Number of components that scored > 50
    confirmation_count = Column(Integer, default=0)
    
    # Raw data snapshot (JSON string for debugging)
    raw_data = Column(Text, nullable=True)
    
    # Alert tracking
    alert_sent = Column(Boolean, default=False)
    alert_sent_at = Column(DateTime, nullable=True)
    
    # Timestamps
    detected_at = Column(DateTime, default=datetime.utcnow, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f"<Signal {self.asset_symbol} score={self.signal_score} type={self.signal_type}>"


class InsiderFiling(Base):
    """
    Stores SEC Form 4 filings to detect clustering patterns.
    """
    __tablename__ = "insider_filings"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Filing identification
    accession_number = Column(String(50), unique=True, nullable=False)  # SEC accession number
    ticker = Column(String(10), nullable=False, index=True)
    company_name = Column(String(200), nullable=True)
    
    # Insider details
    insider_name = Column(String(200), nullable=False)
    insider_title = Column(String(100), nullable=True)  # CEO, CFO, Director, etc.
    
    # Transaction details
    transaction_type = Column(String(20), nullable=False)  # "buy", "sell", "grant"
    shares_transacted = Column(Float, nullable=True)
    price_per_share = Column(Float, nullable=True)
    total_value = Column(Float, nullable=True)
    
    # Dates
    transaction_date = Column(DateTime, nullable=True)
    filing_date = Column(DateTime, nullable=False, index=True)
    
    # Processing status
    processed = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f"<InsiderFiling {self.ticker} {self.insider_name} {self.transaction_type}>"


class WhaleTransaction(Base):
    """
    Stores crypto whale movements for pattern detection.
    """
    __tablename__ = "whale_transactions"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Transaction identification
    tx_hash = Column(String(100), unique=True, nullable=False)
    blockchain = Column(String(20), nullable=False)  # "bitcoin", "ethereum", etc.
    
    # Asset details
    symbol = Column(String(10), nullable=False, index=True)  # "BTC", "ETH", etc.
    amount = Column(Float, nullable=False)
    amount_usd = Column(Float, nullable=False)
    
    # Flow direction
    from_address = Column(String(100), nullable=True)
    to_address = Column(String(100), nullable=True)
    from_owner = Column(String(100), nullable=True)  # "binance", "coinbase", "unknown"
    to_owner = Column(String(100), nullable=True)
    
    # Classification
    flow_type = Column(String(20), nullable=False)  # "exchange_inflow", "exchange_outflow", "whale_transfer"
    
    # Timestamp
    tx_timestamp = Column(DateTime, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f"<WhaleTransaction {self.symbol} {self.amount} {self.flow_type}>"


class AlertCooldown(Base):
    """
    Tracks cooldowns to prevent alert spam for the same asset.
    """
    __tablename__ = "alert_cooldowns"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    asset_symbol = Column(String(20), nullable=False, unique=True, index=True)
    last_alert_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f"<AlertCooldown {self.asset_symbol} last={self.last_alert_at}>"


# ─────────────────────────────────────────────────────────────────────────────────
# DATABASE OPERATIONS
# ─────────────────────────────────────────────────────────────────────────────────

class DatabaseOperations:
    """
    High-level database operations for the signal engine.
    All methods are static for easy access without instantiation.
    """
    
    @staticmethod
    def init_db():
        """Create all tables if they don't exist"""
        Base.metadata.create_all(engine)
        logger.info("Database initialized successfully")
    
    @staticmethod
    def get_session():
        """Get a new database session"""
        return SessionLocal()
    
    # ─────────────────────────────────────────────────────────────────────────────
    # SIGNAL OPERATIONS
    # ─────────────────────────────────────────────────────────────────────────────
    
    @staticmethod
    def save_signal(signal_data: dict) -> Signal:
        """
        Save a new signal to the database.
        
        Args:
            signal_data: Dictionary containing signal fields
            
        Returns:
            The created Signal object
        """
        session = SessionLocal()
        try:
            signal = Signal(**signal_data)
            session.add(signal)
            session.commit()
            session.refresh(signal)
            logger.debug(f"Saved signal: {signal}")
            return signal
        finally:
            session.close()
    
    @staticmethod
    def get_recent_signals(hours: int = 24, min_score: float = 0) -> List[Signal]:
        """
        Retrieve signals from the last N hours.
        
        Args:
            hours: Number of hours to look back
            min_score: Minimum signal score to include
            
        Returns:
            List of Signal objects
        """
        session = SessionLocal()
        try:
            cutoff = datetime.utcnow() - timedelta(hours=hours)
            return session.query(Signal).filter(
                Signal.detected_at >= cutoff,
                Signal.signal_score >= min_score
            ).order_by(Signal.detected_at.desc()).all()
        finally:
            session.close()
    
    # ─────────────────────────────────────────────────────────────────────────────
    # COOLDOWN OPERATIONS
    # ─────────────────────────────────────────────────────────────────────────────
    
    @staticmethod
    def is_on_cooldown(asset_symbol: str) -> bool:
        """
        Check if an asset is on alert cooldown.
        
        Args:
            asset_symbol: The ticker/symbol to check
            
        Returns:
            True if on cooldown (should NOT alert), False otherwise
        """
        session = SessionLocal()
        try:
            cooldown = session.query(AlertCooldown).filter(
                AlertCooldown.asset_symbol == asset_symbol.upper()
            ).first()
            
            if not cooldown:
                return False
            
            cooldown_end = cooldown.last_alert_at + timedelta(hours=Thresholds.COOLDOWN_HOURS)
            return datetime.utcnow() < cooldown_end
        finally:
            session.close()
    
    @staticmethod
    def set_cooldown(asset_symbol: str):
        """
        Set or update cooldown for an asset after alerting.
        
        Args:
            asset_symbol: The ticker/symbol to set cooldown for
        """
        session = SessionLocal()
        try:
            cooldown = session.query(AlertCooldown).filter(
                AlertCooldown.asset_symbol == asset_symbol.upper()
            ).first()
            
            if cooldown:
                cooldown.last_alert_at = datetime.utcnow()
            else:
                cooldown = AlertCooldown(
                    asset_symbol=asset_symbol.upper(),
                    last_alert_at=datetime.utcnow()
                )
                session.add(cooldown)
            
            session.commit()
            logger.debug(f"Set cooldown for {asset_symbol}")
        finally:
            session.close()
    
    # ─────────────────────────────────────────────────────────────────────────────
    # INSIDER FILING OPERATIONS
    # ─────────────────────────────────────────────────────────────────────────────
    
    @staticmethod
    def save_insider_filing(filing_data: dict) -> Optional[InsiderFiling]:
        """
        Save an insider filing if not already exists.
        
        Args:
            filing_data: Dictionary containing filing fields
            
        Returns:
            The created InsiderFiling or None if duplicate
        """
        session = SessionLocal()
        try:
            # Check for duplicate
            existing = session.query(InsiderFiling).filter(
                InsiderFiling.accession_number == filing_data.get("accession_number")
            ).first()
            
            if existing:
                return None
            
            filing = InsiderFiling(**filing_data)
            session.add(filing)
            session.commit()
            session.refresh(filing)
            logger.debug(f"Saved insider filing: {filing}")
            return filing
        finally:
            session.close()
    
    @staticmethod
    def get_insider_cluster(ticker: str, days: int = None) -> List[InsiderFiling]:
        """
        Get insider buys for a ticker within the lookback period.
        
        Args:
            ticker: Stock ticker symbol
            days: Lookback period (defaults to config)
            
        Returns:
            List of InsiderFiling objects (buys only)
        """
        if days is None:
            days = Thresholds.INSIDER_LOOKBACK_DAYS
        
        session = SessionLocal()
        try:
            cutoff = datetime.utcnow() - timedelta(days=days)
            return session.query(InsiderFiling).filter(
                InsiderFiling.ticker == ticker.upper(),
                InsiderFiling.transaction_type == "buy",
                InsiderFiling.filing_date >= cutoff
            ).order_by(InsiderFiling.filing_date.desc()).all()
        finally:
            session.close()
    
    # ─────────────────────────────────────────────────────────────────────────────
    # WHALE TRANSACTION OPERATIONS
    # ─────────────────────────────────────────────────────────────────────────────
    
    @staticmethod
    def save_whale_transaction(tx_data: dict) -> Optional[WhaleTransaction]:
        """
        Save a whale transaction if not already exists.
        
        Args:
            tx_data: Dictionary containing transaction fields
            
        Returns:
            The created WhaleTransaction or None if duplicate
        """
        session = SessionLocal()
        try:
            # Check for duplicate
            existing = session.query(WhaleTransaction).filter(
                WhaleTransaction.tx_hash == tx_data.get("tx_hash")
            ).first()
            
            if existing:
                return None
            
            tx = WhaleTransaction(**tx_data)
            session.add(tx)
            session.commit()
            session.refresh(tx)
            logger.debug(f"Saved whale transaction: {tx}")
            return tx
        finally:
            session.close()
    
    @staticmethod
    def get_whale_flow_summary(symbol: str, hours: int = 24) -> dict:
        """
        Calculate net exchange flow for a crypto asset.
        
        Args:
            symbol: Crypto symbol (BTC, ETH, etc.)
            hours: Lookback period
            
        Returns:
            Dict with inflow, outflow, and net flow in USD
        """
        session = SessionLocal()
        try:
            cutoff = datetime.utcnow() - timedelta(hours=hours)
            transactions = session.query(WhaleTransaction).filter(
                WhaleTransaction.symbol == symbol.upper(),
                WhaleTransaction.tx_timestamp >= cutoff
            ).all()
            
            inflow = sum(tx.amount_usd for tx in transactions if tx.flow_type == "exchange_inflow")
            outflow = sum(tx.amount_usd for tx in transactions if tx.flow_type == "exchange_outflow")
            
            return {
                "symbol": symbol.upper(),
                "inflow_usd": inflow,
                "outflow_usd": outflow,
                "net_flow_usd": outflow - inflow,  # Positive = accumulation
                "transaction_count": len(transactions)
            }
        finally:
            session.close()
    
    # ─────────────────────────────────────────────────────────────────────────────
    # MAINTENANCE OPERATIONS
    # ─────────────────────────────────────────────────────────────────────────────
    
    @staticmethod
    def get_database_stats() -> dict:
        """
        Get database statistics for health monitoring.
        
        Returns:
            Dict with table row counts and database size
        """
        session = SessionLocal()
        try:
            stats = {
                "signals_count": session.query(Signal).count(),
                "insider_filings_count": session.query(InsiderFiling).count(),
                "whale_transactions_count": session.query(WhaleTransaction).count(),
                "cooldowns_count": session.query(AlertCooldown).count(),
            }
            
            # Get database file size for SQLite
            if DatabaseConfig.URL.startswith("sqlite"):
                db_path = DatabaseConfig.URL.replace("sqlite:///", "")
                if os.path.exists(db_path):
                    stats["database_size_mb"] = os.path.getsize(db_path) / (1024 * 1024)
                else:
                    stats["database_size_mb"] = 0
            
            return stats
        finally:
            session.close()
    
    @staticmethod
    def cleanup_old_data(days: int = 90):
        """
        Remove data older than specified days to prevent database bloat.
        
        Args:
            days: Data older than this will be deleted
        """
        session = SessionLocal()
        try:
            cutoff = datetime.utcnow() - timedelta(days=days)
            
            # Delete old transactions
            deleted_whale = session.query(WhaleTransaction).filter(
                WhaleTransaction.tx_timestamp < cutoff
            ).delete()
            
            # Delete old filings
            deleted_filings = session.query(InsiderFiling).filter(
                InsiderFiling.filing_date < cutoff
            ).delete()
            
            # Keep signals longer (they're smaller)
            deleted_signals = session.query(Signal).filter(
                Signal.detected_at < cutoff - timedelta(days=90)  # 180 days total
            ).delete()
            
            session.commit()
            logger.info(f"Cleanup: removed {deleted_whale} whale txs, {deleted_filings} filings, {deleted_signals} signals")
        finally:
            session.close()
