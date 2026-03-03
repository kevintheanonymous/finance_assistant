#!/usr/bin/env python3
"""
Web wrapper for Render free tier deployment.
Runs the market intelligence engine as a background thread while serving a simple health endpoint.
Also runs the Telegram bot for interactive commands.
"""

import os
import threading
import asyncio
from http.server import HTTPServer, BaseHTTPRequestHandler
import json
from datetime import datetime, timezone

# Global status tracking
engine_status = {
    "started_at": None,
    "last_cycle": None,
    "signals_today": 0,
    "status": "starting",
    "bot_status": "starting"
}

class HealthHandler(BaseHTTPRequestHandler):
    """Simple HTTP handler for health checks and status."""
    
    def do_GET(self):
        if self.path == "/" or self.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            response = {
                "status": "running",
                "engine": engine_status,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            self.wfile.write(json.dumps(response).encode())
        elif self.path == "/status":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(engine_status).encode())
        else:
            self.send_response(404)
            self.end_headers()
    
    def log_message(self, format, *args):
        # Suppress HTTP logs
        pass

def run_engine():
    """Run the market intelligence engine in background."""
    global engine_status
    engine_status["started_at"] = datetime.now(timezone.utc).isoformat()
    engine_status["status"] = "running"
    
    try:
        from src.engine import run
        run()
    except Exception as e:
        engine_status["status"] = f"error: {str(e)}"

def run_telegram_bot():
    """Run the Telegram bot for interactive commands."""
    global engine_status
    
    try:
        from src.telegram_bot import get_bot
        bot = get_bot()
        engine_status["bot_status"] = "running"
        print("Telegram bot started - listening for commands...")
        
        # Run the async polling loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(bot.start_polling())
    except Exception as e:
        engine_status["bot_status"] = f"error: {str(e)}"
        print(f"Telegram bot error: {e}")

def main():
    # Start engine in background thread
    engine_thread = threading.Thread(target=run_engine, daemon=True)
    engine_thread.start()
    
    # Start Telegram bot in background thread
    bot_thread = threading.Thread(target=run_telegram_bot, daemon=True)
    bot_thread.start()
    
    # Start HTTP server for health checks
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    print(f"Health server running on port {port}")
    print("Market Intelligence Engine running in background...")
    print("Telegram bot accepting commands...")
    server.serve_forever()

if __name__ == "__main__":
    main()
