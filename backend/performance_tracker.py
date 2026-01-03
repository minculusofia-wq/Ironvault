"""
Performance Tracker Module
Persistent storage of trade history and PnL calculation using SQLite.
"""

import sqlite3
import json
import time
from pathlib import Path
from typing import Any, Optional
from dataclasses import dataclass
from .audit_logger import AuditLogger

@dataclass
class TradeRecord:
    trade_id: str
    strategy: str
    order_type: str
    symbol: str
    side: str
    price: float
    size: float
    pnl: float
    timestamp: float
    details: str  # JSON string

class PerformanceTracker:
    """
    Handles persistent storage and analysis of trading performance.
    """
    
    def __init__(self, audit_logger: AuditLogger, db_dir: str = "data"):
        self._audit = audit_logger
        self._db_dir = Path(db_dir)
        self._db_dir.mkdir(parents=True, exist_ok=True)
        self._db_path = self._db_dir / "performance.db"
        
        self._init_db()
        self._audit.log_system_event("PERFORMANCE_TRACKER_INIT", {"db_path": str(self._db_path)})
    
    def _init_db(self):
        """Initialize SQLite database and tables."""
        conn = sqlite3.connect(self._db_path)
        cursor = conn.cursor()
        
        # Trades table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS trades (
                id TEXT PRIMARY KEY,
                strategy TEXT,
                order_type TEXT,
                symbol TEXT,
                side TEXT,
                price REAL,
                size REAL,
                pnl REAL,
                timestamp REAL,
                details TEXT
            )
        ''')
        
        # Daily stats table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS daily_stats (
                date TEXT PRIMARY KEY,
                total_trades INTEGER,
                total_pnl REAL,
                win_rate REAL,
                max_drawdown REAL
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def record_trade(self, trade: TradeRecord):
        """Record a completed trade to persistent storage."""
        try:
            conn = sqlite3.connect(self._db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT OR REPLACE INTO trades 
                (id, strategy, order_type, symbol, side, price, size, pnl, timestamp, details)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                trade.trade_id, trade.strategy, trade.order_type, trade.symbol,
                trade.side, trade.price, trade.size, trade.pnl, 
                trade.timestamp, trade.details
            ))
            
            conn.commit()
            conn.close()
        except Exception as e:
            self._audit.log_error("DB_RECORD_TRADE_ERROR", str(e))
    
    def get_summary_stats(self, strategy: Optional[str] = None) -> dict[str, Any]:
        """Calculate summary statistics with simple caching to prevent UI freeze."""
        now = time.time()
        
        # Use simple cache if query is the same and recent
        cache_key = strategy or "GLOBAL"
        if not hasattr(self, "_stats_cache"):
            self._stats_cache = {}
            
        cached = self._stats_cache.get(cache_key)
        if cached and (now - cached["time"] < 5.0):
            return cached["data"]

        try:
            conn = sqlite3.connect(self._db_path)
            cursor = conn.cursor()
            
            query = "SELECT COUNT(*), SUM(pnl), AVG(pnl) FROM trades"
            params = []
            if strategy:
                query += " WHERE strategy = ?"
                params.append(strategy)
            
            cursor.execute(query, params)
            count, total_pnl, avg_pnl = cursor.fetchone()
            
            # Win rate
            win_query = "SELECT COUNT(*) FROM trades WHERE pnl > 0"
            if strategy:
                win_query += " AND strategy = ?"
            cursor.execute(win_query, params)
            wins = cursor.fetchone()[0]
            
            win_rate = (wins / count * 100) if count and count > 0 else 0
            
            conn.close()
            
            data = {
                "total_trades": count or 0,
                "total_pnl": total_pnl or 0.0,
                "avg_pnl": avg_pnl or 0.0,
                "win_rate": win_rate
            }
            
            self._stats_cache[cache_key] = {"time": now, "data": data}
            return data
            
        except Exception as e:
            self._audit.log_error("DB_STATS_SUMMARY_ERROR", str(e))
            return {"error": str(e)}

    def get_recent_trades(self, limit: int = 50) -> list[dict]:
        """Get latest N trades."""
        try:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute("SELECT * FROM trades ORDER BY timestamp DESC LIMIT ?", (limit,))
            rows = cursor.fetchall()
            
            results = [dict(row) for row in rows]
            conn.close()
            return results
        except Exception as e:
            self._audit.log_error("DB_GET_TRADES_ERROR", str(e))
            return []
