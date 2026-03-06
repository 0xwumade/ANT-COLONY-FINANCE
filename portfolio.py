"""
paper_trading/portfolio.py — Paper Trading Portfolio Tracker

Tracks a fake portfolio against live market data.
Every time the colony makes a decision, this records it as if
a real trade happened — but with fake money.

Saves everything to paper_portfolio.json so you can check
performance anytime, even after restarting.

Usage:
    python main.py --paper

What it tracks:
    - Starting balance (default $1,000 USDC)
    - Every BUY/SELL the colony would have executed
    - Current holdings per token
    - Unrealised P&L (profit/loss on open positions)
    - Realised P&L (profit/loss on closed positions)
    - Win rate, best trade, worst trade
    - Portfolio value over time
"""

import json
import time
import asyncio
import aiohttp
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional
from loguru import logger

from colony_brain import ColonyDecision

PORTFOLIO_FILE = Path("paper_portfolio.json")
COINGECKO_BASE = "https://api.coingecko.com/api/v3"

# Starting paper balance in USD
STARTING_BALANCE_USD = 1_000.0
# Max % of portfolio per trade (position sizing)
MAX_POSITION_PCT = 0.10    # 10% of portfolio per trade
MIN_TRADE_USD    = 10.0    # minimum $10 per trade


@dataclass
class Position:
    """An open holding in a token."""
    symbol:        str
    coingecko_id:  str
    quantity:      float     # how many tokens held
    avg_buy_price: float     # average price paid
    total_cost:    float     # total USD spent
    open_time:     float     # unix timestamp


@dataclass
class Trade:
    """A completed trade record."""
    id:            int
    symbol:        str
    action:        str        # BUY or SELL
    quantity:      float
    price:         float
    total_usd:     float
    confidence:    float
    signal_count:  int
    timestamp:     float
    pnl:           Optional[float] = None   # filled on SELL


@dataclass
class Portfolio:
    """Full paper portfolio state."""
    starting_balance:  float = STARTING_BALANCE_USD
    cash_usd:          float = STARTING_BALANCE_USD
    positions:         dict  = field(default_factory=dict)   # symbol → Position
    trades:            list  = field(default_factory=list)   # list of Trade
    trade_counter:     int   = 0
    created_at:        float = field(default_factory=time.time)
    last_updated:      float = field(default_factory=time.time)


class PaperPortfolio:
    """
    Paper trading engine.

    Intercepts ColonyDecisions and executes them against
    real live prices — but with fake money.

    Call record_decision() after each colony cycle.
    Call print_summary() to see current performance.
    """

    def __init__(self, starting_balance: float = STARTING_BALANCE_USD):
        self.starting_balance = starting_balance
        self._portfolio: Optional[Portfolio] = None
        self._price_cache: dict[str, float] = {}

    # ── Persistence ───────────────────────────────────────────────────

    def load(self):
        """Load portfolio from disk, or create fresh one."""
        if PORTFOLIO_FILE.exists():
            try:
                data = json.loads(PORTFOLIO_FILE.read_text())
                p = Portfolio(**{k: v for k, v in data.items()
                                 if k in Portfolio.__dataclass_fields__})
                # Rebuild positions as Position objects
                p.positions = {
                    sym: Position(**pos)
                    for sym, pos in data.get("positions", {}).items()
                }
                # Rebuild trades as Trade objects
                p.trades = [Trade(**t) for t in data.get("trades", [])]
                self._portfolio = p
                logger.info(
                    f"[PAPER] Portfolio loaded — "
                    f"${p.cash_usd:.2f} cash, "
                    f"{len(p.positions)} open positions, "
                    f"{len(p.trades)} trades"
                )
            except Exception as e:
                logger.warning(f"[PAPER] Could not load portfolio: {e}. Starting fresh.")
                self._new_portfolio()
        else:
            self._new_portfolio()

    def _new_portfolio(self):
        self._portfolio = Portfolio(
            starting_balance = self.starting_balance,
            cash_usd         = self.starting_balance,
        )
        logger.info(
            f"[PAPER] New portfolio created — "
            f"starting balance: ${self.starting_balance:,.2f}"
        )
        self._save()

    def _save(self):
        p = self._portfolio
        data = {
            "starting_balance": p.starting_balance,
            "cash_usd":         p.cash_usd,
            "positions":        {sym: asdict(pos) for sym, pos in p.positions.items()},
            "trades":           [asdict(t) for t in p.trades],
            "trade_counter":    p.trade_counter,
            "created_at":       p.created_at,
            "last_updated":     time.time(),
        }
        PORTFOLIO_FILE.write_text(json.dumps(data, indent=2))

    # ── Live price fetching ───────────────────────────────────────────

    async def get_price(self, coingecko_id: str) -> Optional[float]:
        """Fetch live USD price from CoinGecko."""
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{COINGECKO_BASE}/simple/price"
                params = {"ids": coingecko_id, "vs_currencies": "usd"}
                async with session.get(url, params=params,
                                       timeout=aiohttp.ClientTimeout(total=8)) as resp:
                    data = await resp.json()
                    price = data.get(coingecko_id, {}).get("usd")
                    if price:
                        self._price_cache[coingecko_id] = float(price)
                        return float(price)
        except Exception as e:
            logger.warning(f"[PAPER] Price fetch failed for {coingecko_id}: {e}")
            # Fall back to cache
            return self._price_cache.get(coingecko_id)
        return None

    # ── Trade execution ───────────────────────────────────────────────

    async def record_decision(
        self,
        decision:     ColonyDecision,
        coingecko_id: str,
        symbol:       str,
    ):
        """
        Called after each ColonyDecision.
        If execute=True, records a paper trade at the live price.
        """
        if not decision.execute:
            return

        price = await self.get_price(coingecko_id)
        if not price:
            logger.warning(f"[PAPER] No price for {symbol} — skipping trade record")
            return

        if decision.action == "BUY":
            await self._paper_buy(symbol, coingecko_id, price, decision)
        elif decision.action == "SELL":
            await self._paper_sell(symbol, coingecko_id, price, decision)

    async def _paper_buy(
        self,
        symbol:       str,
        coingecko_id: str,
        price:        float,
        decision:     ColonyDecision,
    ):
        p = self._portfolio

        # Size: confidence-scaled % of portfolio
        trade_pct   = MAX_POSITION_PCT * decision.confidence
        trade_usd   = p.cash_usd * trade_pct
        trade_usd   = max(min(trade_usd, p.cash_usd), 0)

        if trade_usd < MIN_TRADE_USD:
            logger.info(f"[PAPER] {symbol} BUY skipped — trade size ${trade_usd:.2f} below minimum")
            return

        quantity = trade_usd / price

        # Update cash
        p.cash_usd -= trade_usd

        # Update or create position
        if symbol in p.positions:
            pos = p.positions[symbol]
            total_qty   = pos.quantity + quantity
            total_cost  = pos.total_cost + trade_usd
            pos.quantity      = total_qty
            pos.avg_buy_price = total_cost / total_qty
            pos.total_cost    = total_cost
        else:
            p.positions[symbol] = Position(
                symbol        = symbol,
                coingecko_id  = coingecko_id,
                quantity      = quantity,
                avg_buy_price = price,
                total_cost    = trade_usd,
                open_time     = time.time(),
            )

        # Record trade
        p.trade_counter += 1
        p.trades.append(Trade(
            id           = p.trade_counter,
            symbol       = symbol,
            action       = "BUY",
            quantity     = quantity,
            price        = price,
            total_usd    = trade_usd,
            confidence   = decision.confidence,
            signal_count = decision.signal_count,
            timestamp    = time.time(),
        ))

        logger.success(
            f"[PAPER] 🟢 BUY {symbol} "
            f"${trade_usd:.2f} @ ${price:.6f} "
            f"({quantity:.4f} tokens) "
            f"confidence={decision.confidence:.0%} "
            f"cash_left=${p.cash_usd:.2f}"
        )
        self._save()

    async def _paper_sell(
        self,
        symbol:       str,
        coingecko_id: str,
        price:        float,
        decision:     ColonyDecision,
    ):
        p = self._portfolio

        if symbol not in p.positions:
            logger.debug(f"[PAPER] {symbol} SELL — no position to sell")
            return

        pos       = p.positions[symbol]
        sell_qty  = pos.quantity
        sell_usd  = sell_qty * price
        pnl       = sell_usd - pos.total_cost
        pnl_pct   = (pnl / pos.total_cost) * 100

        # Update cash
        p.cash_usd += sell_usd
        del p.positions[symbol]

        # Record trade
        p.trade_counter += 1
        p.trades.append(Trade(
            id           = p.trade_counter,
            symbol       = symbol,
            action       = "SELL",
            quantity      = sell_qty,
            price        = price,
            total_usd    = sell_usd,
            confidence   = decision.confidence,
            signal_count = decision.signal_count,
            timestamp    = time.time(),
            pnl          = pnl,
        ))

        emoji = "🟢" if pnl >= 0 else "🔴"
        logger.success(
            f"[PAPER] {emoji} SELL {symbol} "
            f"${sell_usd:.2f} @ ${price:.6f} "
            f"P&L: ${pnl:+.2f} ({pnl_pct:+.1f}%) "
            f"cash=${p.cash_usd:.2f}"
        )
        self._save()

    # ── Performance summary ───────────────────────────────────────────

    async def get_portfolio_value(self) -> float:
        """Total value = cash + all open positions at live prices."""
        p     = self._portfolio
        total = p.cash_usd

        for sym, pos in p.positions.items():
            price = await self.get_price(pos.coingecko_id)
            if price:
                total += pos.quantity * price

        return total

    async def print_summary(self):
        """Print a full performance report to the terminal."""
        p             = self._portfolio
        total_value   = await self.get_portfolio_value()
        total_pnl     = total_value - p.starting_balance
        total_pnl_pct = (total_pnl / p.starting_balance) * 100

        sell_trades = [t for t in p.trades if t.action == "SELL" and t.pnl is not None]
        wins  = [t for t in sell_trades if t.pnl >= 0]
        losses= [t for t in sell_trades if t.pnl < 0]
        win_rate = len(wins) / len(sell_trades) * 100 if sell_trades else 0

        best  = max(sell_trades, key=lambda t: t.pnl, default=None)
        worst = min(sell_trades, key=lambda t: t.pnl, default=None)

        print("\n" + "═"*52)
        print("  🐜 ANT COLONY FINANCE — PAPER PORTFOLIO")
        print("═"*52)
        print(f"  Starting balance : ${p.starting_balance:>10,.2f}")
        print(f"  Current value    : ${total_value:>10,.2f}")
        print(f"  Total P&L        : ${total_pnl:>+10,.2f}  ({total_pnl_pct:+.1f}%)")
        print(f"  Cash available   : ${p.cash_usd:>10,.2f}")
        print("─"*52)
        print(f"  Total trades     : {len(p.trades)}")
        print(f"  Buy trades       : {len([t for t in p.trades if t.action=='BUY'])}")
        print(f"  Sell trades      : {len(sell_trades)}")
        print(f"  Win rate         : {win_rate:.1f}%  ({len(wins)}W / {len(losses)}L)")
        if best:
            print(f"  Best trade       : {best.symbol} +${best.pnl:.2f}")
        if worst:
            print(f"  Worst trade      : {worst.symbol} ${worst.pnl:.2f}")
        print("─"*52)

        if p.positions:
            print("  OPEN POSITIONS:")
            for sym, pos in p.positions.items():
                price = await self.get_price(pos.coingecko_id)
                if price:
                    curr_val = pos.quantity * price
                    unreal   = curr_val - pos.total_cost
                    unreal_pct = (unreal / pos.total_cost) * 100
                    print(f"    {sym:<10} qty={pos.quantity:.4f} "
                          f"avg=${pos.avg_buy_price:.6f} "
                          f"now=${price:.6f} "
                          f"P&L=${unreal:+.2f} ({unreal_pct:+.1f}%)")
        else:
            print("  No open positions.")

        print("═"*52 + "\n")
