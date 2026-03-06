"""
main.py — Ant Colony Finance Orchestrator

Launches the full swarm:
1. Spawns agent castes for each tracked token
2. Runs all agents concurrently via asyncio
3. Feeds signals into the ColonyBrain
4. ColonyBrain emits decisions → ColonyTrader executes

Usage:
    python main.py                    # mainnet (reads .env)
    python main.py --simulate         # simulation mode (no real trades)
    python main.py --token 0xABC...   # single token override
"""
import asyncio
import argparse
import time
from loguru import logger

from settings import settings
from whale_agent import WhaleAgent
from technical_agent import TechnicalAgent
from liquidity_agent import LiquidityAgent
from sentiment_agent import SentimentAgent
from arbitrage_agent import ArbitrageAgent
from discovery_agent import DiscoveryAgent
from colony_brain import ColonyBrain
from trader import ColonyTrader
from portfolio import PaperPortfolio
from ws_server import start_server, broadcast


# ── Tokens to track ───────────────────────────────────────────────────
# Seed tokens. Discovery agent will auto-add more from Aerodrome.
TRACKED_TOKENS = [
    {
        "symbol":       "BRETT",
        "address":      "0x532f27101965dd16442E59d40670FaF5eBB142E4",
        "coingecko_id": "based-brett",
        "twitter":      ["$BRETT", "Brett Base token", "basedBrett"],
    },
    {
        "symbol":       "AERO",
        "address":      "0x940181a94A35A4569E4529A3CDfB74e38FD98631",
        "coingecko_id": "aerodrome-finance",
        "twitter":      ["$AERO", "Aerodrome Finance Base"],
    },
    {
        "symbol":       "VIRTUAL",
        "address":      "0x0b3e328455c4059EEb9e3f84b5543F74E24e7E1b",
        "coingecko_id": "virtual-protocol",
        "twitter":      ["$VIRTUAL", "Virtuals Protocol"],
    },
]


def build_agents_for_token(token: dict) -> list:
    """Spawn one agent of each caste for a given token."""
    symbol  = token["symbol"]
    address = token["address"]
    return [
        WhaleAgent(token=symbol,     token_address=address),
        TechnicalAgent(token=symbol, coingecko_id=token["coingecko_id"]),
        LiquidityAgent(token=symbol, token_address=address),
        SentimentAgent(token=symbol, search_terms=token["twitter"]),
        ArbitrageAgent(token=symbol, token_address=address),
    ]


async def run_swarm_cycle(
    brain:   ColonyBrain,
    trader:  ColonyTrader,
    tokens:  list[dict],
    simulate: bool = False,
) -> dict:
    """
    One full swarm cycle:
    1. Spawn agents for all tokens
    2. Run all agents in parallel
    3. Ingest signals into ColonyBrain
    4. Aggregate → decision
    5. Execute if threshold crossed
    """
    all_agents = []
    for token in tokens:
        all_agents.extend(build_agents_for_token(token))

    logger.info(f"[SWARM] Launching {len(all_agents)} agents across {len(tokens)} tokens")

    # Run all agents concurrently
    signals = await asyncio.gather(
        *[agent.run() for agent in all_agents],
        return_exceptions=True,
    )

    # Filter out failures
    valid_signals = [s for s in signals if s is not None and not isinstance(s, Exception)]
    logger.info(f"[SWARM] {len(valid_signals)}/{len(all_agents)} agents returned signals")

    # Ingest into ColonyBrain
    for signal in valid_signals:
        await brain.ingest_signal(signal)

    # Aggregate per-token decisions
    results = {}
    for token in tokens:
        symbol   = token["symbol"]
        decision = await brain.aggregate(symbol)
        results[symbol] = decision

        if decision.execute and not simulate:
            # Pass the actual token address to the trader
            decision.token = token["address"]
            trade_result   = await trader.execute_decision(decision)
            results[symbol + "_trade"] = trade_result
        elif decision.execute and simulate:
            logger.info(
                f"[SIM] Would execute {decision.action} on {symbol} "
                f"(confidence={decision.confidence:.1%})"
            )

    return results


async def main(simulate: bool = False, paper: bool = False):
    logger.info("🐜 Ant Colony Finance starting up...")
    logger.info(f"   Network:   {settings.NETWORK_NAME} ({settings.ACTIVE_RPC_URL})")
    logger.info(f"   Threshold: {settings.CONSENSUS_THRESHOLD:.0%}")
    logger.info(f"   Simulate:  {simulate}")

    # ── Start live dashboard WebSocket server ─────────────────────────
    ws_runner = await start_server()

    # Initialize infrastructure
    brain  = ColonyBrain()
    trader = ColonyTrader()

    await brain.connect()
    await trader.connect()

    # ── Paper trading portfolio ───────────────────────────────────────
    paper_portfolio = None
    if paper:
        paper_portfolio = PaperPortfolio(starting_balance=1_000.0)
        paper_portfolio.load()
        logger.info("[PAPER] Paper trading mode active — $1,000 virtual balance")

    # ── Discovery agent ───────────────────────────────────────────────
    async def on_new_token(token_config: dict):
        """Called by DiscoveryAgent when a new token passes safety filters."""
        sym = token_config["symbol"]
        if any(t["symbol"] == sym for t in TRACKED_TOKENS):
            return
        TRACKED_TOKENS.append(token_config)
        logger.success(
            f"[SWARM] 🆕 Token added to swarm: {sym} "
            f"(TVL=${token_config.get('_tvl', 0):,.0f} "
            f"vol_growth={token_config.get('_volume_growth', 0):.0%})"
        )

    discovery = DiscoveryAgent(on_new_token=on_new_token, scan_interval_seconds=300)
    discovery.seed_known([t["address"] for t in TRACKED_TOKENS])
    asyncio.create_task(discovery.run_forever())
    logger.info("[SWARM] Discovery scout launched — scanning Aerodrome every 5 min")

    cycle = 0
    while True:
        cycle += 1
        logger.info(f"\n{'='*50}")
        logger.info(f"🐜 COLONY CYCLE #{cycle}")
        logger.info(f"{'='*50}")

        start = time.time()
        try:
            results = await run_swarm_cycle(
                brain=brain,
                trader=trader,
                tokens=TRACKED_TOKENS,
                simulate=simulate,
            )

            # Log cycle summary
            for token in TRACKED_TOKENS:
                sym      = token["symbol"]
                decision = results.get(sym)
                if decision:
                    logger.info(
                        f"  {sym}: {decision.action} "
                        f"(buy={decision.buy_score:.1%} "
                        f"sell={decision.sell_score:.1%} "
                        f"agents={decision.signal_count})"
                    )
            
            # Broadcast to dashboard
            await broadcast({
                'type': 'cycle',
                'cycle': cycle,
                'tokens': [
                    {
                        'symbol': token['symbol'],
                        'decision': {
                            'action': results.get(token['symbol']).action if results.get(token['symbol']) else 'HOLD',
                            'confidence': results.get(token['symbol']).confidence if results.get(token['symbol']) else 0,
                            'buy_score': results.get(token['symbol']).buy_score if results.get(token['symbol']) else 0,
                            'sell_score': results.get(token['symbol']).sell_score if results.get(token['symbol']) else 0,
                        }
                    }
                    for token in TRACKED_TOKENS
                ]
            })

        except Exception as e:
            logger.error(f"[SWARM] Cycle {cycle} failed: {e}")

        elapsed = time.time() - start
        sleep_time = max(0, settings.SIGNAL_WINDOW_SECONDS - elapsed)
        logger.info(f"\n[SWARM] Cycle took {elapsed:.1f}s. Sleeping {sleep_time:.1f}s...")
        await asyncio.sleep(sleep_time)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ant Colony Finance")
    parser.add_argument("--simulate", action="store_true", help="Simulate trades (no real execution)")
    parser.add_argument("--paper", action="store_true", help="Paper trading mode — fake portfolio, real prices")
    args = parser.parse_args()

    asyncio.run(main(simulate=args.simulate, paper=args.paper))
