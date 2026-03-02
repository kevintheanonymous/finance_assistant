#!/usr/bin/env python3
# ═══════════════════════════════════════════════════════════════════════════════
# MARKET INTELLIGENCE ENGINE - WEEKLY DIAGNOSTIC SCRIPT
# ═══════════════════════════════════════════════════════════════════════════════
"""
Run this script weekly to check system health.

Usage:
    python diagnose.py

Checks:
    - API connectivity and rate limit status
    - Database size and cleanup needs
    - Alert delivery health
    - Signal quality metrics
"""

import asyncio
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

async def run_diagnostics():
    """Run comprehensive system diagnostics"""
    print("═" * 70)
    print("MARKET INTELLIGENCE ENGINE - WEEKLY DIAGNOSTIC REPORT")
    print(f"Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC")
    print("═" * 70)
    
    issues = []
    warnings = []
    
    # ─────────────────────────────────────────────────────────────────────────
    # 1. CONFIGURATION CHECK
    # ─────────────────────────────────────────────────────────────────────────
    print("\n" + "─" * 70)
    print("1. CONFIGURATION")
    print("─" * 70)
    
    from src.config import APIKeys, AlertConfig
    
    # Required APIs
    api_status = {
        "OpenAI": bool(APIKeys.OPENAI),
        "Finnhub": bool(APIKeys.FINNHUB),
    }
    
    # Optional APIs
    optional_apis = {
        "Whale Alert": bool(APIKeys.WHALE_ALERT),
        "Unusual Whales": bool(APIKeys.UNUSUAL_WHALES),
        "Twitter/X": bool(APIKeys.TWITTER_BEARER),
    }
    
    print("\n  Required APIs:")
    for name, configured in api_status.items():
        status = "✅ Configured" if configured else "❌ MISSING"
        print(f"    {name}: {status}")
        if not configured:
            issues.append(f"{name} API key is missing")
    
    print("\n  Optional APIs:")
    for name, configured in optional_apis.items():
        status = "✅ Configured" if configured else "⚪ Not set"
        print(f"    {name}: {status}")
    
    print("\n  Alert Channels:")
    discord_ok = bool(AlertConfig.DISCORD_WEBHOOK_URL)
    telegram_ok = bool(AlertConfig.TELEGRAM_BOT_TOKEN and AlertConfig.TELEGRAM_CHAT_ID)
    print(f"    Discord: {'✅ Configured' if discord_ok else '❌ Not set'}")
    print(f"    Telegram: {'✅ Configured' if telegram_ok else '⚪ Not set'}")
    
    if not discord_ok and not telegram_ok:
        issues.append("No alert channels configured")
    
    # ─────────────────────────────────────────────────────────────────────────
    # 2. API CONNECTIVITY TEST
    # ─────────────────────────────────────────────────────────────────────────
    print("\n" + "─" * 70)
    print("2. API CONNECTIVITY")
    print("─" * 70)
    
    import httpx
    
    async with httpx.AsyncClient(timeout=15.0) as client:
        api_tests = [
            ("SEC EDGAR", "https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=4&count=1&output=atom", None),
            ("Crypto Fear & Greed", "https://api.alternative.me/fng/", None),
            ("Yahoo Finance (VIX)", "https://query1.finance.yahoo.com/v8/finance/chart/%5EVIX", None),
        ]
        
        if APIKeys.FINNHUB:
            api_tests.append(("Finnhub", f"https://finnhub.io/api/v1/quote?symbol=AAPL&token={APIKeys.FINNHUB}", None))
        
        print()
        for name, url, headers in api_tests:
            try:
                r = await client.get(url, headers=headers or {})
                if r.status_code == 200:
                    print(f"    {name}: ✅ OK (latency: {r.elapsed.total_seconds()*1000:.0f}ms)")
                elif r.status_code == 429:
                    print(f"    {name}: ⚠️ RATE LIMITED")
                    warnings.append(f"{name} is rate limited")
                else:
                    print(f"    {name}: ⚠️ Status {r.status_code}")
                    warnings.append(f"{name} returned status {r.status_code}")
            except Exception as e:
                print(f"    {name}: ❌ ERROR - {str(e)[:50]}")
                issues.append(f"{name} connectivity failed")
    
    # ─────────────────────────────────────────────────────────────────────────
    # 3. DATABASE HEALTH
    # ─────────────────────────────────────────────────────────────────────────
    print("\n" + "─" * 70)
    print("3. DATABASE HEALTH")
    print("─" * 70)
    
    from src.database import DatabaseOperations
    
    try:
        DatabaseOperations.init_db()
        stats = DatabaseOperations.get_database_stats()
        
        print(f"\n    Total signals: {stats.get('signals_count', 0):,}")
        print(f"    Insider filings: {stats.get('insider_filings_count', 0):,}")
        print(f"    Whale transactions: {stats.get('whale_transactions_count', 0):,}")
        print(f"    Active cooldowns: {stats.get('cooldowns_count', 0):,}")
        
        db_size = stats.get('database_size_mb', 0)
        print(f"    Database size: {db_size:.2f} MB")
        
        if db_size > 100:
            warnings.append(f"Database size is {db_size:.0f}MB - consider running cleanup")
        if db_size > 500:
            issues.append(f"Database size is {db_size:.0f}MB - cleanup required")
            
    except Exception as e:
        print(f"\n    ❌ Database error: {e}")
        issues.append("Database connection failed")
    
    # ─────────────────────────────────────────────────────────────────────────
    # 4. SIGNAL QUALITY METRICS
    # ─────────────────────────────────────────────────────────────────────────
    print("\n" + "─" * 70)
    print("4. SIGNAL QUALITY (Last 7 Days)")
    print("─" * 70)
    
    try:
        recent_signals = DatabaseOperations.get_recent_signals(hours=168)  # 7 days
        
        if recent_signals:
            high_conf = [s for s in recent_signals if s.signal_score >= 80]
            moderate = [s for s in recent_signals if 60 <= s.signal_score < 80]
            
            print(f"\n    Total signals generated: {len(recent_signals)}")
            print(f"    High-confidence (≥80): {len(high_conf)}")
            print(f"    Moderate (60-79): {len(moderate)}")
            
            if high_conf:
                avg_score = sum(s.signal_score for s in high_conf) / len(high_conf)
                print(f"    Avg high-conf score: {avg_score:.1f}")
            
            # Top assets
            from collections import Counter
            asset_counts = Counter(s.asset_symbol for s in recent_signals if s.signal_score >= 60)
            if asset_counts:
                print(f"\n    Top signaling assets:")
                for asset, count in asset_counts.most_common(5):
                    print(f"      {asset}: {count} signals")
        else:
            print("\n    No signals in the last 7 days")
            warnings.append("No signals generated in 7 days - check data fetchers")
            
    except Exception as e:
        print(f"\n    ❌ Error retrieving signals: {e}")
    
    # ─────────────────────────────────────────────────────────────────────────
    # 5. ALERT DELIVERY TEST
    # ─────────────────────────────────────────────────────────────────────────
    print("\n" + "─" * 70)
    print("5. ALERT DELIVERY")
    print("─" * 70)
    
    from src.alerts import AlertDispatcher
    
    dispatcher = AlertDispatcher()
    
    print("\n    Testing connectivity (not sending)...")
    
    if AlertConfig.DISCORD_WEBHOOK_URL:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                # Discord webhook check (GET returns method not allowed, which means it's valid)
                r = await client.get(AlertConfig.DISCORD_WEBHOOK_URL)
                if r.status_code in [200, 405]:
                    print(f"    Discord webhook: ✅ Valid")
                else:
                    print(f"    Discord webhook: ⚠️ Status {r.status_code}")
                    warnings.append("Discord webhook may be invalid")
        except Exception as e:
            print(f"    Discord webhook: ❌ Error")
            issues.append("Discord webhook unreachable")
    
    if AlertConfig.TELEGRAM_BOT_TOKEN:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.get(f"https://api.telegram.org/bot{AlertConfig.TELEGRAM_BOT_TOKEN}/getMe")
                if r.status_code == 200:
                    print(f"    Telegram bot: ✅ Valid")
                else:
                    print(f"    Telegram bot: ⚠️ Status {r.status_code}")
                    warnings.append("Telegram bot token may be invalid")
        except Exception as e:
            print(f"    Telegram bot: ❌ Error")
            issues.append("Telegram bot unreachable")
    
    await dispatcher.close()
    
    # ─────────────────────────────────────────────────────────────────────────
    # SUMMARY
    # ─────────────────────────────────────────────────────────────────────────
    print("\n" + "═" * 70)
    print("DIAGNOSTIC SUMMARY")
    print("═" * 70)
    
    if issues:
        print(f"\n❌ ISSUES ({len(issues)}):")
        for issue in issues:
            print(f"    • {issue}")
    
    if warnings:
        print(f"\n⚠️ WARNINGS ({len(warnings)}):")
        for warning in warnings:
            print(f"    • {warning}")
    
    if not issues and not warnings:
        print("\n✅ All systems healthy!")
    
    print("\n" + "═" * 70)
    
    # Return exit code
    return 1 if issues else 0


if __name__ == "__main__":
    exit_code = asyncio.run(run_diagnostics())
    sys.exit(exit_code)
