import time
import MetaTrader5 as mt5
from modules import connector, strategy, execution, alerts
from modules.data_engine import get_tick, normalize_symbol
from modules.risk import pre_trade_checks, record_trade_result, daily_summary
from settings import SYMBOLS


def check_closed_trades(known_tickets: set) -> set:
    """
    Compare currently open positions against known tickets.
    Any ticket that disappeared has closed — record its P&L.
    Returns updated set of open tickets.
    """
    positions   = mt5.positions_get(magic=0) or []
    open_tickets = {p.ticket for p in positions}

    closed = known_tickets - open_tickets
    for ticket in closed:
        deals = mt5.history_deals_get(position=ticket)
        if deals:
            pnl = sum(d.profit for d in deals)
            record_trade_result(pnl)
            print(f"[Risk] Trade #{ticket} closed | P&L: {pnl:+.2f}")

    return open_tickets


def start_bot():
    print("=" * 30 + "\n FROST BOT ACTIVE \n" + "=" * 30)
    if not connector.connect():
        return

    alerts.send("❄️ Frost Bot Online")

    known_tickets: set = set()

    try:
        while True:
            # --- Track closed trades for risk accounting ---
            known_tickets = check_closed_trades(known_tickets)

            # --- Manage open positions (BE + partials) ---
            execution.manage_open_positions()

            # --- Scan watchlist ---
            for symbol in SYMBOLS:
                print(f"[*] Scanning {symbol}...", end="\r")

                result = strategy.score_setup(symbol)

                # Skip invalid or low-score setups
                if not result["valid"]:
                    continue

                direction  = result["bias"]             # "bullish" or "bearish"
                score      = result["score"]["total"]   # 0–10
                grade      = result["score"]["grade"]   # A+, A, B, avoid
                sl         = result["sl"]
                tp         = result["tp"]
                rr         = result["rr"]
                entry_type = result["entry_type"]
                poi        = result["poi_type"]

                # Only A and A+ grades
                if grade == "B":
                    continue

                # --- Risk gate — check all rules before placing ---
                ok, reason = pre_trade_checks(symbol=symbol, score=score)
                if not ok:
                    print(f"[Risk] {symbol} blocked — {reason}")
                    continue

                # --- Get live price ---
                tick = get_tick(normalize_symbol(symbol))
                if not tick:
                    continue

                price         = tick["ask"] if direction == "bullish" else tick["bid"]
                direction_int = 1 if direction == "bullish" else -1

                # --- Place order ---
                order_result = execution.place_order(
                    symbol    = symbol,
                    direction = direction_int,
                    price     = price,
                    sl        = sl,
                    tp        = tp,
                    score     = score,
                )

                if order_result.get("success"):
                    ticket = order_result.get("ticket")
                    if ticket:
                        known_tickets.add(ticket)

                    alerts.send(
                        f"✅ {symbol} | {direction.upper()} | "
                        f"Score: {score}/10 ({grade}) | "
                        f"RR: {rr} | {poi} | {entry_type}"
                    )

            time.sleep(60)   # M1 candle closes every 60 seconds

    except KeyboardInterrupt:
        print("\nStopping...")
        summary = daily_summary()
        print(
            f"\n📊 Daily Summary\n"
            f"   Date:        {summary['date']}\n"
            f"   Start Bal:   ${summary['start_balance']:,.2f}\n"
            f"   Equity Now:  ${summary['current_equity']:,.2f}\n"
            f"   Daily P&L:   ${summary['daily_pnl']:+,.2f}\n"
            f"   Losses:      {summary['daily_losses']}\n"
            f"   Halted:      {summary['halted']}"
        )

    finally:
        connector.disconnect()


if __name__ == "__main__":
    start_bot()