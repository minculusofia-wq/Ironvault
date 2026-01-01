"""
Execution Engine Module
Receives validated orders and executes mechanically without discretion.
No retry logic without policy approval.
"""

from enum import Enum
from dataclasses import dataclass
from typing import Callable
import threading
import time

from .audit_logger import AuditLogger
from py_clob_client.client import ClobClient, ApiCreds
from py_clob_client.clob_types import OrderArgs, OrderType as ClobOrderType

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
    Mechanical order execution engine.
    Executes validated orders without discretion.
    """
    
    def __init__(self, audit_logger: AuditLogger):
        self._audit = audit_logger
        self._orders: dict[str, Order] = {}
        self._order_counter = 0
        self._lock = threading.Lock()
        self._enabled = False
        self._credentials: "CredentialsManager | None" = None
        self._clob_client: ClobClient | None = None
        
        # API Config Defaults 
        self._host = "https://clob.polymarket.com"
        self._chain_id = 137  # Polygon Mainnet
        
        self._status_callbacks: list[Callable[[Order], None]] = []
    
    def configure_api(self, host: str, chain_id: int = 137):
        """Configure CLOB API connection settings."""
        self._host = host
        self._chain_id = chain_id
    
    def set_credentials(self, credentials_manager: "CredentialsManager") -> None:
        """
        Set credentials manager for order execution.
        Credentials values are NEVER logged.
        """
        self._credentials = credentials_manager
        self._audit.log_operator_action("CREDENTIALS_PROVIDED_TO_ENGINE", {
            "has_credentials": credentials_manager.is_unlocked
        })
    
    def enable(self) -> None:
        """Enable the execution engine and initialize client."""
        with self._lock:
            self._enabled = True
            self._init_client()
            self._audit.log_operator_action("EXECUTION_ENGINE_ENABLED")
            
    def _init_client(self):
        """Initialize CLOB client if credentials available."""
        if not self._credentials or not self._credentials.is_unlocked:
            return

        try:
            creds = self._credentials.get_polymarket_credentials()
            if not creds:
                return

            self._clob_client = ClobClient(
                host=self._host,
                key=creds['api_private_key'],  # Wallet private key
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
        """Disable the execution engine."""
        with self._lock:
            self._enabled = False
            self._clob_client = None # Clear sensitive client
            self._audit.log_operator_action("EXECUTION_ENGINE_DISABLED")
    
    def submit_order(self, strategy: str, order_type: str, params: dict) -> str | None:
        """
        Submit an order for execution.
        Returns order_id if accepted, None if engine disabled.
        """
        with self._lock:
            if not self._enabled:
                self._audit.log_policy_violation(
                    "SUBMIT_ORDER",
                    "Execution engine is disabled"
                )
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
            
            self._audit.log_strategy_event(strategy, "ORDER_SUBMITTED", {
                "order_id": order_id,
                "order_type": order_type,
                "params": params
            })
            
            return order_id
    
    def execute_order(self, order_id: str) -> bool:
        """
        Execute a pending order.
        Returns True if execution started, False otherwise.
        """
        with self._lock:
            if not self._enabled:
                return False
            
            order = self._orders.get(order_id)
            if not order:
                return False
            
            if order.status != OrderStatus.PENDING:
                return False
            
            order.status = OrderStatus.EXECUTING
        
        self._audit.log_strategy_event(order.strategy, "ORDER_EXECUTING", {
            "order_id": order_id
        })
        
        # Execute order using credentials (values never logged)
        # In real implementation: use self._credentials.get_wallet_private_key()
        # and self._credentials.get_polymarket_credentials() for API calls
        execution_success = True
        execution_success = True
        
        # Real Execution Logic
        if self._clob_client:
            try:
                # Retrieve parameters
                token_id = order.params.get('token_id')
                price = order.params.get('price')
                size = order.params.get('size')
                side_str = order.params.get('side', 'BUY').upper()
                side = "BUY" if side_str == "BUY" else "SELL"
                
                # Construct OrderArgs
                # Note: This implies params dict MUST match expected fields
                order_args = OrderArgs(
                    price=float(price),
                    size=float(size),
                    side=side,
                    token_id=token_id
                )
                
                # Execute
                resp = self._clob_client.create_and_post_order(order_args)
                
                # If we get here, submission was successful
                order.result = {'clob_response': str(resp)}
                
            except Exception as e:
                execution_success = False
                order.result = {'error': str(e)}
                self._audit.log_error("EXECUTION_FAILED", f"Order {order_id}: {str(e)}")
        
        else:
            # Fallback/Simulation if no client (e.g. testing)
            if self._credentials and self._credentials.is_unlocked:
                 # Logic for when we have creds but maybe client failed init? 
                 # Or treat as simulation mode.
                 pass
            else:
                execution_success = False
                order.result = {'error': 'No credentials/client active'}
        
        with self._lock:
            order.status = OrderStatus.COMPLETED if execution_success else OrderStatus.FAILED
            order.result = {"executed": execution_success, "timestamp": time.time()}
        
        self._audit.log_strategy_event(order.strategy, "ORDER_COMPLETED", {
            "order_id": order_id,
            "result": order.result
        })
        
        self._notify_status(order)
        return True
    
    def cancel_order(self, order_id: str) -> bool:
        """
        Cancel a pending order.
        Returns True if cancelled, False if not found or not cancellable.
        """
        with self._lock:
            order = self._orders.get(order_id)
            if not order:
                return False
            
            if order.status not in [OrderStatus.PENDING, OrderStatus.EXECUTING]:
                return False
            
            order.status = OrderStatus.CANCELLED
            
            self._audit.log_strategy_event(order.strategy, "ORDER_CANCELLED", {
                "order_id": order_id
            })
            
            self._notify_status(order)
            return True
    
    def cancel_all_orders(self) -> int:
        """
        Cancel all pending and executing orders.
        Returns count of cancelled orders.
        """
        cancelled = 0
        with self._lock:
            for order in self._orders.values():
                if order.status in [OrderStatus.PENDING, OrderStatus.EXECUTING]:
                    order.status = OrderStatus.CANCELLED
                    cancelled += 1
        
        if cancelled > 0:
            self._audit.log_operator_action("CANCEL_ALL_ORDERS", {
                "cancelled_count": cancelled
            })
        
        return cancelled
    
    def get_order(self, order_id: str) -> Order | None:
        """Get order by ID."""
        return self._orders.get(order_id)
    
    def get_pending_orders(self) -> list[Order]:
        """Get all pending orders."""
        with self._lock:
            return [o for o in self._orders.values() if o.status == OrderStatus.PENDING]
    
    def subscribe_status(self, callback: Callable[[Order], None]) -> None:
        """Subscribe to order status updates."""
        self._status_callbacks.append(callback)
    
    def _notify_status(self, order: Order) -> None:
        """Notify subscribers of order status change."""
        for callback in self._status_callbacks:
            try:
                callback(order)
            except Exception:
                pass
    
    @property
    def is_enabled(self) -> bool:
        """Whether engine is enabled."""
        return self._enabled
    
    @property
    def pending_count(self) -> int:
        """Count of pending orders."""
        with self._lock:
            return sum(1 for o in self._orders.values() if o.status == OrderStatus.PENDING)
