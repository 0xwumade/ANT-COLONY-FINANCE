"""
agents/liquidity_agent.py — Monitors DEX pool liquidity changes

Watches Uniswap V3 and Aerodrome pools on Base for:
- Liquidity additions → bullish signal
- Liquidity removals  → bearish signal
- Pool imbalance      → directional signal
"""
import asyncio
import aiohttp
from loguru import logger

from base_agent import BaseAgent, PheromoneSignal, Signal
from settings import settings


# Uniswap V3 subgraph on Base (via The Graph)
UNISWAP_SUBGRAPH = "https://api.thegraph.com/subgraphs/name/uniswap/uniswap-v3-base"

POOL_QUERY = """
query PoolData($token: String!) {
  pools(
    where: { token0: $token }
    orderBy: totalValueLockedUSD
    orderDirection: desc
    first: 3
  ) {
    id
    totalValueLockedUSD
    volumeUSD
    token0Price
    token1Price
    poolHourData(orderBy: periodStartUnix, orderDirection: desc, first: 2) {
      tvlUSD
      volumeUSD
    }
  }
}
"""


class LiquidityAgent(BaseAgent):
    """
    Caste: LIQUIDITY (weight: 0.25)

    Signals based on pool TVL changes and volume/TVL ratio.
    - Rising TVL + volume → BUY (accumulation)
    - Falling TVL         → SELL (distribution)
    - High vol/TVL ratio  → momentum confirmation
    """

    def __init__(self, token: str, token_address: str):
        super().__init__(token=token, caste="liquidity")
        self.token_address = token_address.lower()
        self._analysis: dict = {}

    async def analyze(self) -> dict:
        try:
            async with aiohttp.ClientSession() as session:
                payload = {
                    "query":     POOL_QUERY,
                    "variables": {"token": self.token_address},
                }
                async with session.post(UNISWAP_SUBGRAPH, json=payload) as resp:
                    data = await resp.json()

            pools = data.get("data", {}).get("pools", [])

            total_tvl     = 0.0
            tvl_change    = 0.0
            total_volume  = 0.0

            for pool in pools:
                tvl = float(pool.get("totalValueLockedUSD", 0))
                vol = float(pool.get("volumeUSD", 0))
                total_tvl    += tvl
                total_volume += vol

                hour_data = pool.get("poolHourData", [])
                if len(hour_data) >= 2:
                    current_tvl  = float(hour_data[0].get("tvlUSD", 0))
                    previous_tvl = float(hour_data[1].get("tvlUSD", 1))
                    tvl_change  += (current_tvl - previous_tvl) / (previous_tvl or 1)

            vol_tvl_ratio = total_volume / (total_tvl or 1)

            self._analysis = {
                "total_tvl":     total_tvl,
                "tvl_change":    tvl_change,
                "total_volume":  total_volume,
                "vol_tvl_ratio": vol_tvl_ratio,
                "pool_count":    len(pools),
            }
            logger.debug(
                f"[LIQUIDITY:{self.agent_id}] TVL=${total_tvl:,.0f} "
                f"change={tvl_change:.3f} vol/tvl={vol_tvl_ratio:.3f}"
            )

        except Exception as e:
            logger.warning(f"[LIQUIDITY:{self.agent_id}] Analysis failed: {e}")
            self._analysis = {
                "total_tvl": 0, "tvl_change": 0,
                "total_volume": 0, "vol_tvl_ratio": 0, "pool_count": 0,
            }

        return self._analysis

    async def emit(self) -> PheromoneSignal:
        tvl_change    = self._analysis.get("tvl_change", 0)
        vol_tvl_ratio = self._analysis.get("vol_tvl_ratio", 0)
        total_tvl     = self._analysis.get("total_tvl", 0)

        # Low TVL = skip, unreliable signal
        if total_tvl < 10_000:
            return PheromoneSignal(
                agent_id=self.agent_id, caste=self.caste,
                token=self.token, signal=Signal.HOLD, confidence=0.05,
                metadata=self._analysis,
            )

        buy_score  = 0.0
        sell_score = 0.0

        # TVL trend
        if tvl_change > 0.05:
            buy_score  += 0.4
        elif tvl_change < -0.05:
            sell_score += 0.4
        elif tvl_change > 0.02:
            buy_score  += 0.15
        elif tvl_change < -0.02:
            sell_score += 0.15

        # Volume/TVL ratio — high activity is bullish confirmation
        if vol_tvl_ratio > 0.3:
            buy_score += 0.3
        elif vol_tvl_ratio > 0.1:
            buy_score += 0.1

        if buy_score > sell_score:
            signal     = Signal.BUY
            confidence = min(buy_score, 1.0)
        elif sell_score > buy_score:
            signal     = Signal.SELL
            confidence = min(sell_score, 1.0)
        else:
            signal     = Signal.HOLD
            confidence = 0.1

        return PheromoneSignal(
            agent_id   = self.agent_id,
            caste      = self.caste,
            token      = self.token,
            signal     = signal,
            confidence = confidence,
            metadata   = self._analysis,
        )
