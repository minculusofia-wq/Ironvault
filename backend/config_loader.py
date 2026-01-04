"""
Config Loader Module
Loads and validates configuration from JSON file.
No default values - all parameters must be explicit.
"""

import json
from pathlib import Path
from typing import Any
from dataclasses import dataclass
from urllib.parse import urlparse


@dataclass
class CapitalConfig:
    total: float
    max_allocation_strategy_a: float
    max_allocation_strategy_b: float


@dataclass
class StrategyAConfig:
    enabled: bool
    name: str
    max_events: int = 5
    trade_size_percent: float = 1.0
    min_volume: float = 1000.0  # Used for filtering initial discovery
    latency_target_ms: int = 50  # Desired max latency for triggers
    min_odds: float = 1.01  # Minimum odds threshold
    max_odds: float = 100.0  # Maximum odds threshold
    exit_config: dict | None = None  # Dynamic exit configuration
    trigger_cooldown_seconds: float = 5.0  # Cooldown between triggers
    orderbook_cache_ttl_ms: int = 150  # Orderbook cache TTL in ms


@dataclass
class StrategyBConfig:
    enabled: bool
    name: str
    spread_min: float
    spread_max: float
    max_exposure: float
    trade_size_percent: float = 1.0  # Default 1%
    spread_config: dict | None = None  # Dynamic spread configuration
    market_config: dict | None = None  # Market discovery configuration


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
    paper_trading: bool = False


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
        'strategy_a': ['enabled', 'name', 'trade_size_percent'],
        'strategy_b': ['enabled', 'name', 'spread_min', 'spread_max', 'max_exposure', 'trade_size_percent'],
        'risk': ['max_drawdown_percent', 'max_daily_loss', 'kill_switch_threshold'],
        'market': ['connection_timeout_seconds', 'heartbeat_interval_seconds', 'paper_trading']
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
        if not (0 < strategy_a.get('trade_size_percent', 0) <= 100):
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
    
    def _validate_endpoint(self, url: str, section: str, key: str) -> str:
        """Validate that a URL/Endpoint is well-formed and safe."""
        if not url:
            return url
            
        try:
            parsed = urlparse(url)
            # Basic scheme validation
            if parsed.scheme not in ('http', 'https', 'ws', 'wss'):
                raise ConfigValidationError(f"Invalid scheme in {section}.{key}: {parsed.scheme}")
            
            # Basic hostname validation (must have a domain)
            if not parsed.netloc:
                raise ConfigValidationError(f"Invalid hostname in {section}.{key}")
                
            return url
        except Exception as e:
            if isinstance(e, ConfigValidationError):
                raise
            raise ConfigValidationError(f"Malformed URL in {section}.{key}: {str(e)}")

    def _build_config(self, data: dict[str, Any], file_path: str) -> BotConfig:
        """Build typed configuration object from validated data."""
        market_data = data['market']
        
        # Security: Validate endpoints
        rpc_url = self._validate_endpoint(market_data.get('rpc_url', ""), 'market', 'rpc_url')
        clob_api_url = self._validate_endpoint(market_data.get('clob_api_url', ""), 'market', 'clob_api_url')
        gamma_api_url = self._validate_endpoint(market_data.get('gamma_api_url', ""), 'market', 'gamma_api_url')

        market_config = MarketConfig(
            connection_timeout_seconds=market_data.get('connection_timeout_seconds', 30),
            heartbeat_interval_seconds=market_data.get('heartbeat_interval_seconds', 5),
            rpc_url=rpc_url or "https://polygon-rpc.com",
            clob_api_url=clob_api_url or "https://clob.polymarket.com/",
            gamma_api_url=gamma_api_url or "https://gamma-api.polymarket.com/",
            paper_trading=market_data.get('paper_trading', False)
        )
        
        # Handle optional config fields that might be missing in older configs
        strat_a_data = data['strategy_a'].copy()
        if 'min_volume' not in strat_a_data:
            strat_a_data['min_volume'] = 1000.0

        return BotConfig(
            capital=CapitalConfig(**data['capital']),
            strategy_a=StrategyAConfig(**strat_a_data),
            strategy_b=StrategyBConfig(**data['strategy_b']),
            risk=RiskConfig(**data['risk']),
            market=market_config,
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
