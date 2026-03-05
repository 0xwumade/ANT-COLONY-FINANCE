"""
agents/arbitrage_agent.py — Cross-DEX arbitrage opportunity detection

Compares token prices across Uniswap V3 and Aerodrome on Base.
Signals: profitable arb gap detected → BUY (on cheaper DEX).
"""
import asyncio
import aiohttp
from loguru import logger

from agents.base_agent import BaseAgent, PheromoneSignal, Signal
from config.settings import settings


# Uniswap V3 subgraph on Base
UNISWAP_SUBGRAPH  = "https://api.thegraph.com/subgraphs/name/uniswap/uniswap-v3-base"
# Aerodrome subgraph on Base
AERODROME_SUBGRAPH = "https://api.thegraph.com/subgraphs/name/aerodrome-finance/aerodrome"

PRICE_QUERY = """
query TokenPrice($token: String!) {
  token(id: $token) {
    symbol
    derivedETH
    tokenDayData(orderBy: date, orderDirection: desc, first: 1) {
      priceUSD
    }
  }
}
"""

# Minimum price gap (%) to trigger a signal
MIN_ARB_GAP = 0.005   # 0.5%
GAS_COST_USD = 0.10   # estimated Base gas cost per trade


class ArbitrageAgent(BaseAgent):
    """
    Caste: ARBITRAGE (weight: 0.15)

    Detects price discrepancies between DEXes.
    Higher gap = higher confidence signal.

    Note: Signals a BUY on the cheaper venue and implicitly SELL on the pricier.
    The execution layer handles routing.
    """

    def __init__(self, token: str, token_address: str):
        super().__init__(token=token, caste="arbitrage")
        self.token_address = token_address.lower()
        self._analysis: dict = {}

    async def _query_price(
        self, session: aiohttp.ClientSession, subgraph: str
    ) -> float:
        try:
            payload = {
                "query":     PRICE_QUERY,
                "variables": {"token": self.token_address},
            }
            async with session.post(subgraph, json=payload) as resp:
                data = await resp.json()
            token_data  = data.get("data", {}).get("token", {})
            day_data    = token_data.get("tokenDayData", [{}])
            price_str   = day_data[0].get("priceUSD", "0") if day_data else "0"
            return float(price_str)
        except Exception:
            return 0.0

    async def analyze(self) -> dict:
        try:
            async with aiohttp.ClientSession() as session:
                uniswap_price, aerodrome_price = await asyncio.gather(
                    self._query_price(session, UNISWAP_SUBGRAPH),
                    self._query_price(session, AERODROME_SUBGRAPH),
                )

            if uniswap_price == 0 or aerodrome_price == 0:
                self._analysis = {
                    "uniswap_price":  uniswap_price,
                    "aerodrome_price": aerodrome_price,
                    "gap_pct":        0.0,
                    "profitable":     False,
                    "cheaper_venue":  None,
                }
                return self._analysis

            gap_pct       = abs(uniswap_price - aerodrome_price) / min(uniswap_price, aerodrome_price)
            cheaper_venue = "uniswap" if uniswap_price < aerodrome_price else "aerodrome"

            # Check if gap exceeds gas costs (rough: gap * trade_size > gas)
            estimated_profit = gap_pct * settings.MIN_TRADE_SIZE_ETH * uniswap_price
            profitable = estimated_profit > GAS_COST_USD and gap_pct > MIN_ARB_GAP

            self._analysis = {
                "uniswap_price":   uniswap_price,
                "aerodrome_price": aerodrome_price,
                "gap_pct":         gap_pct,
                "profitable":      profitable,
                "cheaper_venue":   cheaper_venue,
                "estimated_profit_usd": estimated_profit,
            }
            logger.debug(
                f"[ARB:{self.agent_id}] {self.token} gap={gap_pct:.3%} "
                f"profitable={profitable} cheaper={cheaper_venue}"
            )

        except Exception as e:
            logger.warning(f"[ARB:{self.agent_id}] Analysis failed: {e}")
            self._analysis = {
                "uniswap_price": 0, "aerodrome_price": 0,
                "gap_pct": 0, "profitable": False, "cheaper_venue": None,
            }

        return self._analysis

    async def emit(self) -> PheromoneSignal:
        profitable = self._analysis.get("profitable", False)
        gap_pct    = self._analysis.get("gap_pct", 0)

        if profitable:
            # Confidence scales with gap size (max at 5% gap)
            confidence = min(gap_pct / 0.05, 1.0)
            signal     = Signal.BUY
        else:
            signal     = Signal.HOLD
            confidence = 0.05

        return PheromoneSignal(
            agent_id   = self.agent_id,
            caste      = self.caste,
            token      = self.token,
            signal     = signal,
            confidence = confidence,
            metadata   = self._analysis,
        )
