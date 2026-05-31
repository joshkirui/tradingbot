"""
FROST BOT 2.0 — Risk Engine

Rules:
    - Risk 0.5–1% per trade (scaled by score)
    - Max 3 losses per day → halt trading
    - Max daily drawdown 3% → halt trading
    - Max open positions 3
    - Only A/A+ setups (score 7+) — enforced in main, guarded here too
    - Dynamic RR targets: score 9–10 → 1:5+, score 7–8 → 1:3
"""

import json
import os
from datetime import datetime, timezone

import MetaTrader5 as mt5

from settings import MIN_LOT, MAX_LOT, EA_MAGIC

# ---------------------------------------------------------------------------
# Constants — tweak in settings.py if you prefer
# ---------------------------------------------------------------------------

RISK_PER_TRADE_MIN  = 0.005   # 0.5% of balance per trade (low score)
RISK_PER_TRADE_MAX  = 0.01    # 1.0% of balance per trade (high score)
MAX_DAILY_LOSSES    = 3       # halt after 3 losing trades in a day
MAX_DAILY_DRAWDOWN  = 0.03    # halt if equity drops 3% below start-of-day balance
MAX_OPEN_POSITIONS  = 3       # never more than 3 concurrent trades
MIN_SCORE           = 7       # reject anything below this

# ---------------------------------------------------------------------------
# Daily state — persisted to a lightweight JSON file
# ---------------------------------------------------------------------------

STATE_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "risk_state.json")


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _load_state() -> dict:
    try:
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        with open(STATE_FILE, "r") as f:
            state = json.load(f)
        if state.get("date") != _today():
            return _reset_state()
        return state
    except (FileNotFoundError, json.JSONDecodeError):
        return _reset_state()


def _save_state(state: dict):
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def _reset_state() -> dict:
    acc   = mt5.account_info()
    bal   = float(acc.balance) if acc else 0.0
    state = {
        "date":             _today(),
        "start_balance":    bal,
        "daily_losses":     0,
        "daily_pnl":        0.0,
        "halted":           False,
        "halt_reason":      "",
    }
    _save_state(state)
    return state


# ---------------------------------------------------------------------------
# Lot sizing — risk-based, score-scaled
# ---------------------------------------------------------------------------

def calculate_dynamic_lot(score: int, balance: float) -> float:
    """
    Risk between 0.5% and 1.0% of balance, scaled by score (0–10).

    Score 7  → 0.5% risk
    Score 10 → 1.0% risk

    Lot = (risk_amount / sl_points) — simplified to a multiplier model
    since exact SL in points is handled by the execution engine.
    """
    if balance <= 0:
        return MIN_LOT

    # Scale risk % linearly between min and max by score
    t          = max(0.0, min(1.0, (score - MIN_SCORE) / (10 - MIN_SCORE)))
    risk_pct   = RISK_PER_TRADE_MIN + t * (RISK_PER_TRADE_MAX - RISK_PER_TRADE_MIN)
    risk_amount = balance * risk_pct

    # Map risk amount to lot — normalised against balance bands
    # For a $1M demo account this produces sensible lots;
    # the clamp to MIN/MAX_LOT keeps it safe on any account size.
    lot = risk_amount / (balance * 0.01) * MIN_LOT * 10
    lot = max(MIN_LOT, min(MAX_LOT, round(lot, 2)))
    return lot


# ---------------------------------------------------------------------------
# Pre-trade checks — call before every order
# ---------------------------------------------------------------------------

def pre_trade_checks(symbol: str = "", score: int = 0) -> tuple[bool, str]:
    """
    Returns (True, "ok") if the bot is allowed to trade.
    Returns (False, reason) if any rule is violated.

    Checks (in order):
        1. Daily halt flag
        2. Max daily losses
        3. Max daily drawdown
        4. Max open positions
        5. Minimum score
    """
    state = _load_state()

    # 1. Already halted today
    if state["halted"]:
        return False, f"Trading halted: {state['halt_reason']}"

    acc = mt5.account_info()
    if acc is None:
        return False, "Cannot read account info"

    # 2. Max daily losses
    if state["daily_losses"] >= MAX_DAILY_LOSSES:
        _halt(state, f"Max daily losses reached ({MAX_DAILY_LOSSES})")
        return False, state["halt_reason"]

    # 3. Max daily drawdown
    start_bal = state["start_balance"] or float(acc.balance)
    drawdown  = (start_bal - float(acc.equity)) / start_bal if start_bal > 0 else 0
    if drawdown >= MAX_DAILY_DRAWDOWN:
        _halt(state, f"Max drawdown hit ({drawdown*100:.1f}%)")
        return False, state["halt_reason"]

    # 4. Max open positions
    positions = mt5.positions_get(magic=EA_MAGIC)
    open_count = len(positions) if positions else 0
    if open_count >= MAX_OPEN_POSITIONS:
        return False, f"Max open positions reached ({MAX_OPEN_POSITIONS})"

    # 5. Minimum score
    if score and score < MIN_SCORE:
        return False, f"Score {score}/10 below minimum ({MIN_SCORE})"

    return True, "Risk levels within limits"


# ---------------------------------------------------------------------------
# Post-trade update — call after a trade closes
# ---------------------------------------------------------------------------

def record_trade_result(pnl: float):
    """
    Call this after each trade closes with the P&L in account currency.
    Updates daily loss counter and total P&L.
    """
    state = _load_state()
    state["daily_pnl"] += pnl
    if pnl < 0:
        state["daily_losses"] += 1
        print(f"[Risk] Loss recorded. Daily losses: {state['daily_losses']}/{MAX_DAILY_LOSSES}")
    _save_state(state)


# ---------------------------------------------------------------------------
# Dynamic RR target — call to get TP multiplier by score
# ---------------------------------------------------------------------------

def get_rr_target(score: int) -> float:
    """
    Score 9–10  → target 1:5
    Score 7–8   → target 1:3
    Below 7     → don't trade (returns 0)
    """
    if score >= 9: return 5.0
    if score >= 7: return 3.0
    return 0.0


# ---------------------------------------------------------------------------
# Daily summary — call at end of session
# ---------------------------------------------------------------------------

def daily_summary() -> dict:
    state = _load_state()
    acc   = mt5.account_info()
    return {
        "date":          state["date"],
        "start_balance": state["start_balance"],
        "current_equity": float(acc.equity) if acc else 0.0,
        "daily_pnl":     state["daily_pnl"],
        "daily_losses":  state["daily_losses"],
        "halted":        state["halted"],
        "halt_reason":   state["halt_reason"],
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _halt(state: dict, reason: str):
    state["halted"]      = True
    state["halt_reason"] = reason
    _save_state(state)
    print(f"[Risk] ⛔ TRADING HALTED — {reason}")