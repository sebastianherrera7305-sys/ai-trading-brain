"""JSON-safe conversions from broker dataclasses to the wire shapes the
dashboard expects (see dashboard/app.js's message handlers)."""

from dataclasses import asdict
from typing import Any, Dict

from trading_brain.broker.base import AccountSummary, Position


def position_to_dict(p: Position) -> Dict[str, Any]:
    return asdict(p)


def account_to_dict(a: AccountSummary) -> Dict[str, Any]:
    return asdict(a)
