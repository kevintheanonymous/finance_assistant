# ═══════════════════════════════════════════════════════════════════════════════
# MARKET INTELLIGENCE ENGINE
# Autonomous Market Signal Aggregator
# ═══════════════════════════════════════════════════════════════════════════════

A 24/7 cloud-hosted engine that monitors informed actors (insiders, whales) across 
equities and crypto, aggregates multiple data signals, and delivers binary-style 
alerts when high-confidence patterns are detected.

## 🎯 What It Does

- **Tracks SEC Form 4 Filings** - Detects clusters of corporate insider buying
- **Monitors Whale Wallets** - Tracks large BTC/ETH movements on-chain
- **Analyzes Options Flow** - Detects unusual call volume spikes
- **AI Sentiment Analysis** - GPT-4 powered news/social sentiment
- **Fear Index Tracking** - VIX and Crypto Fear & Greed integration
- **Smart Alerting** - Only alerts when multiple signals confirm (no noise)

## 📁 Directory Structure

```
market_intel/
├── main.py                 # Entry point
├── diagnose.py             # Weekly diagnostic script
├── requirements.txt        # Python dependencies
├── .env.example            # Environment template (copy to .env)
├── .env                    # Your actual config (DO NOT COMMIT)
├── Procfile                # For Railway/Render deployment
├── railway.toml            # Railway config
├── render.yaml             # Render config
├── data/                   # SQLite database (auto-created)
├── logs/                   # Log files (auto-created)
└── src/
    ├── __init__.py
    ├── config.py           # Configuration management
    ├── database.py         # SQLAlchemy models & operations
    ├── scoring.py          # Signal aggregation & scoring logic
    ├── alerts.py           # Discord/Telegram dispatcher
    ├── engine.py           # Main orchestrator
    └── fetchers/
        ├── __init__.py
        ├── sec_filings.py  # SEC Form 4 parser
        ├── whale_alert.py  # Crypto whale tracker
        ├── options_flow.py # Options volume analyzer
        ├── sentiment.py    # AI sentiment analyzer
        └── fear_index.py   # VIX & Fear/Greed fetcher
```

## 🚀 Quick Start (Local)

### 1. Clone and Install

```powershell
# Navigate to project
cd c:\Users\ruthb\OneDrive\Desktop\money\market_intel

# Create virtual environment
python -m venv venv
.\venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Environment

```powershell
# Copy template
Copy-Item .env.example .env

# Edit .env with your API keys
notepad .env
```

**Required Keys:**
- `OPENAI_API_KEY` - For sentiment analysis
- `DISCORD_WEBHOOK_URL` or `TELEGRAM_BOT_TOKEN` - For alerts

**Optional Keys:**
- `FINNHUB_API_KEY` - Stock data (free tier available)
- `WHALE_ALERT_API_KEY` - Whale transactions (free tier available)

### 3. Test Configuration

```powershell
# Run diagnostics
python diagnose.py

# Send test alert
python main.py --test
```

### 4. Run the Engine

```powershell
# Run 24/7 (keep terminal open)
python main.py

# Or run one cycle for testing
python main.py --once
```

## ☁️ Cloud Deployment

### Option A: Railway.app (Recommended)

1. Create account at https://railway.app
2. Connect your GitHub (push this code to a repo)
3. Create new project → Deploy from GitHub
4. Add environment variables in Railway dashboard
5. Railway auto-detects the Procfile and deploys

**Terminal Commands:**
```powershell
# Initialize git (if needed)
git init
git add .
git commit -m "Initial commit"

# Push to GitHub
git remote add origin https://github.com/YOUR_USERNAME/market-intel.git
git push -u origin main
```

### Option B: Render.com

1. Create account at https://render.com
2. New → Background Worker
3. Connect GitHub repo
4. Add environment variables
5. Deploy

### Option C: DigitalOcean Droplet

```bash
# SSH into your droplet
ssh root@your-droplet-ip

# Install Python
apt update && apt install python3 python3-pip python3-venv -y

# Clone your repo
git clone https://github.com/YOUR_USERNAME/market-intel.git
cd market-intel

# Setup virtual environment
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Create .env and add your keys
nano .env

# Run with screen (keeps running after disconnect)
screen -S market_intel
python main.py

# Detach: Ctrl+A then D
# Reattach: screen -r market_intel
```

## 📊 Signal Scoring Logic

### Component Weights

| Component | Weight | Source |
|-----------|--------|--------|
| Insider Cluster | 20% | SEC Form 4 filings |
| Options Anomaly | 15% | Options volume vs baseline |
| Whale Movement | 20% | Exchange in/outflow |
| Stablecoin Mint | 10% | USDT/USDC supply |
| AI Sentiment | 20% | GPT-4 news analysis |
| Fear Index | 15% | VIX + Crypto F&G |

### Alert Thresholds

| Score | Classification | Action |
|-------|----------------|--------|
| 0-39 | Noise | Discarded silently |
| 40-59 | Weak | Logged only |
| 60-79 | Moderate | Alert with caution |
| **80-100** | **High-Confidence** | **Full alert** |

### Validation Rules

1. Score must meet minimum threshold (60)
2. At least 3 components must score >50
3. Asset cannot re-alert within 24 hour cooldown

## 🔧 Maintenance

### Weekly Diagnostic

```powershell
python diagnose.py
```

This checks:
- API connectivity and rate limits
- Database size and cleanup needs
- Alert channel health
- Signal quality metrics

### Database Cleanup

The system auto-cleans data older than 90 days. Manual cleanup:

```python
from src.database import DatabaseOperations
DatabaseOperations.cleanup_old_data(days=60)
```

### Adjusting Weights

Edit `src/config.py` → `ScoringWeights` class:

```python
class ScoringWeights:
    INSIDER_CLUSTER = 0.25      # Increase insider importance
    OPTIONS_ANOMALY = 0.15
    WHALE_MOVEMENT = 0.20
    STABLECOIN_MINT = 0.05      # Decrease stablecoin importance
    SENTIMENT_SCORE = 0.20
    FEAR_INDEX = 0.15
```

Ensure weights sum to 1.0!

## ⚠️ Operator Rules

### DO:
- Review each alert carefully before acting
- Wait for multiple confirmations across time (not just one alert)
- Use signals for research, not instant action
- Run diagnostics weekly

### DON'T:
- Auto-execute trades based on alerts
- Over-leverage based on "high confidence" signals
- Ignore the 24-hour cooldown (it exists for a reason)
- Assume the system predicts the future (it detects anomalies)

### Signal Interpretation:

```
HIGH-CONFIDENCE ≠ "Guaranteed to go up"
HIGH-CONFIDENCE = "Multiple independent data sources show unusual activity"
```

## 📝 License

MIT License - Use at your own risk. This is not financial advice.

## 🆘 Troubleshooting

### "No alerts received"
1. Run `python main.py --test` to verify webhook
2. Check .env has correct Discord/Telegram config
3. Check logs/ folder for errors

### "SEC fetch failing"
- SEC EDGAR has rate limits. The system handles this automatically.
- If persistent, increase `SEC_FILINGS_INTERVAL` in config.py

### "OpenAI errors"
- Check API key is valid
- Check OpenAI account has credits
- System falls back to rule-based sentiment if GPT fails

### "Database locked"
- Only run one instance of the engine at a time
- Delete `data/signals.db` to reset (loses history)
