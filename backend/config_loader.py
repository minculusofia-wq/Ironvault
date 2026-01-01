"""
Config Loader Module
Loads and validates configuration from JSON file.
No default values - all parameters must be explicit.
"""

import json
from pathlib import Path
from typing import Any
from dataclasses import dataclass


@dataclass
class CapitalConfig:
    total: float
    max_allocation_strategy_a: float
    max_allocation_strategy_b: float


@dataclass
class StrategyAConfig:
    enabled: bool
    name: str
    max_events: int
    min_odds: float
    max_events: int
    min_odds: float
    max_odds: float
    trade_size_percent: float = 1.0  # Default 1%


@dataclass
class StrategyBConfig:
    enabled: bool
    name: str
    spread_min: float
    spread_max: float
    spread_min: float
    spread_max: float
    max_exposure: float
    trade_size_percent: float = 1.0  # Default 1%


@dataclass
class RiskConfig:
    max_drawdown_percent: float
    max_daily_loss: float
    kill_switch_threshold: float


@dataclass
class MarketConfig:
    connection_timeout_seconds: int
    heartbeat_interval_seconds: int
    rpc_url: str = "https://polygon-rpc.com"  # Default public RPC
    clob_api_url: str = "https://clob.polymarket.com/"
    gamma_api_url: str = "https://gamma-api.polymarket.com/"


@dataclass
class BotConfig:
    capital: CapitalConfig
    strategy_a: StrategyAConfig
    strategy_b: StrategyBConfig
    risk: RiskConfig
    market: MarketConfig
    file_path: str


class ConfigValidationError(Exception):
    """Raised when configuration validation fails."""
    pass


class ConfigLoader:
    """Loads and validates bot configuration from JSON file."""
    
    REQUIRED_KEYS = {
        'capital': ['total', 'max_allocation_strategy_a', 'max_allocation_strategy_b'],
        'strategy_a': ['enabled', 'name', 'max_events', 'min_odds', 'max_odds', 'trade_size_percent'],
        'strategy_b': ['enabled', 'name', 'spread_min', 'spread_max', 'max_exposure', 'trade_size_percent'],
        'risk': ['max_drawdown_percent', 'max_daily_loss', 'kill_switch_threshold'],
        'market': ['connection_timeout_seconds', 'heartbeat_interval_seconds']
    }
    
    def __init__(self):
        self._config: BotConfig | None = None
    
    def load(self, file_path: str) -> BotConfig:
        """
        Load configuration from JSON file.
        Raises ConfigValidationError if validation fails.
        """
        path = Path(file_path)
        
        if not path.exists():
            raise ConfigValidationError(f"Config file not found: {file_path}")
        
        if not path.suffix == '.json':
            raise ConfigValidationError("Config file must be JSON format")
        
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            raise ConfigValidationError(f"Invalid JSON: {e}")
        
        self._validate_structure(data)
        self._validate_values(data)
        
        self._config = self._build_config(data, str(path))
        return self._config
    
    def _validate_structure(self, data: dict[str, Any]) -> None:
        """Validate all required keys are present."""
        for section, keys in self.REQUIRED_KEYS.items():
            if section not in data:
                raise ConfigValidationError(f"Missing section: {section}")
            
            for key in keys:
                if key not in data[section]:
                    raise ConfigValidationError(f"Missing key: {section}.{key}")
    
    def _validate_values(self, data: dict[str, Any]) -> None:
        """Validate configuration values are within acceptable ranges."""
        capital = data['capital']
        
        if capital['total'] <= 0:
            raise ConfigValidationError("capital.total must be positive")
        
        if capital['max_allocation_strategy_a'] < 0:
            raise ConfigValidationError("capital.max_allocation_strategy_a cannot be negative")
        
        if capital['max_allocation_strategy_b'] < 0:
            raise ConfigValidationError("capital.max_allocation_strategy_b cannot be negative")
        
        total_allocation = capital['max_allocation_strategy_a'] + capital['max_allocation_strategy_b']
        if total_allocation > capital['total']:
            raise ConfigValidationError(
                "Sum of strategy allocations exceeds total capital"
            )
        
        strategy_a = data['strategy_a']
        if strategy_a['min_odds'] >= strategy_a['max_odds']:
            raise ConfigValidationError("strategy_a.min_odds must be less than max_odds")
        
        if not (0 < strategy_a['trade_size_percent'] <= 100):
            raise ConfigValidationError("strategy_a.trade_size_percent must be between 0 and 100")
        
        strategy_b = data['strategy_b']
        if strategy_b['spread_min'] >= strategy_b['spread_max']:
            raise ConfigValidationError("strategy_b.spread_min must be less than spread_max")
            
        if not (0 < strategy_b['trade_size_percent'] <= 100):
            raise ConfigValidationError("strategy_b.trade_size_percent must be between 0 and 100")
        
        risk = data['risk']
        if risk['max_drawdown_percent'] <= 0 or risk['max_drawdown_percent'] > 100:
            raise ConfigValidationError("risk.max_drawdown_percent must be between 0 and 100")
        
        if risk['kill_switch_threshold'] <= 0:
            raise ConfigValidationError("risk.kill_switch_threshold must be positive")
    
    def _build_config(self, data: dict[str, Any], file_path: str) -> BotConfig:
        """Build typed configuration object from validated data."""
        return BotConfig(
            capital=CapitalConfig(**data['capital']),
            strategy_a=StrategyAConfig(**data['strategy_a']),
            strategy_b=StrategyBConfig(**data['strategy_b']),
            risk=RiskConfig(**data['risk']),
            market=MarketConfig(**data['market']),
            file_path=file_path
        )
    
    @property
    def config(self) -> BotConfig | None:
        """Current loaded configuration."""
        return self._config
    

            
    @property
    def is_loaded(self) -> bool:
        """Whether a valid configuration is loaded."""
        return self._config is not None
