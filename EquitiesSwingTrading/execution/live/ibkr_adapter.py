"""
Interactive Brokers (IBKR) broker adapter for futures trading.

Implements BrokerAdapter interface using the TWS API (ibapi).
Supports both paper and live trading via TWS or IB Gateway.

IMPORTANT: Requires TWS or IB Gateway running locally with API enabled.
"""
import asyncio
import logging
import threading
import time
from datetime import datetime, timezone
from decimal import Decimal
from queue import Queue, Empty
from typing import Optional, List, Dict, Any, Callable
from dataclasses import dataclass

# ibapi imports - install via: pip install ibapi
# Note: May need to install from TWS API download for latest version
try:
    from ibapi.client import EClient
    from ibapi.wrapper import EWrapper
    from ibapi.contract import Contract
    from ibapi.order import Order as IBOrder
    from ibapi.execution import Execution
    from ibapi.common import BarData, TickerId, OrderId
    IBAPI_AVAILABLE = True
except ImportError:
    IBAPI_AVAILABLE = False
    # Define stubs for type hints when ibapi not installed
    EClient = object
    EWrapper = object
    Contract = object
    IBOrder = object

from .broker import (
    BrokerAdapter,
    Order,
    OrderSide,
    OrderType,
    OrderStatus,
    TimeInForce,
    BrokerPosition,
    AccountInfo,
    BracketOrderRequest,
    BrokerError,
    BrokerConnectionError,
    OrderRejectedError,
    InsufficientFundsError,
    PositionNotFoundError,
)

logger = logging.getLogger(__name__)


@dataclass
class IBKRConfig:
    """Configuration for IBKR connection."""
    host: str = "127.0.0.1"
    port: int = 7497  # 7497=TWS paper, 7496=TWS live, 4002=Gateway paper, 4001=Gateway live
    client_id: int = 1
    timeout: float = 30.0  # Connection timeout in seconds
    readonly: bool = False


class IBKRApp(EWrapper, EClient):
    """
    Combined TWS API application.

    Inherits from both EWrapper (receives callbacks) and EClient (sends requests).
    This is the standard pattern for ibapi usage.
    """

    def __init__(self):
        EWrapper.__init__(self)
        EClient.__init__(self, wrapper=self)
        self._next_order_id: Optional[int] = None
        self._account_info: Dict[str, Any] = {}
        self._positions: Dict[str, Dict[str, Any]] = {}
        self._orders: Dict[int, Dict[str, Any]] = {}
        self._executions: Dict[str, Execution] = {}

        # Response queues for synchronous-style access
        self._account_queue: Queue = Queue()
        self._position_queue: Queue = Queue()
        self._order_queue: Queue = Queue()
        self._error_queue: Queue = Queue()

        # Connection state
        self._connected = False
        self._connection_error: Optional[str] = None

    def reset(self):
        """Reset state for reconnection."""
        # IMPORTANT: Must call EClient.reset() to initialize connState
        EClient.reset(self)
        self._account_info = {}
        self._positions = {}
        self._connection_error = None

    # === Connection Callbacks ===

    def connectAck(self):
        """Called when connection is acknowledged."""
        logger.info("IBKR connection acknowledged")

    def connectionClosed(self):
        """Called when connection is closed."""
        self._connected = False
        logger.warning("IBKR connection closed")

    def nextValidId(self, orderId: int):
        """
        Called on connection with the next valid order ID.

        This is also an indicator that connection is established.
        """
        self._next_order_id = orderId
        self._connected = True
        logger.info(f"IBKR connected. Next valid order ID: {orderId}")

    # === Error Handling ===

    def error(self, reqId: int, errorCode: int, errorString: str, advancedOrderRejectJson: str = ""):
        """Handle error messages from TWS."""
        # Codes 2100-2110 are typically informational
        if 2100 <= errorCode <= 2110:
            logger.debug(f"IBKR info [{errorCode}]: {errorString}")
            return

        # Code 502 = couldn't connect
        if errorCode == 502:
            self._connection_error = errorString
            self._connected = False
            logger.error(f"IBKR connection failed: {errorString}")
            return

        # Code 504 = not connected
        if errorCode == 504:
            self._connected = False
            logger.error("IBKR: Not connected")
            return

        # Code 201 = order rejected
        if errorCode == 201:
            logger.error(f"IBKR order rejected [{reqId}]: {errorString}")
            self._error_queue.put({
                "reqId": reqId,
                "code": errorCode,
                "message": errorString,
            })
            return

        # Code 202 = order cancelled
        if errorCode == 202:
            logger.info(f"IBKR order cancelled [{reqId}]: {errorString}")
            return

        # Log other errors
        if errorCode >= 1000:
            logger.error(f"IBKR error [{errorCode}] reqId={reqId}: {errorString}")
        else:
            logger.warning(f"IBKR warning [{errorCode}] reqId={reqId}: {errorString}")

        self._error_queue.put({
            "reqId": reqId,
            "code": errorCode,
            "message": errorString,
        })

    # === Account Callbacks ===

    def managedAccounts(self, accountsList: str):
        """Called with list of managed account IDs."""
        accounts = accountsList.split(",")
        self._account_info["accounts"] = accounts
        logger.info(f"IBKR managed accounts: {accounts}")

    def updateAccountValue(self, key: str, val: str, currency: str, accountName: str):
        """Called with account value updates."""
        if currency == "USD" or currency == "BASE":
            self._account_info[key] = val

    def updateAccountTime(self, timeStamp: str):
        """Called with account update timestamp."""
        self._account_info["last_update"] = timeStamp

    def accountDownloadEnd(self, accountName: str):
        """Called when account download is complete."""
        self._account_queue.put(dict(self._account_info))
        logger.debug(f"IBKR account download complete for {accountName}")

    # === Position Callbacks ===

    def position(self, account: str, contract: Contract, position: Decimal, avgCost: float):
        """Called with position updates."""
        key = f"{contract.symbol}_{contract.secType}_{contract.lastTradeDateOrContractMonth}"
        self._positions[key] = {
            "account": account,
            "contract": contract,
            "position": float(position),
            "avgCost": avgCost,
        }

    def positionEnd(self):
        """Called when position download is complete."""
        self._position_queue.put(dict(self._positions))
        logger.debug(f"IBKR position download complete: {len(self._positions)} positions")

    # === Order Callbacks ===

    def openOrder(self, orderId: int, contract: Contract, order: IBOrder, orderState):
        """Called with open order info."""
        self._orders[orderId] = {
            "orderId": orderId,
            "contract": contract,
            "order": order,
            "status": orderState.status,
            "filledQty": order.filledQuantity if hasattr(order, 'filledQuantity') else 0,
        }

    def orderStatus(
        self,
        orderId: int,
        status: str,
        filled: Decimal,
        remaining: Decimal,
        avgFillPrice: float,
        permId: int,
        parentId: int,
        lastFillPrice: float,
        clientId: int,
        whyHeld: str,
        mktCapPrice: float = 0.0,
    ):
        """Called with order status updates."""
        if orderId in self._orders:
            self._orders[orderId].update({
                "status": status,
                "filled": float(filled),
                "remaining": float(remaining),
                "avgFillPrice": avgFillPrice,
            })
        else:
            self._orders[orderId] = {
                "orderId": orderId,
                "status": status,
                "filled": float(filled),
                "remaining": float(remaining),
                "avgFillPrice": avgFillPrice,
            }

        self._order_queue.put({
            "orderId": orderId,
            "status": status,
            "filled": float(filled),
            "avgFillPrice": avgFillPrice,
        })

    def openOrderEnd(self):
        """Called when open order download is complete."""
        logger.debug(f"IBKR open orders download complete: {len(self._orders)} orders")

    def execDetails(self, reqId: int, contract: Contract, execution: Execution):
        """Called with execution details."""
        self._executions[execution.execId] = execution
        logger.info(
            f"IBKR execution: {execution.side} {execution.shares} {contract.symbol} "
            f"@ {execution.price} (order {execution.orderId})"
        )


class IBKRAdapter(BrokerAdapter):
    """
    Interactive Brokers adapter for futures trading.

    Uses the TWS API (ibapi) for order execution and account management.
    Requires TWS or IB Gateway running locally.

    Features:
    - Supports futures contracts (ES, NQ, CL, etc.)
    - Paper and live trading
    - All order types: market, limit, stop, stop-limit
    - Bracket orders for automatic stop-loss

    Example:
        config = IBKRConfig(port=7497, client_id=1)  # Paper trading
        adapter = IBKRAdapter(config)
        await adapter.connect()

        account = await adapter.get_account()
        print(f"Equity: ${account.equity}")

    Note:
        The ibapi library is blocking/callback-based. This adapter
        runs it in a background thread and provides an async interface.
    """

    # Status mapping from IBKR to our OrderStatus
    _STATUS_MAP: Dict[str, OrderStatus] = {
        "PendingSubmit": OrderStatus.PENDING,
        "PendingCancel": OrderStatus.PENDING,
        "PreSubmitted": OrderStatus.PENDING,
        "Submitted": OrderStatus.ACCEPTED,
        "ApiPending": OrderStatus.PENDING,
        "ApiCancelled": OrderStatus.CANCELLED,
        "Cancelled": OrderStatus.CANCELLED,
        "Filled": OrderStatus.FILLED,
        "Inactive": OrderStatus.REJECTED,
    }

    def __init__(self, config: Optional[IBKRConfig] = None):
        """
        Initialize IBKR adapter.

        Args:
            config: IBKR connection configuration
        """
        if not IBAPI_AVAILABLE:
            raise ImportError(
                "ibapi package not installed. Install via: pip install ibapi\n"
                "Or download from: https://interactivebrokers.github.io/"
            )

        self.config = config or IBKRConfig()
        self._app: Optional[IBKRApp] = None
        self._thread: Optional[threading.Thread] = None
        self._connected = False
        self._lock = threading.Lock()

    async def connect(self) -> bool:
        """
        Establish connection to TWS/Gateway.

        Starts background thread for API message processing.

        Returns:
            True if connection successful.

        Raises:
            BrokerConnectionError: If connection fails.
        """
        try:
            self._app = IBKRApp()

            # Connect in current thread
            self._app.connect(
                self.config.host,
                self.config.port,
                self.config.client_id,
            )

            # Start message processing thread
            self._thread = threading.Thread(
                target=self._run_loop,
                daemon=True,
                name="ibkr-api-thread",
            )
            self._thread.start()

            # Wait for connection confirmation (nextValidId callback)
            start_time = time.time()
            while not self._app._connected:
                if self._app._connection_error:
                    raise BrokerConnectionError(self._app._connection_error)

                if time.time() - start_time > self.config.timeout:
                    raise BrokerConnectionError(
                        f"Connection timeout after {self.config.timeout}s. "
                        "Is TWS/Gateway running with API enabled?"
                    )

                await asyncio.sleep(0.1)

            self._connected = True
            logger.info(
                f"Connected to IBKR at {self.config.host}:{self.config.port} "
                f"(client_id={self.config.client_id})"
            )
            return True

        except Exception as e:
            self._connected = False
            if not isinstance(e, BrokerConnectionError):
                raise BrokerConnectionError(f"Connection failed: {e}") from e
            raise

    def _run_loop(self):
        """Background thread for processing TWS messages."""
        try:
            self._app.run()
        except Exception as e:
            logger.error(f"IBKR message loop error: {e}")
            self._connected = False

    async def disconnect(self) -> None:
        """Close connection to TWS/Gateway."""
        if self._app:
            self._app.disconnect()
            self._app = None

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5.0)
            self._thread = None

        self._connected = False
        logger.info("Disconnected from IBKR")

    async def is_connected(self) -> bool:
        """Check if broker connection is active."""
        return self._connected and self._app is not None and self._app._connected

    # === Account Methods ===

    async def get_account(self) -> AccountInfo:
        """
        Get current account information.

        Returns:
            AccountInfo with equity, cash, buying power, etc.
        """
        self._ensure_connected()

        # Clear queue and request account updates
        while not self._app._account_queue.empty():
            try:
                self._app._account_queue.get_nowait()
            except Empty:
                break

        # Request account data
        accounts = self._app._account_info.get("accounts", [])
        if accounts:
            self._app.reqAccountUpdates(True, accounts[0])
        else:
            self._app.reqAccountUpdates(True, "")

        # Wait for response
        try:
            account_data = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(
                    None, self._app._account_queue.get, True, 10.0
                ),
                timeout=15.0,
            )
        except (asyncio.TimeoutError, Empty):
            raise BrokerError("Timeout waiting for account data")
        finally:
            # Stop account updates
            if accounts:
                self._app.reqAccountUpdates(False, accounts[0])
            else:
                self._app.reqAccountUpdates(False, "")

        # Parse account values
        return AccountInfo(
            equity=Decimal(str(account_data.get("NetLiquidation", "0"))),
            cash=Decimal(str(account_data.get("TotalCashValue", "0"))),
            buying_power=Decimal(str(account_data.get("BuyingPower", "0"))),
            portfolio_value=Decimal(str(account_data.get("GrossPositionValue", "0"))),
            day_trade_count=0,  # IBKR doesn't provide this the same way
            pattern_day_trader=False,
            account_blocked=False,
            trading_blocked=self.config.readonly,
            last_updated=datetime.now(timezone.utc),
        )

    # === Position Methods ===

    async def get_positions(self) -> List[BrokerPosition]:
        """
        Get all open positions.

        Returns:
            List of BrokerPosition objects.
        """
        self._ensure_connected()

        # Clear queue and request positions
        while not self._app._position_queue.empty():
            try:
                self._app._position_queue.get_nowait()
            except Empty:
                break

        self._app.reqPositions()

        # Wait for response
        try:
            positions_data = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(
                    None, self._app._position_queue.get, True, 10.0
                ),
                timeout=15.0,
            )
        except (asyncio.TimeoutError, Empty):
            raise BrokerError("Timeout waiting for positions")

        # Convert to BrokerPosition
        positions = []
        for key, pos_data in positions_data.items():
            if pos_data["position"] != 0:
                contract = pos_data["contract"]
                qty = Decimal(str(pos_data["position"]))
                avg_cost = Decimal(str(pos_data["avgCost"]))

                positions.append(BrokerPosition(
                    symbol=f"{contract.symbol}{contract.lastTradeDateOrContractMonth}",
                    quantity=qty,
                    avg_entry_price=avg_cost,
                    current_price=avg_cost,  # Would need market data for current price
                    market_value=qty * avg_cost,
                    cost_basis=abs(qty) * avg_cost,
                    unrealized_pnl=Decimal("0"),  # Would need market data
                    unrealized_pnl_pct=0.0,
                    side="long" if qty > 0 else "short",
                ))

        return positions

    async def get_position(self, symbol: str) -> Optional[BrokerPosition]:
        """
        Get position for specific symbol.

        Args:
            symbol: Contract symbol (e.g., "ESZ4" or "ES")

        Returns:
            BrokerPosition if position exists, None otherwise.
        """
        positions = await self.get_positions()
        symbol_upper = symbol.upper()

        for pos in positions:
            if symbol_upper in pos.symbol.upper():
                return pos

        return None

    # === Order Methods ===

    async def submit_order(self, order: Order) -> Order:
        """
        Submit order to IBKR.

        Args:
            order: Order to submit

        Returns:
            Order with IBKR-assigned ID and status.

        Raises:
            OrderRejectedError: If broker rejects order.
        """
        self._ensure_connected()

        # Build IBKR contract
        contract = self._build_contract(order.symbol)

        # Build IBKR order
        ib_order = self._build_ib_order(order)

        # Get next order ID
        order_id = self._get_next_order_id()

        # Submit order
        self._app.placeOrder(order_id, contract, ib_order)

        # Wait for acknowledgment
        await asyncio.sleep(0.5)

        # Update our order with the assigned ID
        order.broker_order_id = str(order_id)
        order.order_id = str(order_id)

        # Check for rejection
        try:
            while not self._app._error_queue.empty():
                error = self._app._error_queue.get_nowait()
                if error["reqId"] == order_id and error["code"] == 201:
                    order.status = OrderStatus.REJECTED
                    raise OrderRejectedError(error["message"], order=order)
        except Empty:
            pass

        # Update status from callback
        if order_id in self._app._orders:
            status_str = self._app._orders[order_id].get("status", "Submitted")
            order.status = self._STATUS_MAP.get(status_str, OrderStatus.PENDING)

        logger.info(f"Order submitted: {order_id} {order.side.value} {order.quantity} {order.symbol}")
        return order

    async def submit_bracket_order(self, request: BracketOrderRequest) -> Order:
        """
        Submit bracket order (entry + stop-loss + optional take-profit).

        IBKR supports bracket orders via parent/child order relationships.

        Args:
            request: BracketOrderRequest with all legs

        Returns:
            Parent order with legs attached.
        """
        self._ensure_connected()

        contract = self._build_contract(request.symbol)

        # Parent order (entry)
        parent_id = self._get_next_order_id()
        parent = IBOrder()
        parent.orderId = parent_id
        parent.action = "BUY" if request.side == OrderSide.BUY else "SELL"
        parent.totalQuantity = float(request.quantity)
        parent.orderType = "MKT" if request.entry_type == OrderType.MARKET else "LMT"
        if request.entry_limit_price:
            parent.lmtPrice = float(request.entry_limit_price)
        parent.transmit = False  # Don't transmit until children are added

        # Stop-loss order (child)
        stop_id = self._get_next_order_id()
        stop_order = IBOrder()
        stop_order.orderId = stop_id
        stop_order.parentId = parent_id
        stop_order.action = "SELL" if request.side == OrderSide.BUY else "BUY"
        stop_order.totalQuantity = float(request.quantity)
        stop_order.orderType = "STP"
        stop_order.auxPrice = float(request.stop_loss_price)
        stop_order.transmit = not request.take_profit_price  # Transmit if no take-profit

        # Take-profit order (optional child)
        if request.take_profit_price:
            profit_id = self._get_next_order_id()
            profit_order = IBOrder()
            profit_order.orderId = profit_id
            profit_order.parentId = parent_id
            profit_order.action = "SELL" if request.side == OrderSide.BUY else "BUY"
            profit_order.totalQuantity = float(request.quantity)
            profit_order.orderType = "LMT"
            profit_order.lmtPrice = float(request.take_profit_price)
            profit_order.transmit = True  # Transmit the whole bracket

        # Submit orders
        self._app.placeOrder(parent_id, contract, parent)
        self._app.placeOrder(stop_id, contract, stop_order)
        if request.take_profit_price:
            self._app.placeOrder(profit_id, contract, profit_order)

        await asyncio.sleep(0.5)

        # Return parent order
        return Order(
            order_id=str(parent_id),
            symbol=request.symbol,
            side=request.side,
            order_type=request.entry_type,
            quantity=request.quantity,
            limit_price=request.entry_limit_price,
            status=OrderStatus.PENDING,
            broker_order_id=str(parent_id),
        )

    async def cancel_order(self, order_id: str) -> bool:
        """
        Cancel pending order.

        Args:
            order_id: IBKR order ID to cancel

        Returns:
            True if cancellation request accepted.
        """
        self._ensure_connected()

        try:
            self._app.cancelOrder(int(order_id))
            logger.info(f"Cancel request submitted for order {order_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to cancel order {order_id}: {e}")
            return False

    async def get_order(self, order_id: str) -> Optional[Order]:
        """
        Get order status by ID.

        Args:
            order_id: IBKR order ID

        Returns:
            Order with current status, None if not found.
        """
        self._ensure_connected()

        oid = int(order_id)
        if oid not in self._app._orders:
            return None

        order_data = self._app._orders[oid]
        status_str = order_data.get("status", "Unknown")

        # Reconstruct order from stored data
        if "order" in order_data:
            ib_order = order_data["order"]
            contract = order_data.get("contract")

            return Order(
                order_id=order_id,
                symbol=contract.symbol if contract else "",
                side=OrderSide.BUY if ib_order.action == "BUY" else OrderSide.SELL,
                order_type=self._parse_order_type(ib_order.orderType),
                quantity=Decimal(str(ib_order.totalQuantity)),
                status=self._STATUS_MAP.get(status_str, OrderStatus.PENDING),
                filled_quantity=Decimal(str(order_data.get("filled", 0))),
                filled_avg_price=Decimal(str(order_data.get("avgFillPrice", 0))) if order_data.get("avgFillPrice") else None,
                broker_order_id=order_id,
            )

        return None

    async def get_open_orders(self, symbol: Optional[str] = None) -> List[Order]:
        """
        Get all open orders.

        Args:
            symbol: Optional filter by symbol

        Returns:
            List of open Order objects.
        """
        self._ensure_connected()

        # Request all open orders
        self._app.reqAllOpenOrders()
        await asyncio.sleep(1.0)

        orders = []
        for oid, order_data in self._app._orders.items():
            status = order_data.get("status", "")
            if status in ["Submitted", "PreSubmitted", "PendingSubmit"]:
                order = await self.get_order(str(oid))
                if order:
                    if symbol is None or symbol.upper() in order.symbol.upper():
                        orders.append(order)

        return orders

    # === Position Management ===

    async def close_position(
        self,
        symbol: str,
        quantity: Optional[Decimal] = None
    ) -> Order:
        """
        Close position (market order).

        Args:
            symbol: Symbol to close
            quantity: Optional partial close quantity (None = full close)

        Returns:
            Exit order.
        """
        position = await self.get_position(symbol)
        if not position:
            raise PositionNotFoundError(f"No position for {symbol}")

        close_qty = quantity if quantity else abs(position.quantity)
        close_side = OrderSide.SELL if position.is_long else OrderSide.BUY

        order = Order(
            order_id="",
            symbol=symbol,
            side=close_side,
            order_type=OrderType.MARKET,
            quantity=close_qty,
        )

        return await self.submit_order(order)

    async def close_all_positions(self) -> List[Order]:
        """
        Close all positions (emergency).

        Returns:
            List of exit orders submitted.
        """
        self._ensure_connected()

        positions = await self.get_positions()
        orders = []

        for pos in positions:
            try:
                order = await self.close_position(pos.symbol)
                orders.append(order)
            except Exception as e:
                logger.error(f"Failed to close position {pos.symbol}: {e}")

        logger.warning(f"Emergency close all: {len(orders)} positions closed")
        return orders

    # === Private Helper Methods ===

    def _ensure_connected(self) -> None:
        """Raise error if not connected."""
        if not self._connected or not self._app:
            raise BrokerConnectionError("Not connected to IBKR")

    def _get_next_order_id(self) -> int:
        """Get next valid order ID."""
        with self._lock:
            if self._app._next_order_id is None:
                raise BrokerError("Order ID not initialized - not connected?")
            order_id = self._app._next_order_id
            self._app._next_order_id += 1
            return order_id

    def _build_contract(self, symbol: str) -> Contract:
        """
        Build IBKR Contract from symbol string.

        Supports formats:
        - "MES" -> front month micro e-mini
        - "ESZ4" -> specific month
        - "ES202412" -> YYYYMM format
        """
        contract = Contract()

        # Parse symbol
        # Simple case: root symbol only (e.g., "MES", "ES", "CL")
        root = symbol.upper()
        expiry = ""

        # Check for month code (e.g., "ESZ4" or "ESZ24")
        if len(symbol) > 2:
            for i, char in enumerate(symbol):
                if char.isdigit():
                    root = symbol[:i].upper()
                    expiry = symbol[i:]
                    break

        contract.symbol = root
        contract.secType = "FUT"
        contract.currency = "USD"

        # Set exchange based on symbol
        exchange_map = {
            "ES": "CME", "MES": "CME",
            "NQ": "CME", "MNQ": "CME",
            "RTY": "CME", "M2K": "CME",
            "YM": "CBOT", "MYM": "CBOT",
            "CL": "NYMEX", "MCL": "NYMEX",
            "NG": "NYMEX", "MNG": "NYMEX",
            "GC": "COMEX", "MGC": "COMEX",
        }
        contract.exchange = exchange_map.get(root, "CME")

        # Handle expiry
        if expiry:
            # Could be "Z4", "Z24", or "202412"
            if len(expiry) >= 6 and expiry.isdigit():
                contract.lastTradeDateOrContractMonth = expiry
            else:
                # Convert month code to YYYYMM
                # [*TO-DO*] - Proper month code parsing
                contract.lastTradeDateOrContractMonth = expiry

        return contract

    def _build_ib_order(self, order: Order) -> IBOrder:
        """Build IBKR Order from our Order dataclass."""
        ib_order = IBOrder()

        # Action
        ib_order.action = "BUY" if order.side == OrderSide.BUY else "SELL"

        # Quantity
        ib_order.totalQuantity = float(order.quantity)

        # Order type
        type_map = {
            OrderType.MARKET: "MKT",
            OrderType.LIMIT: "LMT",
            OrderType.STOP: "STP",
            OrderType.STOP_LIMIT: "STP LMT",
        }
        ib_order.orderType = type_map.get(order.order_type, "MKT")

        # Prices
        if order.limit_price:
            ib_order.lmtPrice = float(order.limit_price)
        if order.stop_price:
            ib_order.auxPrice = float(order.stop_price)

        # Time in force
        tif_map = {
            TimeInForce.DAY: "DAY",
            TimeInForce.GTC: "GTC",
            TimeInForce.IOC: "IOC",
            TimeInForce.FOK: "FOK",
        }
        ib_order.tif = tif_map.get(order.time_in_force, "DAY")

        return ib_order

    def _parse_order_type(self, ib_type: str) -> OrderType:
        """Parse IBKR order type string to our OrderType."""
        type_map = {
            "MKT": OrderType.MARKET,
            "LMT": OrderType.LIMIT,
            "STP": OrderType.STOP,
            "STP LMT": OrderType.STOP_LIMIT,
        }
        return type_map.get(ib_type, OrderType.MARKET)
