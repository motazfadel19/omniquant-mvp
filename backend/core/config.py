"""
Central configuration.

Every tunable previously scattered across analyzer.py / backtest.py / smc.py
now lives here so that the backtest and the live engine can be forced to use
*identical* rules (that mismatch was the single biggest correctness bug of v0.5).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]


def _env_str(name: str, default: str) -> str:
    return os.getenv(name, default)


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(float(os.getenv(name, default)))
    except (TypeError, ValueError):
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_list(name: str, default: str) -> list[str]:
    raw = os.getenv(name, default)
    return [s.strip().upper() for s in raw.split(",") if s.strip()]


@dataclass
class Settings:
    # ---------------- Runtime mode ----------------
    # "paper" never reaches the broker: orders are simulated and logged.
    # "live"  sends real orders to MT5.
    trading_mode: str = "paper"

    # ---------------- Security ----------------
    auth_token: str = "change-me"

    # ---------------- Instruments ----------------
    stream_symbols: list[str] = field(default_factory=lambda: ["XAUUSD"])
    heatmap_symbols: list[str] = field(default_factory=lambda: ["XAUUSD"])
    allowed_symbols: list[str] = field(default_factory=list)
    # Empty == trade both directions. Restricting to BUY only must be a
    # deliberate, documented choice — never a hardcoded `if signal != "BUY"`.
    allowed_directions: list[str] = field(default_factory=list)

    # ---------------- Position sizing ----------------
    max_lot_size: float = 0.5
    default_lot_size: float = 0.01

    # ---------------- Strategy (single source of truth) ----------------
    # These are used by BOTH the backtest and the live engine.
    min_score: float = 0.50
    min_confluences: int = 3
    stronger_by: float = 1.5
    min_confidence: float = 0.30
    sl_atr_mult: float = 1.5
    tp_atr_mult: float = 2.5
    max_bars_held: int = 50

    # ---------------- Execution realism ----------------
    spread_points: float = 20.0          # round-turn spread applied in backtest
    commission_r: float = 0.10           # round-turn commission, expressed in R
    slippage_points: float = 0.0

    # ---------------- Risk guardrails ----------------
    max_concurrent_positions: int = 3     # positions, NOT distinct symbols
    cooldown_seconds: int = 3600          # min gap between two entries same symbol
    max_trades_per_day: int = 10
    max_daily_loss_r: float = 3.0         # trip the kill switch at -3R in a day
    max_daily_loss_pct: float = 2.0       # ...or at -2% of the day's start balance
    max_spread_points: float = 100.0
    min_stop_points: int = 0              # 0 = use broker stops_level

    # ---------------- Loops ----------------
    ai_interval_sec: int = 60
    stream_interval_sec: int = 1
    trade_logger_interval_sec: int = 10
    trade_logger_lookback_days: int = 30

    # ---------------- ML ----------------
    ml_threshold: float = 0.65
    use_ml: bool = False
    # Minimum labelled samples before training is allowed at all.
    ml_min_samples: int = 1000

    # ---------------- Storage ----------------
    db_path: str = str(BACKEND_DIR / "omniquant.db")

    # Values that mean "the operator never configured a secret".  Compared
    # case-insensitively.  Keep in sync with tools/setup_env.py.
    PLACEHOLDER_TOKENS: tuple[str, ...] = (
        "", "change-me", "changeme", "dev-local-token-change-me",
        "omniquant-local-dev-token", "your-token-here", "token", "secret",
    )

    @property
    def live(self) -> bool:
        return self.trading_mode.lower() == "live"

    @property
    def auth_configured(self) -> bool:
        """A real secret exists (not the sample value, not something trivially short)."""
        token = (self.auth_token or "").strip()
        return token.lower() not in self.PLACEHOLDER_TOKENS and len(token) >= 24

    @property
    def auth_weakness(self) -> str | None:
        """Why the token is unusable, or None when it is fine."""
        token = (self.auth_token or "").strip()
        if not token or token.lower() in self.PLACEHOLDER_TOKENS:
            return "AUTH_TOKEN is unset or still the sample value"
        if len(token) < 24:
            return f"AUTH_TOKEN is only {len(token)} characters (24+ recommended)"
        return None

    def is_symbol_allowed(self, symbol: str) -> bool:
        if not self.allowed_symbols:
            return True
        return symbol.upper() in self.allowed_symbols

    def is_direction_allowed(self, direction: str) -> bool:
        if not self.allowed_directions:
            return True
        return direction.upper() in self.allowed_directions


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Load settings once from the environment (dotenv is loaded by the caller)."""
    return Settings(
        trading_mode=_env_str("TRADING_MODE", "paper").lower(),
        auth_token=_env_str("AUTH_TOKEN", "change-me"),
        stream_symbols=_env_list("STREAM_SYMBOLS", "XAUUSD"),
        heatmap_symbols=_env_list("HEATMAP_SYMBOLS", "XAUUSD"),
        allowed_symbols=_env_list("ALLOWED_SYMBOLS", ""),
        allowed_directions=_env_list("ALLOWED_DIRECTIONS", ""),
        max_lot_size=_env_float("MAX_LOT_SIZE", 0.5),
        default_lot_size=_env_float("DEFAULT_LOT_SIZE", 0.01),
        min_score=_env_float("MIN_SCORE", 0.50),
        min_confluences=_env_int("MIN_CONFLUENCES", 3),
        stronger_by=_env_float("STRONGER_BY", 1.5),
        min_confidence=_env_float("MIN_CONFIDENCE", 0.30),
        sl_atr_mult=_env_float("SL_ATR_MULT", 1.5),
        tp_atr_mult=_env_float("TP_ATR_MULT", 2.5),
        max_bars_held=_env_int("MAX_BARS_HELD", 50),
        spread_points=_env_float("SPREAD_POINTS", 20.0),
        commission_r=_env_float("COMMISSION_R", 0.10),
        slippage_points=_env_float("SLIPPAGE_POINTS", 0.0),
        max_concurrent_positions=_env_int("MAX_CONCURRENT_POSITIONS", 3),
        cooldown_seconds=_env_int("COOLDOWN_SECONDS", 3600),
        max_trades_per_day=_env_int("MAX_TRADES_PER_DAY", 10),
        max_daily_loss_r=_env_float("MAX_DAILY_LOSS_R", 3.0),
        max_daily_loss_pct=_env_float("MAX_DAILY_LOSS_PCT", 2.0),
        max_spread_points=_env_float("MAX_SPREAD_POINTS", 100.0),
        min_stop_points=_env_int("MIN_STOP_POINTS", 0),
        ai_interval_sec=_env_int("AI_INTERVAL_SEC", 60),
        stream_interval_sec=_env_int("STREAM_INTERVAL_SEC", 1),
        trade_logger_interval_sec=_env_int("TRADE_LOGGER_INTERVAL_SEC", 10),
        trade_logger_lookback_days=_env_int("TRADE_LOGGER_LOOKBACK_DAYS", 30),
        ml_threshold=_env_float("ML_THRESHOLD", 0.65),
        use_ml=_env_bool("USE_ML", False),
        ml_min_samples=_env_int("ML_MIN_SAMPLES", 1000),
        db_path=_env_str("DB_PATH", str(BACKEND_DIR / "omniquant.db")),
    )
