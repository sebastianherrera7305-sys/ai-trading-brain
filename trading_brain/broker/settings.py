"""
Settings Module — AI Trading Brain, Phase 3

Everything a human needs to control without touching code: how much to risk,
which instruments/tiers are live, and the kill switch. Persisted to a JSON
file so a restart doesn't silently reset the account back to defaults --
the risk knobs a user set deliberately (or the kill switch they hit) must
survive a crash or redeploy.

Defaults are deliberately conservative: paper mode, small risk, S-tier only,
and NOT trading any instrument until the user explicitly turns it on. This
module never places an order; it only says what's allowed.
"""

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, Optional

from ..scoring import Tier

_TIER_ORDER = [Tier.REJECT, Tier.B, Tier.A, Tier.S]


@dataclass
class BotSettings:
    account_mode: str = "paper"  # "paper" | "live" -- never defaults to live
    risk_percent: float = 0.5    # % of account equity risked per trade
    max_contracts: int = 1
    min_tier: str = "S"          # Tier name: only trade setups at or above this tier
    enabled_instruments: Dict[str, bool] = field(default_factory=lambda: {
        "GC=F": False, "ES=F": False, "CL=F": False, "EURUSD=X": False,
    })
    kill_switch_active: bool = False  # manual halt: no new entries, existing positions untouched
    daily_drawdown_limit_percent: float = 2.0  # halt new entries if today's realized loss exceeds this

    def meets_min_tier(self, tier: Tier) -> bool:
        try:
            floor = _TIER_ORDER.index(Tier[self.min_tier])
        except KeyError:
            floor = _TIER_ORDER.index(Tier.S)
        return _TIER_ORDER.index(tier) >= floor

    def is_instrument_enabled(self, symbol: str) -> bool:
        return bool(self.enabled_instruments.get(symbol, False))

    def trading_allowed(self) -> bool:
        """The single gate engine_runner must check before acting on any new
        signal. Existing open positions are never force-closed by this --
        only NEW entries are blocked."""
        return not self.kill_switch_active

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "BotSettings":
        known = {f for f in cls.__dataclass_fields__}
        filtered = {k: v for k, v in data.items() if k in known}
        return cls(**filtered)


class SettingsStore:
    """Loads/saves BotSettings to a JSON file. Missing or corrupt file falls
    back to defaults rather than raising -- a bad settings.json must not
    prevent the service from starting up in a safe (paper, kill-switch-off,
    nothing-enabled) state."""

    def __init__(self, path: Optional[Path] = None):
        self.path = path or Path(__file__).resolve().parent.parent.parent / "settings.json"

    def load(self) -> BotSettings:
        if not self.path.exists():
            return BotSettings()
        try:
            with open(self.path, "r") as f:
                data = json.load(f)
            return BotSettings.from_dict(data)
        except (json.JSONDecodeError, OSError, TypeError):
            return BotSettings()

    def save(self, settings: BotSettings) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.path.with_suffix(".json.tmp")
        with open(tmp_path, "w") as f:
            json.dump(settings.to_dict(), f, indent=2)
        tmp_path.replace(self.path)  # atomic on POSIX -- no half-written settings.json
