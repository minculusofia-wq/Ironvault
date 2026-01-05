"""
ExecutionEngine Module (Async)
Executor that runs a background async task to process the order queue.
Wraps synchronous CLOB client calls in a thread executor to prevent blocking.

v2.5 Optimizations:
- Position tracking for PnL calculation (FIFO)
- Realistic paper trading with slippage simulation
- Fill probability based on liquidity
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Callable, List
import asyncio
import time
import random

from .audit_logger import AuditLogger
from .rate_limiter import RateLimiter
from py_clob_client.client import ClobClient, ApiCreds
from py_clob_client.clob_types import OrderArgs


@dataclass
class Position:
    """Represents a position entry for PnL tracking."""
    price: float
    size: float
    timestamp: float
    order_id: str

# Import for type hint only - avoid circular import
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .credentials_manager import CredentialsManager


class OrderStatus(Enum):
    """Status of an order."""
    PENDING = "PENDING"
    EXECUTING = "EXECUTING"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"


@dataclass
class Order:
    """Represents an order to execute."""
    order_id: str
    strategy: str
    order_type: str
    params: dict
    status: OrderStatus = OrderStatus.PENDING
    result: dict | None = None


class ExecutionEngine:
    """
    Async Execution Engine.
    Processes orders from a queue asynchronously.
    """
    
    def __init__(self, audit_logger: AuditLogger):
        self._audit = audit_logger
        self._orders: dict[str, Order] = {}
        self._order_queue: asyncio.Queue = asyncio.Queue()
        self._order_counter = 0
        self._enabled = False
        self._credentials: "CredentialsManager | None" = None
        self._clob_client: ClobClient | None = None
        
        # v3.0: Rate Limiter (50 req/s burst 100) - increased for better throughput
        self._rate_limiter = RateLimiter(max_tokens=100, refill_rate=50)

        # API Config Defaults
        self._host = "https://clob.polymarket.com"
        self._chain_id = 137  # Polygon Mainnet

        self._status_callbacks: list[Callable[[Order], None]] = []
        self._processing_task: asyncio.Task | None = None

        # v2.5: Position tracking for PnL calculation (FIFO)
        self._positions: dict[str, List[Position]] = {}  # token_id -> [Position entries]
        self._realized_pnl: dict[str, float] = {}  # token_id -> cumulative PnL
        self._total_realized_pnl: float = 0.0

        # v3.0: Paper trading simulation config (enhanced)
        self._paper_config = {
            'slippage_base': 0.0008,     # 0.08% base slippage
            'slippage_min': 0.0003,      # 0.03% minimum slippage
            'slippage_max': 0.008,       # 0.8% maximum slippage
            'slippage_size_factor': 0.001,  # Additional slippage per $100 size
            'fill_probability': 0.92,    # 92% base fill rate
            'latency_min_ms': 30,        # Minimum latency
            'latency_max_ms': 150,       # Maximum latency
            'partial_fill_chance': 0.10, # 10% chance of partial fill
            'depth_impact_factor': 0.0005  # Market impact factor
        }
    
    def configure_api(self, host: str, chain_id: int = 137, paper_trading: bool = False):
        """Configure CLOB API connection settings."""
        self._host = host
        self._chain_id = chain_id
        self._paper_trading = paper_trading
    
    def set_credentials(self, credentials_manager: "CredentialsManager") -> None:
        """Set credentials manager."""
        self._credentials = credentials_manager
        self._audit.log_operator_action("CREDENTIALS_PROVIDED_TO_ENGINE", {
            "has_credentials": credentials_manager.is_unlocked
        })
    
    def enable(self) -> None:
        """Enable engine and start processing loop."""
        if self._enabled:
            return
            
        self._enabled = True
        self._init_client()
        # Start the background processor
        self._processing_task = asyncio.create_task(self._process_queue())
        self._audit.log_operator_action("EXECUTION_ENGINE_ENABLED")
            
    def _init_client(self):
        """Initialize CLOB client (Sync) - to be used in executor."""
        # Reset client if exists to allow fresh start
        self._clob_client = None

        if getattr(self, '_paper_trading', False):
             self._audit.log_system_event("EXECUTION_ENGINE_INIT", {"mode": "PAPER_TRADING"})
             return

        if not self._credentials or not self._credentials.is_unlocked:
            self._audit.log_error("CLOB_INIT_ERROR", "Credentials not unlocked")
            return

        try:
            creds = self._credentials.get_polymarket_credentials()
            if not creds:
                self._audit.log_error("CLOB_INIT_ERROR", "Failed to retrieve Polymarket credentials")
                return

            self._clob_client = ClobClient(
                host=self._host,
                key=creds['api_private_key'],
                chain_id=self._chain_id,
                creds=ApiCreds(
                    api_key=creds['api_key'],
                    api_secret=creds['api_secret'],
                    api_passphrase=creds['api_passphrase']
                )
            )
            self._audit.log_system_event("CLOB_CLIENT_INITIALIZED", {"host": self._host})
        except Exception as e:
            self._audit.log_error("CLOB_INIT_ERROR", f"Exception during init: {str(e)}")
            self._clob_client = None
    
    def disable(self) -> None:
        """Disable engine and stop processing."""
        self._enabled = False
        if self._processing_task:
            self._processing_task.cancel()
            self._processing_task = None
        self._clob_client = None
        self._audit.log_operator_action("EXECUTION_ENGINE_DISABLED")
    
    def submit_order(self, strategy: str, order_type: str, params: dict) -> str | None:
        """
        Submit an order.
        Adds to async queue for processing.
        """
        if not self._enabled:
            self._audit.log_policy_violation("SUBMIT_ORDER", "Execution engine is disabled")
            return None
        
        self._order_counter += 1
        order_id = f"ORD-{self._order_counter:06d}"
        
        order = Order(
            order_id=order_id,
            strategy=strategy,
            order_type=order_type,
            params=params,
            status=OrderStatus.PENDING
        )
        
        self._orders[order_id] = order
        # Put in queue (nowait because we are likely in sync context calling this, or async)
        # However, submit_order is called by sync strategies currently. 
        # We need a way to put into the loop from sync land if strategy is sync.
        # But we plan to make strategies async. For now, assuming calling from async context
        # or we use loop.call_soon_threadsafe if called from thread.
        # As we are redesigning everything to async, we assume callers can await or we use put_nowait.
        try:
            self._order_queue.put_nowait(order_id)
        except asyncio.QueueFull:
            self._audit.log_error("QUEUE_FULL", "Order queue is full")
            return None
        
        self._audit.log_strategy_event(strategy, "ORDER_SUBMITTED", {
            "order_id": order_id,
            "order_type": order_type
        })
        
        return order_id
    
    async def _process_queue(self):
        """Background loop to process orders."""
        while self._enabled:
            try:
                order_id = await self._order_queue.get()
                await self._execute_order(order_id)
                self._order_queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                self._audit.log_error("QUEUE_PROCESS_ERROR", str(e))
                await asyncio.sleep(1) # Backoff
    
    async def _execute_order(self, order_id: str) -> bool:
        """
        Execute order (Async wrapper).
        """
        order = self._orders.get(order_id)
        if not order:
            return False
            
        if order.status != OrderStatus.PENDING:
            return False
        
        order.status = OrderStatus.EXECUTING
        self._audit.log_strategy_event(order.strategy, "ORDER_EXECUTING", {"order_id": order_id})
        
        loop = asyncio.get_running_loop()
        execution_success = False
        result_data = {}
        
        if getattr(self, '_paper_trading', False):
            # v2.5: REALISTIC PAPER TRADING SIMULATION
            try:
                result_data = await self._simulate_paper_trade(order)
                execution_success = result_data.get('filled', False)

                if execution_success:
                    # Track position and calculate PnL
                    self._track_position(order, result_data)
                    self._audit.log_strategy_event(order.strategy, "PAPER_TRADE_EXECUTED", {
                        "order_id": order_id,
                        "params": order.params,
                        "simulated_price": result_data.get('executed_price'),
                        "fill_size": result_data.get('fill_size'),
                        "pnl": result_data.get('pnl', 0)
                    })
                else:
                    self._audit.log_strategy_event(order.strategy, "PAPER_TRADE_REJECTED", {
                        "order_id": order_id,
                        "reason": result_data.get('reject_reason', 'unknown')
                    })
            except Exception as e:
                execution_success = False
                result_data = {'error': str(e)}

        elif self._clob_client:
            try:
                # Rate Limit Check
                await self._rate_limiter.acquire()
                
                # Run blocking CLOB call in executor
                resp = await loop.run_in_executor(None, self._send_clob_order, order)
                result_data = {'clob_response': str(resp)}
                execution_success = True
            except Exception as e:
                execution_success = False
                result_data = {'error': str(e)}
                self._audit.log_error("EXECUTION_FAILED", f"Order {order_id}: {str(e)}")
        else:
             result_data = {'error': 'No active CLOB client'}
             execution_success = False
             
        order.status = OrderStatus.COMPLETED if execution_success else OrderStatus.FAILED
        order.result = result_data
        order.result["timestamp"] = time.time()
        
        self._audit.log_strategy_event(order.strategy, "ORDER_COMPLETED", {
            "order_id": order_id, 
            "result": order.result
        })
        
        self._notify_status(order)
        return True

    def _send_clob_order(self, order: Order):
        """Sync function to be run in executor."""
        if not self._clob_client:
            raise Exception("Client not initialized")
            
        token_id = order.params.get('token_id')
        price = float(order.params.get('price'))
        size = float(order.params.get('size'))
        side = "BUY" if order.params.get('side', 'BUY').upper() == "BUY" else "SELL"
        
        order_args = OrderArgs(
            price=price,
            size=size,
            side=side,
            token_id=token_id
        )
        return self._clob_client.create_and_post_order(order_args)
    
    def cancel_order(self, order_id: str) -> bool:
        """Cancel order (stub for now)."""
        # In async world, we'd add a cancellation task or flag.
        order = self._orders.get(order_id)
        if order and order.status in [OrderStatus.PENDING, OrderStatus.EXECUTING]:
            order.status = OrderStatus.CANCELLED
            self._audit.log_strategy_event(order.strategy, "ORDER_CANCELLED", {"order_id": order_id})
            return True
        return False

    def cancel_all_orders(self) -> int:
        """Cancel all."""
        cancelled = 0
        for order in self._orders.values():
            if order.status in [OrderStatus.PENDING, OrderStatus.EXECUTING]:
                order.status = OrderStatus.CANCELLED
                cancelled += 1
        return cancelled

    def get_order(self, order_id: str) -> Order | None:
        return self._orders.get(order_id)
        
    def subscribe_status(self, callback: Callable[[Order], None]) -> None:
        self._status_callbacks.append(callback)
    
    def _notify_status(self, order: Order) -> None:
        for callback in self._status_callbacks:
            try:
                callback(order)
            except Exception:
                pass
    
    @property
    def is_enabled(self) -> bool:
        return self._enabled
    
    @property
    def pending_count(self) -> int:
        return sum(1 for o in self._orders.values() if o.status == OrderStatus.PENDING)

    # ============= v2.5: Paper Trading Simulation =============

    async def _simulate_paper_trade(self, order: Order) -> dict:
        """
        Realistic paper trading simulation with slippage, partial fills, and latency.
        Returns a dict with execution details.
        """
        cfg = self._paper_config
        token_id = order.params.get('token_id', '')
        price = float(order.params.get('price', 0))
        size = float(order.params.get('size', 0))
        side = order.params.get('side', 'BUY').upper()

        # 1. Simulate network latency (50-200ms)
        latency = random.randint(cfg['latency_min_ms'], cfg['latency_max_ms']) / 1000.0
        await asyncio.sleep(latency)

        # 2. Check fill probability (simulates liquidity availability)
        if random.random() > cfg['fill_probability']:
            return {
                'filled': False,
                'reject_reason': 'INSUFFICIENT_LIQUIDITY',
                'simulated': True,
                'latency_ms': latency * 1000
            }

        # 3. v3.0: Calculate depth-based slippage
        # Base slippage + size impact + random market noise
        base_slippage = cfg['slippage_base']
        size_impact = (size / 100.0) * cfg['slippage_size_factor']  # Per $100 impact
        market_noise = random.uniform(-0.0002, 0.0002)  # ±0.02% random noise

        # Total slippage bounded by min/max
        slippage = max(cfg['slippage_min'], min(cfg['slippage_max'], base_slippage + size_impact + market_noise))

        if side == 'BUY':
            # Buying costs more (price goes up)
            executed_price = price * (1 + slippage)
        else:
            # Selling gets less (price goes down)
            executed_price = price * (1 - slippage)

        # 4. Partial fill simulation
        fill_size = size
        is_partial = False
        if random.random() < cfg['partial_fill_chance']:
            fill_size = size * random.uniform(0.5, 0.95)
            is_partial = True

        # 5. Calculate PnL if this is a closing trade
        pnl = 0.0
        if side == 'SELL' and token_id in self._positions and self._positions[token_id]:
            pnl = self._calculate_fifo_pnl(token_id, executed_price, fill_size)

        return {
            'filled': True,
            'executed_price': round(executed_price, 6),
            'requested_price': price,
            'slippage_pct': round(slippage * 100, 3),
            'fill_size': round(fill_size, 4),
            'requested_size': size,
            'is_partial_fill': is_partial,
            'pnl': round(pnl, 4),
            'latency_ms': round(latency * 1000, 1),
            'simulated': True,
            'clob_response': 'PAPER_TRADE_FILLED'
        }

    def _track_position(self, order: Order, result: dict) -> None:
        """Track position for PnL calculation using FIFO method."""
        token_id = order.params.get('token_id', '')
        side = order.params.get('side', 'BUY').upper()
        executed_price = result.get('executed_price', 0)
        fill_size = result.get('fill_size', 0)

        if token_id not in self._positions:
            self._positions[token_id] = []

        if side == 'BUY':
            # Add new position entry
            self._positions[token_id].append(Position(
                price=executed_price,
                size=fill_size,
                timestamp=time.time(),
                order_id=order.order_id
            ))
        elif side == 'SELL':
            # Remove from positions (FIFO) - already calculated PnL
            self._consume_positions(token_id, fill_size)

    def _calculate_fifo_pnl(self, token_id: str, sell_price: float, sell_size: float) -> float:
        """
        Calculate PnL using FIFO (First In First Out) method.
        Returns the realized PnL for this sell.
        """
        if token_id not in self._positions:
            return 0.0

        positions = self._positions[token_id]
        if not positions:
            return 0.0

        remaining_to_sell = sell_size
        total_pnl = 0.0
        total_cost = 0.0
        total_sold = 0.0

        for pos in positions:
            if remaining_to_sell <= 0:
                break

            # How much can we sell from this position?
            sellable = min(pos.size, remaining_to_sell)

            # Cost basis for this portion
            cost = sellable * pos.price
            revenue = sellable * sell_price
            pnl = revenue - cost

            total_cost += cost
            total_sold += sellable
            total_pnl += pnl
            remaining_to_sell -= sellable

        # Update cumulative PnL tracking
        if token_id not in self._realized_pnl:
            self._realized_pnl[token_id] = 0.0
        self._realized_pnl[token_id] += total_pnl
        self._total_realized_pnl += total_pnl

        self._audit.log_strategy_event("PNL_TRACKER", "PNL_REALIZED", {
            "token": token_id[:16] + "...",
            "sell_price": sell_price,
            "sell_size": sell_size,
            "cost_basis": round(total_cost, 4),
            "pnl": round(total_pnl, 4),
            "cumulative_pnl": round(self._total_realized_pnl, 4)
        })

        return total_pnl

    def _consume_positions(self, token_id: str, size: float) -> None:
        """Consume positions in FIFO order after a sell."""
        if token_id not in self._positions:
            return

        remaining = size
        new_positions = []

        for pos in self._positions[token_id]:
            if remaining <= 0:
                new_positions.append(pos)
            elif pos.size <= remaining:
                # Fully consume this position
                remaining -= pos.size
            else:
                # Partially consume this position
                pos.size -= remaining
                new_positions.append(pos)
                remaining = 0

        self._positions[token_id] = new_positions

    # ============= v2.5: PnL Accessors =============

    @property
    def total_realized_pnl(self) -> float:
        """Get total realized PnL across all tokens."""
        return self._total_realized_pnl

    @property
    def realized_pnl_by_token(self) -> dict[str, float]:
        """Get realized PnL breakdown by token."""
        return self._realized_pnl.copy()

    @property
    def open_positions(self) -> dict[str, List[Position]]:
        """Get all open positions."""
        return {k: v.copy() for k, v in self._positions.items() if v}

    def get_position_value(self, token_id: str, current_price: float) -> dict:
        """Calculate unrealized PnL for a specific token."""
        if token_id not in self._positions or not self._positions[token_id]:
            return {'size': 0, 'cost_basis': 0, 'current_value': 0, 'unrealized_pnl': 0}

        total_size = sum(p.size for p in self._positions[token_id])
        total_cost = sum(p.size * p.price for p in self._positions[token_id])
        current_value = total_size * current_price
        unrealized_pnl = current_value - total_cost

        return {
            'size': round(total_size, 4),
            'cost_basis': round(total_cost, 4),
            'current_value': round(current_value, 4),
            'unrealized_pnl': round(unrealized_pnl, 4),
            'avg_entry_price': round(total_cost / total_size, 6) if total_size > 0 else 0
        }

    def configure_paper_trading(self, config: dict) -> None:
        """Update paper trading simulation parameters."""
        for key in config:
            if key in self._paper_config:
                self._paper_config[key] = config[key]
        self._audit.log_system_event("PAPER_CONFIG_UPDATED", self._paper_config)

    # ============= v3.2: Enhanced Position Tracking & Callbacks =============

    def get_position_summary(self) -> dict:
        """Get summary of all open positions for UI/monitoring."""
        positions_data = []
        total_unrealized = 0.0
        total_size = 0.0

        for token_id, positions in self._positions.items():
            if not positions:
                continue

            token_size = sum(p.size for p in positions)
            token_cost = sum(p.size * p.price for p in positions)
            avg_price = token_cost / token_size if token_size > 0 else 0

            positions_data.append({
                'token_id': token_id[:16] + "...",
                'size': round(token_size, 4),
                'avg_entry_price': round(avg_price, 6),
                'cost_basis': round(token_cost, 4),
                'num_entries': len(positions)
            })
            total_size += token_size

        return {
            'total_positions': len([p for p in self._positions.values() if p]),
            'total_size_usd': round(total_size, 2),
            'total_realized_pnl': round(self._total_realized_pnl, 4),
            'positions': positions_data
        }

    def get_unrealized_pnl_all(self, current_prices: dict) -> dict:
        """
        Calculate unrealized PnL for all positions given current prices.
        current_prices: {token_id: current_price}
        """
        result = {
            'total_unrealized_pnl': 0.0,
            'by_token': {}
        }

        for token_id, positions in self._positions.items():
            if not positions or token_id not in current_prices:
                continue

            current_price = current_prices[token_id]
            token_size = sum(p.size for p in positions)
            token_cost = sum(p.size * p.price for p in positions)
            current_value = token_size * current_price
            unrealized_pnl = current_value - token_cost

            result['by_token'][token_id[:16] + "..."] = {
                'size': round(token_size, 4),
                'cost_basis': round(token_cost, 4),
                'current_value': round(current_value, 4),
                'unrealized_pnl': round(unrealized_pnl, 4),
                'unrealized_pnl_pct': round((unrealized_pnl / token_cost) * 100, 2) if token_cost > 0 else 0
            }
            result['total_unrealized_pnl'] += unrealized_pnl

        result['total_unrealized_pnl'] = round(result['total_unrealized_pnl'], 4)
        return result

    @property
    def execution_stats(self) -> dict:
        """Get execution engine statistics."""
        completed = sum(1 for o in self._orders.values() if o.status == OrderStatus.COMPLETED)
        failed = sum(1 for o in self._orders.values() if o.status == OrderStatus.FAILED)
        cancelled = sum(1 for o in self._orders.values() if o.status == OrderStatus.CANCELLED)

        return {
            'total_orders': len(self._orders),
            'pending': self.pending_count,
            'completed': completed,
            'failed': failed,
            'cancelled': cancelled,
            'success_rate': round((completed / len(self._orders)) * 100, 1) if self._orders else 0,
            'total_realized_pnl': round(self._total_realized_pnl, 4),
            'paper_trading': getattr(self, '_paper_trading', False)
        }
