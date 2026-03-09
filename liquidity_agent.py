"""
agents/liquidity_agent.py — TVL and volume signals via DeFiLlama (free, no key)
"""
import aiohttp
from loguru import logger

from base_agent import BaseAgent, PheromoneSignal, Signal
from settings import settings

DEFILLAMA_TVL  = "https://api.llama.fi/v2/historicalChainTvl/Base"
COINGECKO_BASE = "https://api.coingecko.com/api/v3"


class LiquidityAgent(BaseAgent):
    def __init__(self, token: str, token_address: str):
        super().__init__(token=token, caste="liquidity")
        self.token_address = token_address.lower()
        self._analysis: dict = {}

    async def analyze(self) -> dict:
        try:
            headers = {}
            if settings.COINGECKO_API_KEY:
                headers["x-cg-demo-api-key"] = settings.COINGECKO_API_KEY

            async with aiohttp.ClientSession() as session:
                # Get 7-day market data from CoinGecko for this token
                # Map address to coingecko via contract lookup
                async with session.get(
                    f"{COINGECKO_BASE}/coins/base/contract/{self.token_address}",
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    data = await resp.json()

            market = data.get("market_data", {})
            total_volume  = market.get("total_volume", {}).get("usd", 0) or 0
            market_cap    = market.get("market_cap", {}).get("usd", 0) or 0
            price_change  = market.get("price_change_percentage_24h", 0) or 0

            # Volume/mcap ratio as liquidity health proxy
            vol_mcap_ratio = total_volume / market_cap if market_cap > 0 else 0

            self._analysis = {
                "total_volume":   total_volume,
                "market_cap":     market_cap,
                "price_change_24h": price_change,
                "vol_mcap_ratio": vol_mcap_ratio,
            }
            logger.info(
                f"[LIQUIDITY:{self.agent_id}] {self.token} "
                f"vol=${total_volume:,.0f} vol/mcap={vol_mcap_ratio:.3f} change={price_change:.1f}%"
            )

        except Exception as e:
            logger.warning(f"[LIQUIDITY:{self.agent_id}] Failed: {e}")
            self._analysis = {
                "total_volume": 0, "market_cap": 0,
                "price_change_24h": 0, "vol_mcap_ratio": 0,
            }
        return self._analysis

    async def emit(self) -> PheromoneSignal:
        vol_mcap  = self._analysis.get("vol_mcap_ratio", 0)
        change    = self._analysis.get("price_change_24h", 0)
        volume    = self._analysis.get("total_volume", 0)

        if volume < 1000:
            return PheromoneSignal(self.agent_id, self.caste, self.token,
                Signal.HOLD, 0.05, metadata=self._analysis)

        buy_score = sell_score = 0.0

        # High volume/mcap = active liquidity = bullish
        if vol_mcap > 0.3:   buy_score  += 0.35
        elif vol_mcap > 0.1: buy_score  += 0.15

        # 24h price change momentum
        if change > 5:        buy_score  += 0.35
        elif change > 2:      buy_score  += 0.15
        elif change < -5:     sell_score += 0.35
        elif change < -2:     sell_score += 0.15

        if buy_score > sell_score:
            return PheromoneSignal(self.agent_id, self.caste, self.token,
                Signal.BUY,  min(buy_score, 1.0),  metadata=self._analysis)
        elif sell_score > buy_score:
            return PheromoneSignal(self.agent_id, self.caste, self.token,
                Signal.SELL, min(sell_score, 1.0), metadata=self._analysis)
        return PheromoneSignal(self.agent_id, self.caste, self.token,
            Signal.HOLD, 0.1, metadata=self._analysis)
