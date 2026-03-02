# ═══════════════════════════════════════════════════════════════════════════════
# MARKET INTELLIGENCE ENGINE - ALERT DISPATCHER
# ═══════════════════════════════════════════════════════════════════════════════
"""
Sends alerts via Discord webhook and/or Telegram bot.
Formats signals into human-readable messages.
"""

from datetime import datetime
from typing import Optional, Dict

import httpx
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from .config import AlertConfig
from .database import DatabaseOperations
from .scoring import Signal
from .trading_guide import generate_trading_guide, format_trading_guide_telegram, format_trading_guide_discord

# ─────────────────────────────────────────────────────────────────────────────────
# ALERT TEMPLATES
# ─────────────────────────────────────────────────────────────────────────────────

DISCORD_TEMPLATE = """
═══════════════════════════════════════
🚨 **MARKET INTELLIGENCE ALERT**
═══════════════════════════════════════

📊 **SIGNAL TYPE:** {signal_type_emoji} {signal_type} (Score: {score}/100)
🏷️ **ASSET:** ${symbol} ({asset_type})
📅 **TIMESTAMP:** {timestamp} UTC

─────────────────────────────────────
**SIGNAL COMPONENTS:**
─────────────────────────────────────
{components}

─────────────────────────────────────
**INTERPRETATION:**
─────────────────────────────────────
{interpretation}
{trading_guide}

═══════════════════════════════════════
"""

TELEGRAM_TEMPLATE = """
🚨 <b>{signal_type_emoji} {signal_type}</b> (Score: {score}/100)

<b>Asset:</b> ${symbol} ({asset_type})
<b>Time:</b> {timestamp} UTC

{components}
{trading_guide}

⚡ <i>Signal detected. Review trading guide above.</i>
"""

# ─────────────────────────────────────────────────────────────────────────────────
# ALERT DISPATCHER CLASS
# ─────────────────────────────────────────────────────────────────────────────────

class AlertDispatcher:
    """
    Sends formatted alerts to Discord and Telegram.
    
    Features:
    - Retry logic for reliability
    - Rate limiting awareness
    - Cooldown management
    - Delivery confirmation
    """
    
    def __init__(self):
        self.discord_webhook = AlertConfig.DISCORD_WEBHOOK_URL
        self.telegram_token = AlertConfig.TELEGRAM_BOT_TOKEN
        self.telegram_chat_id = AlertConfig.TELEGRAM_CHAT_ID
        self.client = httpx.AsyncClient(timeout=30.0)
    
    async def close(self):
        """Close the HTTP client"""
        await self.client.aclose()
    
    # ─────────────────────────────────────────────────────────────────────────────
    # MAIN DISPATCH METHOD
    # ─────────────────────────────────────────────────────────────────────────────
    
    async def dispatch(self, signal: Signal) -> bool:
        """
        Send alert for a signal via all configured channels.
        
        Args:
            signal: The Signal object to alert on
            
        Returns:
            True if at least one channel succeeded
        """
        success = False
        
        # Try Discord
        if self.discord_webhook:
            try:
                discord_success = await self._send_discord(signal)
                if discord_success:
                    success = True
                    logger.info(f"Discord alert sent for {signal.asset_symbol}")
            except Exception as e:
                logger.error(f"Discord alert failed: {e}")
        
        # Try Telegram
        if self.telegram_token and self.telegram_chat_id:
            try:
                telegram_success = await self._send_telegram(signal)
                if telegram_success:
                    success = True
                    logger.info(f"Telegram alert sent for {signal.asset_symbol}")
            except Exception as e:
                logger.error(f"Telegram alert failed: {e}")
        
        # Set cooldown if alert was sent
        if success:
            DatabaseOperations.set_cooldown(signal.asset_symbol)
        
        return success
    
    # ─────────────────────────────────────────────────────────────────────────────
    # DISCORD
    # ─────────────────────────────────────────────────────────────────────────────
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def _send_discord(self, signal: Signal) -> bool:
        """
        Send alert to Discord webhook.
        
        Args:
            signal: Signal to alert on
            
        Returns:
            True if successful
        """
        message = self._format_discord_message(signal)
        
        payload = {
            "content": message,
            "username": "Market Intelligence Bot",
            "avatar_url": "https://i.imgur.com/4M34hi2.png"  # Generic chart icon
        }
        
        response = await self.client.post(
            self.discord_webhook,
            json=payload
        )
        
        if response.status_code == 429:
            # Rate limited
            retry_after = response.json().get("retry_after", 5)
            logger.warning(f"Discord rate limited, retry after {retry_after}s")
            await asyncio.sleep(retry_after)
            raise Exception("Rate limited")
        
        response.raise_for_status()
        return True
    
    def _format_discord_message(self, signal: Signal) -> str:
        """Format signal for Discord"""
        # Determine emoji
        if signal.signal_type == "high_confidence":
            signal_type_emoji = "🔴"
            signal_type_text = "HIGH-CONFIDENCE SIGNAL"
        else:
            signal_type_emoji = "🟡"
            signal_type_text = "MODERATE SIGNAL"
        
        # Format components
        components_lines = []
        
        cs = signal.component_scores
        
        if signal.asset_type == "equity":
            if cs.get("insider_cluster", 0) > 50:
                components_lines.append(f"✅ Insider Activity: Score {cs['insider_cluster']:.0f}")
            else:
                components_lines.append(f"⚪ Insider Activity: Score {cs.get('insider_cluster', 0):.0f}")
            
            if cs.get("options_anomaly", 0) > 50:
                components_lines.append(f"✅ Options Flow: Score {cs['options_anomaly']:.0f}")
            else:
                components_lines.append(f"⚪ Options Flow: Score {cs.get('options_anomaly', 0):.0f}")
        
        else:  # crypto
            if cs.get("whale_movement", 0) > 50:
                components_lines.append(f"✅ Whale Movement: Score {cs['whale_movement']:.0f}")
            else:
                components_lines.append(f"⚪ Whale Movement: Score {cs.get('whale_movement', 0):.0f}")
            
            if cs.get("stablecoin_mint", 0) > 50:
                components_lines.append(f"✅ Stablecoin Flow: Score {cs['stablecoin_mint']:.0f}")
            else:
                components_lines.append(f"⚪ Stablecoin Flow: Score {cs.get('stablecoin_mint', 0):.0f}")
        
        # Common components
        if cs.get("sentiment_score", 0) > 60:
            components_lines.append(f"✅ AI Sentiment: BULLISH ({cs['sentiment_score']:.0f})")
        elif cs.get("sentiment_score", 50) < 40:
            components_lines.append(f"❌ AI Sentiment: BEARISH ({cs['sentiment_score']:.0f})")
        else:
            components_lines.append(f"⚪ AI Sentiment: NEUTRAL ({cs.get('sentiment_score', 50):.0f})")
        
        fear_score = cs.get("fear_index", 50)
        if fear_score > 60:
            components_lines.append(f"✅ Fear Index: Favorable ({fear_score:.0f})")
        elif fear_score < 40:
            components_lines.append(f"⚠️ Fear Index: Caution ({fear_score:.0f})")
        else:
            components_lines.append(f"⚪ Fear Index: Neutral ({fear_score:.0f})")
        
        components_text = "\n".join(components_lines)
        
        # Generate interpretation
        interpretation = self._generate_interpretation(signal)
        
        # Generate trading guide
        guide = generate_trading_guide(
            signal_score=signal.final_score,
            asset_symbol=signal.asset_symbol,
            asset_type=signal.asset_type,
            component_scores=signal.component_scores,
            current_price=signal.raw_data.get("current_price") if signal.raw_data else None
        )
        trading_guide_text = format_trading_guide_discord(guide, signal.asset_symbol)
        
        return DISCORD_TEMPLATE.format(
            signal_type_emoji=signal_type_emoji,
            signal_type=signal_type_text,
            score=int(signal.final_score),
            symbol=signal.asset_symbol,
            asset_type=signal.asset_type.upper(),
            timestamp=signal.detected_at.strftime("%Y-%m-%d %H:%M"),
            components=components_text,
            interpretation=interpretation,
            trading_guide=trading_guide_text
        )
    
    # ─────────────────────────────────────────────────────────────────────────────
    # TELEGRAM
    # ─────────────────────────────────────────────────────────────────────────────
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def _send_telegram(self, signal: Signal) -> bool:
        """
        Send alert to Telegram bot.
        
        Args:
            signal: Signal to alert on
            
        Returns:
            True if successful
        """
        message = self._format_telegram_message(signal)
        
        url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"
        
        payload = {
            "chat_id": self.telegram_chat_id,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        }
        
        response = await self.client.post(url, json=payload)
        
        if response.status_code == 429:
            retry_after = response.json().get("parameters", {}).get("retry_after", 5)
            logger.warning(f"Telegram rate limited, retry after {retry_after}s")
            await asyncio.sleep(retry_after)
            raise Exception("Rate limited")
        
        response.raise_for_status()
        return True
    
    def _format_telegram_message(self, signal: Signal) -> str:
        """Format signal for Telegram (compact version)"""
        # Determine emoji
        if signal.signal_type == "high_confidence":
            signal_type_emoji = "🔴"
            signal_type_text = "HIGH-CONFIDENCE"
        else:
            signal_type_emoji = "🟡"
            signal_type_text = "MODERATE"
        
        # Format components (compact)
        components_lines = []
        cs = signal.component_scores
        
        if signal.asset_type == "equity":
            insider = "✅" if cs.get("insider_cluster", 0) > 50 else "⚪"
            options = "✅" if cs.get("options_anomaly", 0) > 50 else "⚪"
            components_lines.append(f"{insider} Insiders: {cs.get('insider_cluster', 0):.0f}")
            components_lines.append(f"{options} Options: {cs.get('options_anomaly', 0):.0f}")
        else:
            whale = "✅" if cs.get("whale_movement", 0) > 50 else "⚪"
            stable = "✅" if cs.get("stablecoin_mint", 0) > 50 else "⚪"
            components_lines.append(f"{whale} Whales: {cs.get('whale_movement', 0):.0f}")
            components_lines.append(f"{stable} Stables: {cs.get('stablecoin_mint', 0):.0f}")
        
        sentiment_score = cs.get("sentiment_score", 50)
        if sentiment_score > 60:
            sentiment = "✅ Bullish"
        elif sentiment_score < 40:
            sentiment = "❌ Bearish"
        else:
            sentiment = "⚪ Neutral"
        components_lines.append(f"{sentiment}")
        
        components_text = "\n".join(components_lines)
        
        # Generate trading guide
        guide = generate_trading_guide(
            signal_score=signal.final_score,
            asset_symbol=signal.asset_symbol,
            asset_type=signal.asset_type,
            component_scores=signal.component_scores,
            current_price=signal.raw_data.get("current_price") if signal.raw_data else None
        )
        trading_guide_text = format_trading_guide_telegram(guide, signal.asset_symbol)
        
        return TELEGRAM_TEMPLATE.format(
            signal_type_emoji=signal_type_emoji,
            signal_type=signal_type_text,
            score=int(signal.final_score),
            symbol=signal.asset_symbol,
            asset_type=signal.asset_type.upper(),
            timestamp=signal.detected_at.strftime("%Y-%m-%d %H:%M"),
            components=components_text,
            trading_guide=trading_guide_text
        )
    
    # ─────────────────────────────────────────────────────────────────────────────
    # INTERPRETATION GENERATOR
    # ─────────────────────────────────────────────────────────────────────────────
    
    def _generate_interpretation(self, signal: Signal) -> str:
        """
        Generate human-readable interpretation of the signal.
        
        Args:
            signal: Signal to interpret
            
        Returns:
            Interpretation text
        """
        cs = signal.component_scores
        parts = []
        
        if signal.asset_type == "equity":
            if cs.get("insider_cluster", 0) > 60:
                parts.append("Corporate insiders are buying")
            if cs.get("options_anomaly", 0) > 60:
                parts.append("unusual call option activity detected")
        else:
            if cs.get("whale_movement", 0) > 60:
                parts.append("Large holders are accumulating")
            if cs.get("stablecoin_mint", 0) > 60:
                parts.append("stablecoin inflows elevated")
        
        if cs.get("sentiment_score", 50) > 70:
            parts.append("news sentiment is strongly positive")
        elif cs.get("sentiment_score", 50) < 30:
            parts.append("but news sentiment is negative")
        
        if not parts:
            return "Multiple data points showing coordinated movement. This is NOT a prediction. This is anomaly detection."
        
        interpretation = ", ".join(parts) + "."
        interpretation += "\n\nThis is NOT a prediction. This is anomaly detection."
        
        return interpretation
    
    # ─────────────────────────────────────────────────────────────────────────────
    # TEST ALERT
    # ─────────────────────────────────────────────────────────────────────────────
    
    async def send_test_alert(self) -> Dict[str, bool]:
        """
        Send a test alert to verify configuration.
        
        Returns:
            Dict with success status for each channel
        """
        results = {"discord": False, "telegram": False}
        
        test_message = """
═══════════════════════════════════════
🧪 **TEST ALERT**
═══════════════════════════════════════

This is a test message from Market Intelligence Engine.
If you received this, your alerts are configured correctly!

Timestamp: {timestamp} UTC
═══════════════════════════════════════
""".format(timestamp=datetime.utcnow().strftime("%Y-%m-%d %H:%M"))
        
        # Test Discord
        if self.discord_webhook:
            try:
                response = await self.client.post(
                    self.discord_webhook,
                    json={"content": test_message, "username": "Market Intel Test"}
                )
                response.raise_for_status()
                results["discord"] = True
                logger.info("Discord test alert sent successfully")
            except Exception as e:
                logger.error(f"Discord test failed: {e}")
        
        # Test Telegram
        if self.telegram_token and self.telegram_chat_id:
            try:
                url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"
                response = await self.client.post(url, json={
                    "chat_id": self.telegram_chat_id,
                    "text": test_message.replace("**", ""),
                    "parse_mode": "Markdown"
                })
                response.raise_for_status()
                results["telegram"] = True
                logger.info("Telegram test alert sent successfully")
            except Exception as e:
                logger.error(f"Telegram test failed: {e}")
        
        return results


# Import for sleep in rate limiting
import asyncio
