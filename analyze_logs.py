#!/usr/bin/env python3
"""
Log Analysis Tool for IRONVAULT
Parses audit logs to summarize paper trading performance.
"""

import os
import re
import ast
import sys
from pathlib import Path
from datetime import datetime

LOG_DIR = Path("logs")

def find_latest_log():
    if not LOG_DIR.exists():
        return None
    files = list(LOG_DIR.glob("audit_*.log"))
    if not files:
        return None
    # Sort by name (which includes timestamp)
    return sorted(files)[-1]

def parse_log_line(line):
    # Format: YYYY-MM-DD HH:MM:SS | INFO | {json-like dict}
    try:
        parts = line.split(" | ", 2)
        if len(parts) < 3:
            return None
        
        timestamp_str = parts[0]
        # details part is a string representation of a dict
        details_str = parts[2].strip()
        
        # safely evaluate the dict string
        data = ast.literal_eval(details_str)
        return {"timestamp": timestamp_str, "data": data}
    except Exception:
        return None

def analyze_logs(log_file):
    print(f"📊 Analyzing log file: {log_file}")
    
    trades = []
    errors = 0
    
    with open(log_file, 'r', encoding='utf-8') as f:
        for line in f:
            entry = parse_log_line(line)
            if not entry:
                continue
                
            data = entry["data"]
            event_type = data.get("type")
            action = data.get("action")
            details = data.get("details", {})
            
            if action == "PAPER_TRADE_EXECUTED":
                trades.append({
                    "time": entry["timestamp"],
                    "strategy": details.get("strategy", "Unknown"),
                    "order_id": details.get("order_id"),
                    "params": details.get("params", {})
                })
            elif event_type == "SYSTEM_ERROR" or event_type == "POLICY_VIOLATION":
                errors += 1
                
    # Summary
    print(f"\n--- 📝 Paper Trading Summary ---")
    print(f"Total Trades Simulated: {len(trades)}")
    print(f"Errors/Violations Logged: {errors}")
    
    if not trades:
        print("\nNo paper trades found yet. Make sure the bot is RUNNING and strategies are active.")
        return

    print(f"\n--- 📋 Trade Details ---")
    
    by_strategy = {}
    
    for t in trades:
        strat = t["strategy"]
        if strat not in by_strategy:
            by_strategy[strat] = []
        by_strategy[strat].append(t)
        
        params = t["params"]
        side = params.get("side", "BUY")
        size = float(params.get("size", 0))
        price = float(params.get("price", 0))
        token = params.get("token_id", "???")[:10] + "..."
        
        print(f"[{t['time']}] {strat} | {side} {size} @ {price} | Token: {token}")

    print(f"\n--- 📈 Strategy Breakdown ---")
    for strat, t_list in by_strategy.items():
        count = len(t_list)
        total_vol = sum(float(t["params"].get("size", 0)) * float(t["params"].get("price", 0)) for t in t_list)
        print(f"{strat}: {count} trades | Est. Volume: ${total_vol:.2f}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        log_file = sys.argv[1]
    else:
        log_file = find_latest_log()
        
    if not log_file:
        print("❌ No log files found in logs/ directory.")
    else:
        analyze_logs(log_file)
