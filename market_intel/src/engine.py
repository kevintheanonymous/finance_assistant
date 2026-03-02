# ═══════════════════════════════════════════════════════════════════════════════
# MARKET INTELLIGENCE ENGINE - MAIN ORCHESTRATOR (ENHANCED WITH LEARNING)
# ═══════════════════════════════════════════════════════════════════════════════
"""
Central orchestrator that coordinates all components.
This is the entry point for the 24/7 market intelligence engine.

ENHANCED FEATURES:
- 11 data fetchers (core + advanced)
- Machine learning weight optimization
- Outcome tracking for every prediction
- Daily performance analysis
"""

import asyncio
import signal
import sys
from datetime import datetime
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from loguru import logger

from .config import (
    setup_logging,
    validate_config,
    SchedulerConfig,
    Thresholds
)
from .database import DatabaseOperations
from .scoring import ScoringEngine
from .alerts import AlertDispatcher

# Core fetchers
from .fetchers import (
    SECFilingsFetcher,
    WhaleAlertFetcher,
    OptionsFlowFetcher,
    SentimentAnalyzer,
    FearIndexFetcher
)

# Advanced fetchers
from .fetchers import (
    DarkPoolTracker,
    ShortInterestTracker,
    CongressionalTracker,
    OnChainAnalytics,
    SocialMomentumTracker,
    MacroIndicators
)

# Learning system
from .learning import OutcomeTracker, WeightOptimizer, PerformanceAnalyzer

# ─────────────────────────────────────────────────────────────────────────────────
# ORCHESTRATOR CLASS
# ─────────────────────────────────────────────────────────────────────────────────

class MarketIntelOrchestrator:
    """
    Main orchestrator that:
    1. Initializes all components (11 fetchers + learning)
    2. Schedules data fetching jobs
    3. Runs scoring after each fetch
    4. Dispatches alerts when thresholds are met
    5. Tracks outcomes and optimizes weights
    """
    
    def __init__(self):
        # Initialize logging
        setup_logging()
        logger.info("═" * 60)
        logger.info("MARKET INTELLIGENCE ENGINE v2.0 (ENHANCED)")
        logger.info("═" * 60)
        
        # Validate configuration
        if not validate_config():
            logger.warning("Configuration has warnings - some features may not work")
        
        # Initialize database
        DatabaseOperations.init_db()
        
        # Initialize components
        self.scoring_engine = ScoringEngine(use_learned_weights=True)
        self.alert_dispatcher = AlertDispatcher()
        
        # Initialize core fetchers
        self.sec_fetcher = SECFilingsFetcher()
        self.whale_fetcher = WhaleAlertFetcher()
        self.options_fetcher = OptionsFlowFetcher()
        self.sentiment_analyzer = SentimentAnalyzer()
        self.fear_fetcher = FearIndexFetcher()
        
        # Initialize advanced fetchers
        self.dark_pool_tracker = DarkPoolTracker()
        self.short_interest_tracker = ShortInterestTracker()
        self.congressional_tracker = CongressionalTracker()
        self.on_chain_analytics = OnChainAnalytics()
        self.social_momentum_tracker = SocialMomentumTracker()
        self.macro_indicators = MacroIndicators()
        
        # Initialize learning components
        self.outcome_tracker = OutcomeTracker()
        self.weight_optimizer = WeightOptimizer()
        self.performance_analyzer = PerformanceAnalyzer()
        
        # Initialize scheduler
        self.scheduler = AsyncIOScheduler()
        
        # Running flag
        self._running = False
        
        logger.info("Initialized 11 data fetchers + ML learning system")
    
    # ─────────────────────────────────────────────────────────────────────────────
    # LIFECYCLE METHODS
    # ─────────────────────────────────────────────────────────────────────────────
    
    async def start(self):
        """Start the orchestrator and all scheduled jobs"""
        logger.info("Starting Market Intelligence Engine...")
        
        self._running = True
        
        # Schedule jobs
        self._schedule_jobs()
        
        # Start scheduler
        self.scheduler.start()
        
        # Run initial fetch
        logger.info("Running initial data fetch...")
        await self._run_full_cycle()
        
        logger.info("═" * 60)
        logger.info("MARKET INTELLIGENCE ENGINE - RUNNING")
        logger.info(f"Data Sources: 11 | Learning: ENABLED")
        logger.info("═" * 60)
        
        # Keep running
        while self._running:
            await asyncio.sleep(1)
    
    async def stop(self):
        """Gracefully stop the orchestrator"""
        logger.info("Stopping Market Intelligence Engine...")
        
        self._running = False
        
        # Shutdown scheduler
        self.scheduler.shutdown(wait=True)
        
        # Close core fetchers
        await self.sec_fetcher.close()
        await self.whale_fetcher.close()
        await self.options_fetcher.close()
        await self.sentiment_analyzer.close()
        await self.fear_fetcher.close()
        
        # Close advanced fetchers
        await self.dark_pool_tracker.close()
        await self.short_interest_tracker.close()
        await self.congressional_tracker.close()
        await self.on_chain_analytics.close()
        await self.social_momentum_tracker.close()
        await self.macro_indicators.close()
        
        # Close learning components
        await self.outcome_tracker.close()
        
        # Close alert dispatcher
        await self.alert_dispatcher.close()
        
        logger.info("Market Intelligence Engine stopped")
    
    # ─────────────────────────────────────────────────────────────────────────────
    # SCHEDULER SETUP
    # ─────────────────────────────────────────────────────────────────────────────
    
    def _schedule_jobs(self):
        """Configure all scheduled jobs (core + advanced + learning)"""
        
        # ═══════════════ CORE FETCHERS ═══════════════
        
        # SEC Filings - every 15 minutes
        self.scheduler.add_job(
            self._job_fetch_sec,
            IntervalTrigger(minutes=SchedulerConfig.SEC_FILINGS_INTERVAL),
            id="sec_filings",
            name="Fetch SEC Form 4 Filings"
        )
        
        # Whale Alert - every 5 minutes
        self.scheduler.add_job(
            self._job_fetch_whales,
            IntervalTrigger(minutes=SchedulerConfig.WHALE_ALERT_INTERVAL),
            id="whale_alert",
            name="Fetch Whale Transactions"
        )
        
        # Options Flow - every 30 minutes
        self.scheduler.add_job(
            self._job_fetch_options,
            IntervalTrigger(minutes=SchedulerConfig.OPTIONS_FLOW_INTERVAL),
            id="options_flow",
            name="Fetch Options Flow"
        )
        
        # Sentiment Analysis - every hour
        self.scheduler.add_job(
            self._job_analyze_sentiment,
            IntervalTrigger(minutes=SchedulerConfig.SENTIMENT_INTERVAL),
            id="sentiment",
            name="Analyze Sentiment"
        )
        
        # Fear Indices - every hour
        self.scheduler.add_job(
            self._job_fetch_fear_indices,
            IntervalTrigger(minutes=SchedulerConfig.FEAR_INDEX_INTERVAL),
            id="fear_indices",
            name="Fetch Fear Indices"
        )
        
        # ═══════════════ ADVANCED FETCHERS ═══════════════
        
        # Dark Pool Data - every 30 minutes
        self.scheduler.add_job(
            self._job_fetch_dark_pool,
            IntervalTrigger(minutes=30),
            id="dark_pool",
            name="Fetch Dark Pool Activity"
        )
        
        # Short Interest - every 2 hours
        self.scheduler.add_job(
            self._job_fetch_short_interest,
            IntervalTrigger(hours=2),
            id="short_interest",
            name="Fetch Short Interest"
        )
        
        # Congressional Trading - every 4 hours
        self.scheduler.add_job(
            self._job_fetch_congressional,
            IntervalTrigger(hours=4),
            id="congressional",
            name="Fetch Congressional Trades"
        )
        
        # On-Chain Analytics - every 15 minutes
        self.scheduler.add_job(
            self._job_fetch_on_chain,
            IntervalTrigger(minutes=15),
            id="on_chain",
            name="Fetch On-Chain Data"
        )
        
        # Social Momentum - every 30 minutes
        self.scheduler.add_job(
            self._job_fetch_social_momentum,
            IntervalTrigger(minutes=30),
            id="social_momentum",
            name="Fetch Social Momentum"
        )
        
        # Macro Indicators - every 2 hours
        self.scheduler.add_job(
            self._job_fetch_macro,
            IntervalTrigger(hours=2),
            id="macro",
            name="Fetch Macro Indicators"
        )
        
        # ═══════════════ SCORING & ALERTS ═══════════════
        
        # Full scoring cycle - every 15 minutes
        self.scheduler.add_job(
            self._job_score_and_alert,
            IntervalTrigger(minutes=15),
            id="scoring",
            name="Score and Alert"
        )
        
        # ═══════════════ LEARNING SYSTEM ═══════════════
        
        # Check outcomes - every 4 hours
        self.scheduler.add_job(
            self._job_check_outcomes,
            IntervalTrigger(hours=4),
            id="check_outcomes",
            name="Check Prediction Outcomes"
        )
        
        # Daily weight optimization - at 6 AM UTC
        self.scheduler.add_job(
            self._job_optimize_weights,
            CronTrigger(hour=6, minute=0),
            id="optimize_weights",
            name="Daily Weight Optimization"
        )
        
        # Daily performance log - at 23:55 UTC
        self.scheduler.add_job(
            self._job_log_performance,
            CronTrigger(hour=23, minute=55),
            id="log_performance",
            name="Daily Performance Log"
        )
        
        # ═══════════════ MAINTENANCE ═══════════════
        
        # Database cleanup - daily at 4 AM
        self.scheduler.add_job(
            self._job_cleanup,
            CronTrigger(hour=4, minute=0),
            id="cleanup",
            name="Database Cleanup"
        )
        
        logger.info(f"Scheduled {len(self.scheduler.get_jobs())} jobs")
    
    # ─────────────────────────────────────────────────────────────────────────────
    # JOB HANDLERS (CORE FETCHERS)
    # ─────────────────────────────────────────────────────────────────────────────
    
    async def _job_fetch_sec(self):
        """Job: Fetch SEC Form 4 filings"""
        try:
            logger.info("[JOB] Fetching SEC filings...")
            scores = await self.sec_fetcher.get_component_scores()
            self.scoring_engine.update_insider_scores(scores)
        except Exception as e:
            logger.error(f"SEC fetch job failed: {e}")
    
    async def _job_fetch_whales(self):
        """Job: Fetch whale transactions"""
        try:
            logger.info("[JOB] Fetching whale transactions...")
            scores = await self.whale_fetcher.get_component_scores()
            self.scoring_engine.update_whale_scores(scores)
        except Exception as e:
            logger.error(f"Whale fetch job failed: {e}")
    
    async def _job_fetch_options(self):
        """Job: Fetch options flow data"""
        try:
            logger.info("[JOB] Fetching options flow...")
            scores = await self.options_fetcher.get_component_scores()
            self.scoring_engine.update_options_scores(scores)
        except Exception as e:
            logger.error(f"Options fetch job failed: {e}")
    
    async def _job_analyze_sentiment(self):
        """Job: Analyze sentiment"""
        try:
            logger.info("[JOB] Analyzing sentiment...")
            scores = await self.sentiment_analyzer.get_component_scores()
            self.scoring_engine.update_sentiment_scores(scores)
        except Exception as e:
            logger.error(f"Sentiment analysis job failed: {e}")
    
    async def _job_fetch_fear_indices(self):
        """Job: Fetch fear indices"""
        try:
            logger.info("[JOB] Fetching fear indices...")
            scores = await self.fear_fetcher.get_component_scores()
            self.scoring_engine.update_fear_index_scores(scores)
        except Exception as e:
            logger.error(f"Fear index fetch job failed: {e}")
    
    # ─────────────────────────────────────────────────────────────────────────────
    # JOB HANDLERS (ADVANCED FETCHERS)
    # ─────────────────────────────────────────────────────────────────────────────
    
    async def _job_fetch_dark_pool(self):
        """Job: Fetch dark pool trading data"""
        try:
            logger.info("[JOB] Fetching dark pool activity...")
            scores = await self.dark_pool_tracker.get_component_scores()
            self.scoring_engine.update_dark_pool_scores(scores)
        except Exception as e:
            logger.error(f"Dark pool fetch job failed: {e}")
    
    async def _job_fetch_short_interest(self):
        """Job: Fetch short interest data"""
        try:
            logger.info("[JOB] Fetching short interest...")
            scores = await self.short_interest_tracker.get_component_scores()
            self.scoring_engine.update_short_interest_scores(scores)
        except Exception as e:
            logger.error(f"Short interest fetch job failed: {e}")
    
    async def _job_fetch_congressional(self):
        """Job: Fetch congressional trading data"""
        try:
            logger.info("[JOB] Fetching congressional trades...")
            scores = await self.congressional_tracker.get_component_scores()
            self.scoring_engine.update_congressional_scores(scores)
        except Exception as e:
            logger.error(f"Congressional fetch job failed: {e}")
    
    async def _job_fetch_on_chain(self):
        """Job: Fetch on-chain analytics"""
        try:
            logger.info("[JOB] Fetching on-chain data...")
            scores = await self.on_chain_analytics.get_component_scores()
            self.scoring_engine.update_on_chain_scores(scores)
        except Exception as e:
            logger.error(f"On-chain fetch job failed: {e}")
    
    async def _job_fetch_social_momentum(self):
        """Job: Fetch social momentum data"""
        try:
            logger.info("[JOB] Fetching social momentum...")
            scores = await self.social_momentum_tracker.get_component_scores()
            self.scoring_engine.update_social_momentum_scores(scores)
        except Exception as e:
            logger.error(f"Social momentum fetch job failed: {e}")
    
    async def _job_fetch_macro(self):
        """Job: Fetch macro indicators"""
        try:
            logger.info("[JOB] Fetching macro indicators...")
            scores = await self.macro_indicators.get_component_scores()
            self.scoring_engine.update_macro_scores(scores)
        except Exception as e:
            logger.error(f"Macro indicators fetch job failed: {e}")
    
    # ─────────────────────────────────────────────────────────────────────────────
    # JOB HANDLERS (SCORING & ALERTS)
    # ─────────────────────────────────────────────────────────────────────────────
    
    async def _job_score_and_alert(self):
        """Job: Generate scores and send alerts"""
        try:
            logger.info("[JOB] Running scoring cycle...")
            
            # Generate signals
            signals = self.scoring_engine.generate_signals()
            
            # Save all signals
            self.scoring_engine.save_signals(signals)
            
            # Filter for alerting
            alertable = self.scoring_engine.filter_for_alerting(signals)
            
            if alertable:
                logger.info(f"Found {len(alertable)} signals to alert")
                
                for signal in alertable:
                    logger.info(f"Alerting: {signal.asset_symbol} (score: {signal.final_score})")
                    await self.alert_dispatcher.dispatch(signal)
                    
                    # Record signal for outcome tracking (learning)
                    await self.outcome_tracker.record_signal(signal.to_dict())
            else:
                logger.info("No signals above threshold")
                
        except Exception as e:
            logger.error(f"Scoring/alert job failed: {e}")
    
    # ─────────────────────────────────────────────────────────────────────────────
    # JOB HANDLERS (LEARNING SYSTEM)
    # ─────────────────────────────────────────────────────────────────────────────
    
    async def _job_check_outcomes(self):
        """Job: Check outcomes of past predictions"""
        try:
            logger.info("[JOB] Checking prediction outcomes...")
            await self.outcome_tracker.check_outcomes()
        except Exception as e:
            logger.error(f"Outcome check job failed: {e}")
    
    async def _job_optimize_weights(self):
        """Job: Daily weight optimization based on outcomes"""
        try:
            logger.info("[JOB] Running weight optimization...")
            
            # Calculate optimal weights from 7-day outcomes
            new_weights = self.weight_optimizer.calculate_optimal_weights(timeframe="7d")
            
            # Get performance metrics
            report = self.performance_analyzer.get_accuracy_report(days=30)
            metrics = {
                "accuracy_1d": report.get("accuracy_1d"),
                "accuracy_7d": report.get("accuracy_7d"),
                "avg_return": report.get("avg_return_7d"),
                "predictions_analyzed": report.get("total_predictions", 0)
            }
            
            # Save new weights
            weights_id = self.weight_optimizer.save_learned_weights(new_weights, metrics)
            
            # Activate if we have enough data and accuracy is reasonable
            if metrics.get("predictions_analyzed", 0) >= 30:
                if metrics.get("accuracy_7d", 0) >= 50:  # Better than coin flip
                    self.weight_optimizer.activate_weights(weights_id)
                    logger.info(f"Activated new weights (accuracy: {metrics.get('accuracy_7d')}%)")
                else:
                    logger.info(f"New weights not activated (accuracy: {metrics.get('accuracy_7d')}% < 50%)")
            else:
                logger.info(f"Insufficient data for weight activation ({metrics.get('predictions_analyzed')} < 30)")
                
        except Exception as e:
            logger.error(f"Weight optimization job failed: {e}")
    
    async def _job_log_performance(self):
        """Job: Log daily performance metrics"""
        try:
            logger.info("[JOB] Logging daily performance...")
            self.performance_analyzer.log_daily_performance()
            
            # Also get and log cumulative stats
            stats = self.performance_analyzer.get_cumulative_stats()
            logger.info(f"Cumulative stats: {stats}")
        except Exception as e:
            logger.error(f"Performance log job failed: {e}")
    
    # ─────────────────────────────────────────────────────────────────────────────
    # JOB HANDLERS (MAINTENANCE)
    # ─────────────────────────────────────────────────────────────────────────────
    
    async def _job_cleanup(self):
        """Job: Clean up old database records"""
        try:
            logger.info("[JOB] Running database cleanup...")
            DatabaseOperations.cleanup_old_data(days=90)
        except Exception as e:
            logger.error(f"Cleanup job failed: {e}")
    
    # ─────────────────────────────────────────────────────────────────────────────
    # FULL CYCLE
    # ─────────────────────────────────────────────────────────────────────────────
    
    async def _run_full_cycle(self):
        """Run a complete data fetch and scoring cycle (all 11 fetchers)"""
        try:
            # Fetch all core data in parallel
            logger.info("Fetching core data sources...")
            await asyncio.gather(
                self._job_fetch_sec(),
                self._job_fetch_whales(),
                self._job_fetch_options(),
                self._job_fetch_fear_indices()
            )
            
            # Fetch all advanced data in parallel
            logger.info("Fetching advanced data sources...")
            await asyncio.gather(
                self._job_fetch_dark_pool(),
                self._job_fetch_short_interest(),
                self._job_fetch_congressional(),
                self._job_fetch_on_chain(),
                self._job_fetch_social_momentum(),
                self._job_fetch_macro()
            )
            
            # Sentiment analysis (runs separately due to API rate limits)
            await self._job_analyze_sentiment()
            
            # Score and alert
            await self._job_score_and_alert()
            
            logger.info("Full cycle complete - 11 data sources processed")
            
        except Exception as e:
            logger.error(f"Full cycle failed: {e}")
    
    # ─────────────────────────────────────────────────────────────────────────────
    # STATUS & DIAGNOSTICS
    # ─────────────────────────────────────────────────────────────────────────────
    
    def get_status(self) -> dict:
        """Get current engine status including learning metrics"""
        # Get cumulative performance stats
        try:
            perf_stats = self.performance_analyzer.get_cumulative_stats()
        except:
            perf_stats = {}
        
        # Get active weights
        try:
            active_weights = self.weight_optimizer.get_active_weights()
        except:
            active_weights = {}
        
        return {
            "running": self._running,
            "version": "2.0 (Enhanced with ML)",
            "scheduler_running": self.scheduler.running if self.scheduler else False,
            "data_sources": 11,
            "jobs": [
                {
                    "id": job.id,
                    "name": job.name,
                    "next_run": str(job.next_run_time) if job.next_run_time else None
                }
                for job in self.scheduler.get_jobs()
            ] if self.scheduler else [],
            "database_stats": DatabaseOperations.get_database_stats(),
            "market_summary": self.scoring_engine.get_market_summary(),
            "learning": {
                "active_weights": active_weights,
                "performance": perf_stats
            }
        }
    
    def get_performance_report(self, days: int = 30) -> dict:
        """Get detailed performance report for the last N days"""
        return self.performance_analyzer.get_accuracy_report(days=days)


# ─────────────────────────────────────────────────────────────────────────────────
# MAIN ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────────

async def main():
    """Main entry point"""
    orchestrator = MarketIntelOrchestrator()
    
    # Handle shutdown signals
    def handle_shutdown(sig, frame):
        logger.info(f"Received signal {sig}, shutting down...")
        asyncio.create_task(orchestrator.stop())
    
    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)
    
    try:
        await orchestrator.start()
    except KeyboardInterrupt:
        await orchestrator.stop()
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        await orchestrator.stop()
        sys.exit(1)


def run():
    """Synchronous entry point for command line"""
    asyncio.run(main())


if __name__ == "__main__":
    run()
