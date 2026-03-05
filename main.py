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

from config.settings import settings
from agents.whale_agent     import WhaleAgent
from agents.technical_agent import TechnicalAgent
from agents.liquidity_agent import LiquidityAgent
from agents.sentiment_agent import SentimentAgent
from agents.arbitrage_agent import ArbitrageAgent
from consensus.colony_brain import ColonyBrain
from execution.trader       import ColonyTrader


# ── Tokens to track ───────────────────────────────────────────────────
# Add your tokens here: (symbol, address, coingecko_id, twitter_terms)
TRACKED_TOKENS = [
    {
        "symbol":       "BRETT",
        "address":      "0x532f27101965dd16442E59d40670FaF5eBB142E4",
        "coingecko_id": "based-brett",
        "twitter":      ["$BRETT", "Brett Base token", "basedBrett"],
    },
    {
        "symbol":       "DEGEN",
        "address":      "0x4ed4E862860beD51a9570b96d89aF5E1B0Efefed",
        "coingecko_id": "degen-base",
        "twitter":      ["$DEGEN", "Degen token", "DegenChain"],
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


async def main(simulate: bool = False):
    logger.info("🐜 Ant Colony Finance starting up...")
    logger.info(f"   Network:   Base ({settings.BASE_RPC_URL})")
    logger.info(f"   Threshold: {settings.CONSENSUS_THRESHOLD:.0%}")
    logger.info(f"   Simulate:  {simulate}")

    # Initialize infrastructure
    brain  = ColonyBrain()
    trader = ColonyTrader()

    await brain.connect()
    await trader.connect()

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

        except Exception as e:
            logger.error(f"[SWARM] Cycle {cycle} failed: {e}")

        elapsed = time.time() - start
        sleep_time = max(0, settings.SIGNAL_WINDOW_SECONDS - elapsed)
        logger.info(f"\n[SWARM] Cycle took {elapsed:.1f}s. Sleeping {sleep_time:.1f}s...")
        await asyncio.sleep(sleep_time)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ant Colony Finance")
    parser.add_argument("--simulate", action="store_true", help="Simulate trades (no real execution)")
    args = parser.parse_args()

    asyncio.run(main(simulate=args.simulate))
