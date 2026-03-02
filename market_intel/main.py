#!/usr/bin/env python3
# ═══════════════════════════════════════════════════════════════════════════════
# MARKET INTELLIGENCE ENGINE - ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════
"""
Main entry point for the Market Intelligence Engine.

Usage:
    python main.py              # Run the engine (24/7 mode)
    python main.py --test       # Send test alerts
    python main.py --status     # Check engine status
    python main.py --diagnose   # Run diagnostics
"""

import argparse
import asyncio
import sys

def main():
    parser = argparse.ArgumentParser(
        description="Market Intelligence Engine - Autonomous Signal Aggregator"
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Send test alerts to verify Discord/Telegram configuration"
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Show current engine status and market summary"
    )
    parser.add_argument(
        "--diagnose",
        action="store_true",
        help="Run full diagnostic check on all APIs and connections"
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run one full cycle then exit (useful for testing)"
    )
    
    args = parser.parse_args()
    
    if args.test:
        asyncio.run(run_test_alerts())
    elif args.status:
        asyncio.run(run_status_check())
    elif args.diagnose:
        asyncio.run(run_diagnostics())
    elif args.once:
        asyncio.run(run_single_cycle())
    else:
        # Run the engine in 24/7 mode
        from src.engine import run
        run()


async def run_test_alerts():
    """Send test alerts to verify configuration"""
    print("=" * 60)
    print("MARKET INTELLIGENCE ENGINE - TEST ALERTS")
    print("=" * 60)
    
    from src.alerts import AlertDispatcher
    
    dispatcher = AlertDispatcher()
    results = await dispatcher.send_test_alert()
    await dispatcher.close()
    
    print("\nResults:")
    print(f"  Discord: {'✅ Success' if results['discord'] else '❌ Failed'}")
    print(f"  Telegram: {'✅ Success' if results['telegram'] else '❌ Failed'}")
    
    if not any(results.values()):
        print("\n⚠️  No alerts were sent. Check your .env configuration.")
        sys.exit(1)
    
    print("\n✅ Test complete!")


async def run_status_check():
    """Show current engine status"""
    print("=" * 60)
    print("MARKET INTELLIGENCE ENGINE - STATUS")
    print("=" * 60)
    
    from src.database import DatabaseOperations
    
    DatabaseOperations.init_db()
    stats = DatabaseOperations.get_database_stats()
    
    print("\n📊 Database Statistics:")
    print(f"  Signals recorded: {stats.get('signals_count', 0)}")
    print(f"  Insider filings: {stats.get('insider_filings_count', 0)}")
    print(f"  Whale transactions: {stats.get('whale_transactions_count', 0)}")
    print(f"  Active cooldowns: {stats.get('cooldowns_count', 0)}")
    print(f"  Database size: {stats.get('database_size_mb', 0):.2f} MB")
    
    # Show recent signals
    recent = DatabaseOperations.get_recent_signals(hours=24, min_score=60)
    
    print(f"\n🚨 Signals (last 24h, score >= 60): {len(recent)}")
    for sig in recent[:5]:
        print(f"  • {sig.asset_symbol}: {sig.signal_score:.0f} ({sig.signal_type}) @ {sig.detected_at}")


async def run_diagnostics():
    """Run full diagnostic check"""
    print("=" * 60)
    print("MARKET INTELLIGENCE ENGINE - DIAGNOSTICS")
    print("=" * 60)
    
    from src.config import APIKeys, AlertConfig, validate_config
    from src.database import DatabaseOperations
    import httpx
    
    # Check configuration
    print("\n🔧 Configuration:")
    config_valid = validate_config()
    print(f"  Config valid: {'✅' if config_valid else '⚠️ Warnings'}")
    
    # Check API keys
    print("\n🔑 API Keys:")
    print(f"  OpenAI: {'✅ Set' if APIKeys.OPENAI else '❌ Missing'}")
    print(f"  Finnhub: {'✅ Set' if APIKeys.FINNHUB else '❌ Missing'}")
    print(f"  Whale Alert: {'✅ Set' if APIKeys.WHALE_ALERT else '⚪ Optional'}")
    print(f"  Unusual Whales: {'✅ Set' if APIKeys.UNUSUAL_WHALES else '⚪ Optional'}")
    
    # Check alert config
    print("\n📢 Alert Channels:")
    print(f"  Discord: {'✅ Configured' if AlertConfig.DISCORD_WEBHOOK_URL else '❌ Not set'}")
    print(f"  Telegram: {'✅ Configured' if AlertConfig.TELEGRAM_BOT_TOKEN else '❌ Not set'}")
    
    # Test API connectivity
    print("\n🌐 API Connectivity:")
    async with httpx.AsyncClient(timeout=10.0) as client:
        # Test SEC
        try:
            r = await client.get("https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=4&count=1&output=atom")
            print(f"  SEC EDGAR: {'✅ OK' if r.status_code == 200 else f'⚠️ {r.status_code}'}")
        except Exception as e:
            print(f"  SEC EDGAR: ❌ {e}")
        
        # Test Finnhub
        if APIKeys.FINNHUB:
            try:
                r = await client.get(f"https://finnhub.io/api/v1/quote?symbol=AAPL&token={APIKeys.FINNHUB}")
                print(f"  Finnhub: {'✅ OK' if r.status_code == 200 else f'⚠️ {r.status_code}'}")
            except Exception as e:
                print(f"  Finnhub: ❌ {e}")
        
        # Test Crypto Fear & Greed
        try:
            r = await client.get("https://api.alternative.me/fng/")
            print(f"  Crypto F&G: {'✅ OK' if r.status_code == 200 else f'⚠️ {r.status_code}'}")
        except Exception as e:
            print(f"  Crypto F&G: ❌ {e}")
    
    # Database
    print("\n💾 Database:")
    try:
        DatabaseOperations.init_db()
        stats = DatabaseOperations.get_database_stats()
        print(f"  Status: ✅ Connected")
        print(f"  Size: {stats.get('database_size_mb', 0):.2f} MB")
    except Exception as e:
        print(f"  Status: ❌ {e}")
    
    print("\n✅ Diagnostics complete!")


async def run_single_cycle():
    """Run one complete cycle"""
    print("=" * 60)
    print("MARKET INTELLIGENCE ENGINE - SINGLE CYCLE")
    print("=" * 60)
    
    from src.engine import MarketIntelOrchestrator
    
    orchestrator = MarketIntelOrchestrator()
    
    try:
        await orchestrator._run_full_cycle()
        
        # Show results
        status = orchestrator.get_status()
        summary = status.get("market_summary", {})
        
        print("\n📊 Market Summary:")
        print(f"  Equity regime: {summary.get('equity', {}).get('regime', 'unknown')}")
        print(f"  Crypto regime: {summary.get('crypto', {}).get('regime', 'unknown')}")
        
        print("\n✅ Single cycle complete!")
        
    finally:
        await orchestrator.stop()


if __name__ == "__main__":
    main()
