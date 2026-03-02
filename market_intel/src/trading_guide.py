# ═══════════════════════════════════════════════════════════════════════════════
# MARKET INTELLIGENCE ENGINE - TRADING GUIDE GENERATOR
# ═══════════════════════════════════════════════════════════════════════════════
"""
Generates actionable trading guidance based on signal analysis.

IMPORTANT DISCLAIMER:
This is NOT financial advice. These are algorithmic suggestions based on 
historical patterns. Always do your own research and never risk more than 
you can afford to lose.
"""

from typing import Dict, Tuple
from dataclasses import dataclass


@dataclass
class TradingGuide:
    """Complete trading guidance for a signal"""
    action: str  # BUY, SELL, HOLD, WATCH
    confidence: str  # HIGH, MEDIUM, LOW
    position_size_pct: float  # % of portfolio
    entry_timing: str
    entry_zones: Dict[str, float]  # current, aggressive, conservative
    take_profit_targets: list  # [TP1, TP2, TP3]
    stop_loss: float
    risk_reward_ratio: float
    hold_duration: str
    notes: list
    risk_level: str  # LOW, MEDIUM, HIGH


def generate_trading_guide(
    signal_score: float,
    asset_symbol: str,
    asset_type: str,  # "equity" or "crypto"
    component_scores: Dict[str, float],
    current_price: float = None
) -> TradingGuide:
    """
    Generate complete trading guidance based on signal analysis.
    
    Args:
        signal_score: Final signal score (0-100)
        asset_symbol: Asset ticker
        asset_type: "equity" or "crypto"
        component_scores: Dict of component scores
        current_price: Current asset price (optional)
    
    Returns:
        TradingGuide dataclass
    """
    
    # Determine action and confidence
    action, confidence = _determine_action(signal_score, component_scores)
    
    # Calculate position size based on confidence
    position_size = _calculate_position_size(signal_score, confidence, asset_type)
    
    # Determine entry timing
    entry_timing = _get_entry_timing(signal_score, component_scores, asset_type)
    
    # Calculate price targets (if price available)
    entry_zones, tp_targets, stop_loss = _calculate_price_levels(
        signal_score, asset_type, current_price, component_scores
    )
    
    # Calculate risk/reward
    if current_price and tp_targets and stop_loss:
        avg_tp = sum(tp_targets) / len(tp_targets)
        risk = abs(current_price - stop_loss)
        reward = abs(avg_tp - current_price)
        rr_ratio = reward / risk if risk > 0 else 0
    else:
        rr_ratio = _estimate_risk_reward(signal_score)
    
    # Determine hold duration
    hold_duration = _get_hold_duration(signal_score, asset_type, component_scores)
    
    # Generate notes/tips
    notes = _generate_notes(signal_score, component_scores, asset_type, action)
    
    # Determine risk level
    risk_level = _assess_risk_level(signal_score, component_scores, asset_type)
    
    return TradingGuide(
        action=action,
        confidence=confidence,
        position_size_pct=position_size,
        entry_timing=entry_timing,
        entry_zones=entry_zones,
        take_profit_targets=tp_targets,
        stop_loss=stop_loss,
        risk_reward_ratio=rr_ratio,
        hold_duration=hold_duration,
        notes=notes,
        risk_level=risk_level
    )


def _determine_action(score: float, components: Dict[str, float]) -> Tuple[str, str]:
    """Determine action and confidence level"""
    
    # Count strong components
    strong_count = sum(1 for v in components.values() if v > 70)
    moderate_count = sum(1 for v in components.values() if 50 < v <= 70)
    weak_count = sum(1 for v in components.values() if v <= 30)
    
    # Sentiment check
    sentiment = components.get("sentiment_score", 50)
    
    if score >= 80:
        action = "BUY"
        confidence = "HIGH"
    elif score >= 70:
        action = "BUY"
        confidence = "MEDIUM"
    elif score >= 60:
        if strong_count >= 2:
            action = "BUY"
            confidence = "MEDIUM"
        else:
            action = "WATCH"
            confidence = "LOW"
    elif score >= 50:
        action = "WATCH"
        confidence = "LOW"
    else:
        # Check for short signals
        if sentiment < 30 and weak_count >= 2:
            action = "AVOID"
            confidence = "MEDIUM"
        else:
            action = "HOLD"
            confidence = "LOW"
    
    return action, confidence


def _calculate_position_size(score: float, confidence: str, asset_type: str) -> float:
    """
    Calculate recommended position size as % of portfolio.
    Uses conservative risk management principles.
    """
    
    # Base sizes by confidence
    base_sizes = {
        "HIGH": 5.0,    # Max 5% for high confidence
        "MEDIUM": 3.0,  # Max 3% for medium
        "LOW": 1.0      # Max 1% for low
    }
    
    base = base_sizes.get(confidence, 1.0)
    
    # Adjust for score
    score_multiplier = score / 100
    
    # Crypto is more volatile, reduce size
    if asset_type == "crypto":
        volatility_factor = 0.6
    else:
        volatility_factor = 1.0
    
    position_size = base * score_multiplier * volatility_factor
    
    # Never exceed 5% per position
    return min(round(position_size, 1), 5.0)


def _get_entry_timing(score: float, components: Dict[str, float], asset_type: str) -> str:
    """Determine optimal entry timing"""
    
    fear_index = components.get("fear_index", 50)
    sentiment = components.get("sentiment_score", 50)
    
    if score >= 80:
        if fear_index > 70:  # Extreme fear = buy opportunity
            return "IMMEDIATE - Extreme fear presents best entry"
        else:
            return "TODAY - Strong signal, enter on any dip"
    
    elif score >= 70:
        if asset_type == "equity":
            return "WITHIN 1-2 DAYS - Wait for market open dip or use limit order 1-2% below"
        else:
            return "WITHIN 24H - Set limit order 2-3% below current, or accumulate in portions"
    
    elif score >= 60:
        if sentiment > 70:
            return "WAIT - High sentiment may mean near-term pullback. Set alerts for 5% dip"
        else:
            return "THIS WEEK - Accumulate in 3 portions over 3-5 days"
    
    else:
        return "NO ENTRY - Add to watchlist, wait for score >65"


def _calculate_price_levels(
    score: float, 
    asset_type: str, 
    current_price: float,
    components: Dict[str, float]
) -> Tuple[Dict, list, float]:
    """Calculate entry zones, take profit targets, and stop loss"""
    
    if not current_price:
        # Return percentage-based guidance
        if score >= 70:
            entry_zones = {
                "market": "Current price",
                "limit": "-1% to -2%",
                "aggressive": "Market order OK"
            }
            tp_targets = ["+8%", "+15%", "+25%"]
            stop_loss = "-5%"
        else:
            entry_zones = {
                "market": "Avoid market orders",
                "limit": "-3% to -5%",
                "aggressive": "Not recommended"
            }
            tp_targets = ["+5%", "+10%", "+15%"]
            stop_loss = "-7%"
        
        return entry_zones, tp_targets, stop_loss
    
    # Price-based calculations
    if asset_type == "crypto":
        # Crypto: wider ranges due to volatility
        if score >= 80:
            entry_aggressive = current_price
            entry_limit = current_price * 0.97
            entry_conservative = current_price * 0.95
            tp1 = current_price * 1.10
            tp2 = current_price * 1.20
            tp3 = current_price * 1.35
            sl = current_price * 0.92
        elif score >= 70:
            entry_aggressive = current_price * 0.98
            entry_limit = current_price * 0.95
            entry_conservative = current_price * 0.90
            tp1 = current_price * 1.08
            tp2 = current_price * 1.15
            tp3 = current_price * 1.25
            sl = current_price * 0.90
        else:
            entry_aggressive = current_price * 0.95
            entry_limit = current_price * 0.90
            entry_conservative = current_price * 0.85
            tp1 = current_price * 1.05
            tp2 = current_price * 1.10
            tp3 = current_price * 1.18
            sl = current_price * 0.88
    else:
        # Equity: tighter ranges
        if score >= 80:
            entry_aggressive = current_price
            entry_limit = current_price * 0.98
            entry_conservative = current_price * 0.97
            tp1 = current_price * 1.08
            tp2 = current_price * 1.15
            tp3 = current_price * 1.25
            sl = current_price * 0.95
        elif score >= 70:
            entry_aggressive = current_price * 0.99
            entry_limit = current_price * 0.97
            entry_conservative = current_price * 0.95
            tp1 = current_price * 1.06
            tp2 = current_price * 1.12
            tp3 = current_price * 1.20
            sl = current_price * 0.93
        else:
            entry_aggressive = current_price * 0.97
            entry_limit = current_price * 0.95
            entry_conservative = current_price * 0.92
            tp1 = current_price * 1.04
            tp2 = current_price * 1.08
            tp3 = current_price * 1.15
            sl = current_price * 0.92
    
    entry_zones = {
        "aggressive": round(entry_aggressive, 2),
        "limit": round(entry_limit, 2),
        "conservative": round(entry_conservative, 2)
    }
    
    tp_targets = [round(tp1, 2), round(tp2, 2), round(tp3, 2)]
    stop_loss = round(sl, 2)
    
    return entry_zones, tp_targets, stop_loss


def _estimate_risk_reward(score: float) -> float:
    """Estimate R:R ratio based on score"""
    if score >= 80:
        return 3.0
    elif score >= 70:
        return 2.5
    elif score >= 60:
        return 2.0
    else:
        return 1.5


def _get_hold_duration(score: float, asset_type: str, components: Dict[str, float]) -> str:
    """Recommend hold duration based on signal characteristics"""
    
    insider = components.get("insider_cluster", 0)
    options = components.get("options_anomaly", 0)
    whale = components.get("whale_movement", 0)
    congressional = components.get("congressional", 0)
    
    # Insider/Congressional signals = longer term
    if insider > 70 or congressional > 70:
        return "2-6 WEEKS - Insider signals typically play out over weeks"
    
    # Options anomaly = shorter term
    if options > 70:
        return "3-10 DAYS - Options activity suggests near-term catalyst"
    
    # Whale movements
    if whale > 70:
        if asset_type == "crypto":
            return "1-4 WEEKS - Whale accumulation precedes moves"
        else:
            return "2-8 WEEKS - Institutional accumulation"
    
    # Default by score
    if score >= 80:
        return "1-4 WEEKS - Strong signal, ride the trend"
    elif score >= 70:
        return "1-2 WEEKS - Take profits at first target"
    else:
        return "3-7 DAYS - Quick trade, tight stops"


def _generate_notes(
    score: float, 
    components: Dict[str, float], 
    asset_type: str,
    action: str
) -> list:
    """Generate contextual trading notes"""
    notes = []
    
    # Position sizing note
    if score >= 80:
        notes.append("💰 Strong signal - can size up but never exceed 5% portfolio")
    elif score >= 70:
        notes.append("💰 Moderate signal - keep position size 2-3% of portfolio")
    else:
        notes.append("💰 Lower confidence - use small position (1% max)")
    
    # Entry strategy
    if action == "BUY":
        notes.append("📈 Consider DCA: Split entry into 2-3 portions over 2-3 days")
    
    # Take profit strategy
    if score >= 70:
        notes.append("🎯 Take profit strategy: Sell 30% at TP1, 40% at TP2, let 30% ride to TP3")
    else:
        notes.append("🎯 Conservative exit: Take 50% at TP1, 50% at TP2")
    
    # Stop loss
    notes.append("🛑 ALWAYS set stop loss before entering - move to breakeven after TP1 hit")
    
    # Component-specific notes
    if components.get("fear_index", 50) > 75:
        notes.append("😱 Extreme fear = opportunity - but expect volatility")
    elif components.get("fear_index", 50) < 25:
        notes.append("😊 Extreme greed - markets may be overheated, use tighter stops")
    
    if components.get("sentiment_score", 50) > 80:
        notes.append("📰 Strong positive sentiment - watch for 'buy the rumor, sell the news'")
    
    if components.get("options_anomaly", 0) > 70:
        notes.append("📊 High options activity - potential catalyst within 1-2 weeks")
    
    if components.get("insider_cluster", 0) > 70:
        notes.append("👔 Insider buying cluster - historically 60%+ accurate over 6 months")
    
    if components.get("whale_movement", 0) > 70:
        notes.append("🐋 Whale accumulation detected - smart money moving")
    
    if components.get("congressional", 0) > 70:
        notes.append("🏛️ Congressional trading detected - may have info edge")
    
    if asset_type == "crypto":
        notes.append("⚠️ Crypto volatility: Expect 10-20% swings, size accordingly")
    
    # Risk reminder
    notes.append("⚠️ NOT financial advice - DYOR and only risk what you can afford to lose")
    
    return notes


def _assess_risk_level(score: float, components: Dict[str, float], asset_type: str) -> str:
    """Assess overall risk level of the trade"""
    
    risk_score = 0
    
    # Score-based risk
    if score >= 80:
        risk_score += 1
    elif score >= 70:
        risk_score += 2
    else:
        risk_score += 3
    
    # Confirmation count
    strong_count = sum(1 for v in components.values() if v > 70)
    if strong_count >= 4:
        risk_score -= 1
    elif strong_count <= 1:
        risk_score += 1
    
    # Fear/greed
    fear = components.get("fear_index", 50)
    if fear < 25 or fear > 80:  # Extremes add risk
        risk_score += 1
    
    # Asset type
    if asset_type == "crypto":
        risk_score += 1
    
    # Map to level
    if risk_score <= 2:
        return "LOW"
    elif risk_score <= 4:
        return "MEDIUM"
    else:
        return "HIGH"


def format_trading_guide_telegram(guide: TradingGuide, symbol: str) -> str:
    """Format trading guide for Telegram message"""
    
    # Action emoji
    action_emoji = {
        "BUY": "🟢",
        "SELL": "🔴",
        "HOLD": "🟡",
        "WATCH": "👀",
        "AVOID": "⛔"
    }.get(guide.action, "⚪")
    
    # Risk emoji
    risk_emoji = {
        "LOW": "🟢",
        "MEDIUM": "🟡",
        "HIGH": "🔴"
    }.get(guide.risk_level, "⚪")
    
    lines = []
    lines.append("")
    lines.append("━━━━━━━━━━━━━━━━━━")
    lines.append(f"<b>📋 TRADING GUIDE</b>")
    lines.append("━━━━━━━━━━━━━━━━━━")
    lines.append("")
    lines.append(f"{action_emoji} <b>Action:</b> {guide.action}")
    lines.append(f"📊 <b>Confidence:</b> {guide.confidence}")
    lines.append(f"{risk_emoji} <b>Risk Level:</b> {guide.risk_level}")
    lines.append(f"💼 <b>Position Size:</b> {guide.position_size_pct}% of portfolio")
    lines.append("")
    
    lines.append(f"<b>⏰ Entry Timing:</b>")
    lines.append(f"   {guide.entry_timing}")
    lines.append("")
    
    if guide.entry_zones:
        lines.append(f"<b>🎯 Entry Zones:</b>")
        for zone, value in guide.entry_zones.items():
            lines.append(f"   • {zone.title()}: {value}")
        lines.append("")
    
    if guide.take_profit_targets:
        lines.append(f"<b>💰 Take Profit Targets:</b>")
        for i, tp in enumerate(guide.take_profit_targets, 1):
            lines.append(f"   TP{i}: {tp}")
        lines.append("")
    
    if guide.stop_loss:
        lines.append(f"<b>🛑 Stop Loss:</b> {guide.stop_loss}")
    
    lines.append(f"<b>⚖️ Risk/Reward:</b> 1:{guide.risk_reward_ratio:.1f}")
    lines.append(f"<b>⏱️ Hold Duration:</b> {guide.hold_duration}")
    lines.append("")
    
    lines.append("<b>📝 Notes:</b>")
    for note in guide.notes[:5]:  # Limit to 5 notes for readability
        lines.append(f"• {note}")
    
    return "\n".join(lines)


def format_trading_guide_discord(guide: TradingGuide, symbol: str) -> str:
    """Format trading guide for Discord message"""
    
    lines = []
    lines.append("")
    lines.append("─────────────────────────────────────")
    lines.append("**📋 TRADING GUIDE:**")
    lines.append("─────────────────────────────────────")
    lines.append("")
    lines.append(f"**Action:** {guide.action} ({guide.confidence} confidence)")
    lines.append(f"**Risk Level:** {guide.risk_level}")
    lines.append(f"**Position Size:** {guide.position_size_pct}% of portfolio")
    lines.append("")
    lines.append(f"**⏰ Entry Timing:**")
    lines.append(f"{guide.entry_timing}")
    lines.append("")
    
    if guide.entry_zones:
        lines.append(f"**🎯 Entry Zones:**")
        for zone, value in guide.entry_zones.items():
            lines.append(f"• {zone.title()}: {value}")
        lines.append("")
    
    if guide.take_profit_targets:
        lines.append(f"**💰 Take Profit Targets:**")
        for i, tp in enumerate(guide.take_profit_targets, 1):
            lines.append(f"TP{i}: {tp}")
        lines.append("")
    
    lines.append(f"**🛑 Stop Loss:** {guide.stop_loss}")
    lines.append(f"**⚖️ Risk:Reward:** 1:{guide.risk_reward_ratio:.1f}")
    lines.append(f"**⏱️ Duration:** {guide.hold_duration}")
    lines.append("")
    
    lines.append("**📝 Key Notes:**")
    for note in guide.notes[:5]:
        lines.append(f"• {note}")
    
    return "\n".join(lines)
