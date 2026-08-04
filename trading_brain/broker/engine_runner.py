"""
Engine Runner Module — AI Trading Brain, Phase 3

Wires a Strategy -- the exact same setup-detection logic the backtester was
validated against (strategy.SmartMoneyConceptsStrategy, by default) -- to
a live Broker, one bar at a time, gated by BotSettings.

Scope decision, stated plainly: this operates on DAILY bars, matching every
validated backtest so far (see backtest_report.html / the four real-CSV
runs). liquidity_tolerance, displacement thresholds, and every other
BacktestConfig default were tuned against daily OHLC -- pointing this at
intraday bars would silently run an unvalidated strategy at an unvalidated
timeframe. If intraday trading is wanted later, that needs its own
calibration pass first, not a config change here.

State machine per instrument:
  FLAT    -- looking for a new candidate on each bar.
  PENDING -- a resting limit order is out at the broker; waiting for it to
             fill, get cancelled on invalidation-before-fill, or time out
             (max_pending_candles).
  OPEN    -- position is live. The broker's own bracket (stop_loss/
             take_profit attached at entry -- see paper.py's bracket
             handling, or IBKR's native bracket order) manages the hard
             stop and target. This engine's only remaining job for an OPEN
             position is the close-based invalidation exit (README rule:
             "exit on invalidation before the hard stop"), since no broker
             API expresses "close beyond this price" as a resting order.
"""

from dataclasses import dataclass
from typing import Callable, List, Optional, Set

from ..config import BacktestConfig
from ..displacement import Direction
from ..market_structure import Candle
from ..risk import position_size
from ..strategy import SmartMoneyConceptsStrategy, Strategy
from .base import Bar, Broker, OrderRequest, OrderSide
from .settings import BotSettings

SettingsProvider = Callable[[], BotSettings]
AccountBalanceProvider = Callable[[], float]


@dataclass
class _ActiveTrade:
    direction: Direction
    entry: float
    stop_loss: float
    take_profit: float
    invalidation_price: float
    tier_name: str


class LiveEngine:
    """One instance per instrument. Feed it bars via on_bar(); it decides
    when to place, cancel, or invalidation-exit an order, respecting
    whatever BotSettings says *at the moment each bar arrives* -- settings
    changes take effect on the next bar, not retroactively on state already
    in flight."""

    def __init__(
        self,
        symbol: str,
        broker: Broker,
        settings_provider: SettingsProvider,
        account_balance_provider: AccountBalanceProvider,
        config: Optional[BacktestConfig] = None,
        unit_value_per_point: float = 1.0,
        strategy: Optional[Strategy] = None,
    ):
        self.symbol = symbol
        self.broker = broker
        self.settings_provider = settings_provider
        self.account_balance_provider = account_balance_provider
        self.config = config or BacktestConfig()
        self.unit_value_per_point = unit_value_per_point
        self.strategy = strategy or SmartMoneyConceptsStrategy()

        self.candles: List[Candle] = []
        self.seen_origins: Set[int] = set()
        self.state = "flat"  # "flat" | "pending" | "open"
        self.active: Optional[_ActiveTrade] = None
        self._pending_broker_order_id: Optional[str] = None
        self._pending_placed_at_index: Optional[int] = None
        self._pending_invalidation: Optional[float] = None
        self._pending_direction: Optional[Direction] = None

    def on_bar(self, bar: Bar) -> None:
        # timestamp deliberately dropped, not carried from bar.timestamp:
        # the strategy's session-time gate (is_allowed_to_trade) checks
        # intraday session windows, which a daily bar's timestamp
        # (typically midnight) never falls inside. Every backtest this
        # system has been validated against ran the same way -- stripping
        # the timestamp to None, which is_allowed_to_trade's documented
        # fallback treats as "session gating doesn't apply." Carrying a
        # real timestamp here would silently start enforcing an intraday
        # rule this strategy has never been calibrated or tested against.
        candle = Candle(
            index=len(self.candles),
            open=bar.open, high=bar.high, low=bar.low, close=bar.close,
            timestamp=None,
        )
        self.candles.append(candle)
        i = candle.index
        settings = self.settings_provider()

        if self.state == "open":
            self._sync_open_state()
            if self.state == "open":
                self._check_invalidation(candle)
        elif self.state == "pending":
            self._sync_pending_state()
            if self.state == "pending":
                self._check_pending_timeout_or_invalidation(candle, i)
        else:
            self._look_for_candidate(i, settings)

    def _sync_open_state(self) -> None:
        """The broker may have already closed this position on its own
        (bracket stop/target touched). Detect that and fall back to flat
        rather than continuing to think we're holding something we're not."""
        positions = self.broker.get_positions()
        if self.symbol not in positions:
            self.state = "flat"
            self.active = None

    def _sync_pending_state(self) -> None:
        """Mirror image of _sync_open_state: the resting order may have
        already filled (transitions to open) via the broker's own fill path
        before this bar's on_bar call -- reconcile rather than double-acting."""
        positions = self.broker.get_positions()
        if self.symbol in positions and self.active is not None:
            self.state = "open"
            self._pending_broker_order_id = None

    def _check_invalidation(self, candle: Candle) -> None:
        trade = self.active
        if trade is None:
            return
        bullish = trade.direction == Direction.BULLISH
        invalidated = (
            candle.close <= trade.invalidation_price if bullish
            else candle.close >= trade.invalidation_price
        )
        if not invalidated:
            return
        positions = self.broker.get_positions()
        pos = positions.get(self.symbol)
        if pos is None or pos.quantity == 0:
            self.state = "flat"
            self.active = None
            return
        side = OrderSide.SELL if pos.quantity > 0 else OrderSide.BUY
        self.broker.place_order(OrderRequest(symbol=self.symbol, side=side, quantity=abs(pos.quantity)))
        self.state = "flat"
        self.active = None

    def _check_pending_timeout_or_invalidation(self, candle: Candle, i: int) -> None:
        if self._pending_direction is not None and self._pending_invalidation is not None:
            bullish = self._pending_direction == Direction.BULLISH
            invalidated = (
                candle.close <= self._pending_invalidation if bullish
                else candle.close >= self._pending_invalidation
            )
            if invalidated:
                self._cancel_pending()
                return
        if self._pending_placed_at_index is not None and i - self._pending_placed_at_index > self.config.max_pending_candles:
            self._cancel_pending()

    def _cancel_pending(self) -> None:
        if self._pending_broker_order_id is not None:
            self.broker.cancel_order(self._pending_broker_order_id)
        self.state = "flat"
        self.active = None
        self._pending_broker_order_id = None
        self._pending_placed_at_index = None
        self._pending_invalidation = None
        self._pending_direction = None

    def _look_for_candidate(self, i: int, settings: BotSettings) -> None:
        if not settings.trading_allowed():
            return
        if not settings.is_instrument_enabled(self.symbol):
            return

        candidate = self.strategy.find_candidate(self.candles, i, self.config, self.seen_origins)
        if candidate is None:
            return
        if not settings.meets_min_tier(candidate.tier):
            return

        account_balance = self.account_balance_provider()
        try:
            raw_size = position_size(
                account_balance, settings.risk_percent, candidate.entry, candidate.stop_loss,
                self.unit_value_per_point,
            )
        except ValueError:
            return
        quantity = min(int(raw_size), settings.max_contracts)
        if quantity < 1:
            return

        side = OrderSide.BUY if candidate.direction == Direction.BULLISH else OrderSide.SELL
        result = self.broker.place_order(OrderRequest(
            symbol=self.symbol,
            side=side,
            quantity=quantity,
            limit_price=candidate.entry,
            stop_loss=candidate.stop_loss,
            take_profit=candidate.take_profit,
            client_order_id=f"{self.symbol}-{i}",
        ))

        self.state = "pending"
        self.active = _ActiveTrade(
            direction=candidate.direction,
            entry=candidate.entry,
            stop_loss=candidate.stop_loss,
            take_profit=candidate.take_profit,
            invalidation_price=candidate.invalidation_price,
            tier_name=candidate.tier.name,
        )
        self._pending_broker_order_id = result.broker_order_id
        self._pending_placed_at_index = i
        self._pending_invalidation = candidate.invalidation_price
        self._pending_direction = candidate.direction
