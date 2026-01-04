"""
Audit Logger Module
Write-only logging of all operator actions and state transitions.
Structured format with timestamps.

v3.0: Added log rotation and disk space protection.
"""

import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime
from pathlib import Path
from enum import Enum
from typing import Any
import os


class EventType(Enum):
    """Types of auditable events."""
    OPERATOR_ACTION = "OPERATOR_ACTION"
    STATE_TRANSITION = "STATE_TRANSITION"
    CAPITAL_CHANGE = "CAPITAL_CHANGE"
    STRATEGY_EVENT = "STRATEGY_EVENT"
    POLICY_VIOLATION = "POLICY_VIOLATION"
    KILL_SWITCH = "KILL_SWITCH"
    SYSTEM_ERROR = "SYSTEM_ERROR"


class AuditLogger:
    """
    Write-only audit logger with rotation.
    All actions are logged with timestamps in structured format.
    """

    # v3.0: Log rotation settings
    MAX_LOG_SIZE_MB = 10  # Max size per log file
    MAX_BACKUP_COUNT = 5  # Keep 5 backup files
    MAX_TOTAL_LOGS_MB = 100  # Max total log folder size

    def __init__(self, log_dir: str = "logs"):
        self._log_dir = Path(log_dir)
        self._log_dir.mkdir(parents=True, exist_ok=True)

        # v3.0: Cleanup old logs if folder is too large
        self._cleanup_old_logs()

        self._log_file = self._log_dir / f"audit_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

        self._logger = logging.getLogger("audit")
        self._logger.setLevel(logging.INFO)
        self._logger.handlers.clear()

        # v3.0: Use RotatingFileHandler for automatic rotation
        file_handler = RotatingFileHandler(
            self._log_file,
            maxBytes=self.MAX_LOG_SIZE_MB * 1024 * 1024,
            backupCount=self.MAX_BACKUP_COUNT,
            encoding='utf-8'
        )
        file_handler.setLevel(logging.INFO)

        formatter = logging.Formatter(
            '%(asctime)s | %(levelname)s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(formatter)

        self._logger.addHandler(file_handler)

        self.log(EventType.OPERATOR_ACTION, "AUDIT_LOGGER_INITIALIZED", {
            "log_file": str(self._log_file)
        })

    def _cleanup_old_logs(self) -> None:
        """Remove old log files if total size exceeds limit."""
        try:
            log_files = sorted(
                self._log_dir.glob("audit_*.log*"),
                key=lambda f: f.stat().st_mtime
            )

            total_size = sum(f.stat().st_size for f in log_files)
            max_bytes = self.MAX_TOTAL_LOGS_MB * 1024 * 1024

            # Remove oldest files until under limit
            while total_size > max_bytes and len(log_files) > 1:
                oldest = log_files.pop(0)
                total_size -= oldest.stat().st_size
                oldest.unlink()
                print(f"[AuditLogger] Removed old log: {oldest.name}")

        except Exception as e:
            print(f"[AuditLogger] Cleanup error: {e}")
    
    import re
    _HEX_64_RE = re.compile(r'([0-9a-fA-F]{64})')
    _REDACTED = "***REDACTED***"
    _MAX_STRING_LEN = 1000

    def log(self, event_type: EventType, action: str, details: dict[str, Any] | None = None) -> None:
        """
        Log an auditable event with automated redaction.
        """
        redacted_details = self._redact(details) if details else {}
        entry = {
            "type": event_type.value,
            "action": action,
            "details": redacted_details
        }
        self._logger.info(f"{entry}")

    def _redact(self, data: Any) -> Any:
        """Recursively redact sensitive information."""
        if isinstance(data, dict):
            return {k: self._redact(v) if not self._is_sensitive_key(k) else self._REDACTED 
                    for k, v in data.items()}
        if isinstance(data, list):
            return [self._redact(item) for item in data]
        if isinstance(data, str):
            # Mask hex keys (like private keys)
            redacted = self._HEX_64_RE.sub(self._REDACTED, data)
            # Truncate if too long
            if len(redacted) > self._MAX_STRING_LEN:
                return redacted[:self._MAX_STRING_LEN] + "... [TRUNCATED]"
            return redacted
        return data

    def _is_sensitive_key(self, key: str) -> bool:
        """Check if a dictionary key likely contains sensitive data."""
        sensitive_patterns = {
            "api_key", "secret", "private_key", "password", 
            "token", "credential", "passphrase", "vault"
        }
        key_lower = key.lower()
        return any(pattern in key_lower for pattern in sensitive_patterns)
    
    def log_operator_action(self, action: str, details: dict[str, Any] | None = None) -> None:
        """Log an operator-initiated action."""
        self.log(EventType.OPERATOR_ACTION, action, details)
    
    def log_state_transition(self, from_state: str, to_state: str, reason: str) -> None:
        """Log a state machine transition."""
        self.log(EventType.STATE_TRANSITION, "STATE_CHANGE", {
            "from": from_state,
            "to": to_state,
            "reason": reason
        })
    
    def log_capital_change(self, pool: str, old_value: float, new_value: float, reason: str) -> None:
        """Log a capital pool change."""
        self.log(EventType.CAPITAL_CHANGE, "CAPITAL_UPDATE", {
            "pool": pool,
            "old_value": old_value,
            "new_value": new_value,
            "reason": reason
        })
    
    def log_strategy_event(self, strategy: str, event: str, details: dict[str, Any] | None = None) -> None:
        """Log a strategy-related event."""
        self.log(EventType.STRATEGY_EVENT, event, {
            "strategy": strategy,
            **(details or {})
        })
    
    def log_policy_violation(self, action: str, reason: str) -> None:
        """Log a policy violation (blocked action)."""
        self.log(EventType.POLICY_VIOLATION, "VIOLATION_BLOCKED", {
            "attempted_action": action,
            "reason": reason
        })
    
    def log_kill_switch(self, trigger: str, details: dict[str, Any] | None = None) -> None:
        """Log a kill switch activation."""
        self.log(EventType.KILL_SWITCH, "KILL_SWITCH_TRIGGERED", {
            "trigger": trigger,
            **(details or {})
        })

    def log_error(self, action: str, message: str) -> None:
        """Log a system error."""
        self.log(EventType.SYSTEM_ERROR, action, {"message": message})
    
    def log_system_event(self, action: str, details: dict[str, Any] | None = None) -> None:
        """Log a system-level event."""
        self.log(EventType.OPERATOR_ACTION, action, details)
    
    @property
    def log_file_path(self) -> str:
        """Path to current log file."""
        return str(self._log_file)
