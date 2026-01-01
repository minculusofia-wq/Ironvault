"""
ExecutionEngine Module (Async)
Executor that runs a background async task to process the order queue.
Wraps synchronous CLOB client calls in a thread executor to prevent blocking.
"""

from enum import Enum
from dataclasses import dataclass
from typing import Callable
import asyncio
import time

from .audit_logger import AuditLogger
from .rate_limiter import RateLimiter
from py_clob_client.client import ClobClient, ApiCreds
from py_clob_client.clob_types import OrderArgs

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
        
        # Rate Limiter (10 req/s burst 20)
        self._rate_limiter = RateLimiter(max_tokens=20, refill_rate=10)
        
        # API Config Defaults 
        self._host = "https://clob.polymarket.com"
        self._chain_id = 137  # Polygon Mainnet
        
        self._status_callbacks: list[Callable[[Order], None]] = []
        self._processing_task: asyncio.Task | None = None
    
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
        if getattr(self, '_paper_trading', False):
             self._audit.log_system_event("EXECUTION_ENGINE_INIT", {"mode": "PAPER_TRADING"})
             return

        if not self._credentials or not self._credentials.is_unlocked:
            return

        try:
            creds = self._credentials.get_polymarket_credentials()
            if not creds:
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
            self._audit.log_error("CLOB_INIT_ERROR", str(e))
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
             # PAPER TRADING SIMULATION
             # We assume immediate fill for now or we could use clob_adapter to check if fills are possible
             try:
                 # Simulate network delay
                 await asyncio.sleep(0.1) 
                 result_data = {'clob_response': 'PAPER_TRADE_FILLED', 'simulated': True}
                 execution_success = True
                 self._audit.log_strategy_event(order.strategy, "PAPER_TRADE_EXECUTED", {"order_id": order_id, "params": order.params})
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
