"""
agents/arbitrage_agent.py — Price momentum and market gap signals via CoinGecko
"""
import aiohttp
from loguru import logger

from base_agent import BaseAgent, PheromoneSignal, Signal
from settings import settings

COINGECKO_BASE = "https://api.coingecko.com/api/v3"


class ArbitrageAgent(BaseAgent):
    """
    Caste: ARBITRAGE (weight: 0.15)

    Uses CoinGecko market data to detect:
    - Price vs 7d average gap → mean reversion opportunity
    - ATH distance → relative value signal
    - Bid/ask spread via ticker data
    """

    def __init__(self, token: str, token_address: str):
        super().__init__(token=token, caste="arbitrage")
        self.token_address = token_address.lower()
        self._analysis: dict = {}

    async def analyze(self) -> dict:
        try:
            headers = {}
            if settings.COINGECKO_API_KEY:
                headers["x-cg-demo-api-key"] = settings.COINGECKO_API_KEY

            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{COINGECKO_BASE}/coins/base/contract/{self.token_address}",
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    data = await resp.json()

            market = data.get("market_data", {})
            current_price = market.get("current_price", {}).get("usd", 0) or 0
            high_24h      = market.get("high_24h", {}).get("usd", 0) or 0
            low_24h       = market.get("low_24h", {}).get("usd", 0) or 0
            ath           = market.get("ath", {}).get("usd", 0) or 0
            change_7d     = market.get("price_change_percentage_7d", 0) or 0
            change_1h     = market.get("price_change_percentage_1h_in_currency", {}).get("usd", 0) or 0

            # Position within 24h range (0 = at low, 1 = at high)
            range_24h = high_24h - low_24h
            range_position = (current_price - low_24h) / range_24h if range_24h > 0 else 0.5

            # Distance from ATH (discount = potential upside)
            ath_discount = 1 - (current_price / ath) if ath > 0 else 0

            self._analysis = {
                "current_price":   current_price,
                "range_position":  range_position,
                "ath_discount":    ath_discount,
                "change_7d":       change_7d,
                "change_1h":       change_1h,
            }
            logger.info(
                f"[ARB:{self.agent_id}] {self.token} "
                f"range_pos={range_position:.2f} ath_disc={ath_discount:.2f} 7d={change_7d:.1f}%"
            )

        except Exception as e:
            logger.warning(f"[ARB:{self.agent_id}] Failed: {e}")
            self._analysis = {
                "current_price": 0, "range_position": 0.5,
                "ath_discount": 0, "change_7d": 0, "change_1h": 0,
            }
        return self._analysis

    async def emit(self) -> PheromoneSignal:
        pos    = self._analysis.get("range_position", 0.5)
        disc   = self._analysis.get("ath_discount", 0)
        c7d    = self._analysis.get("change_7d", 0)
        c1h    = self._analysis.get("change_1h", 0)

        if self._analysis.get("current_price", 0) == 0:
            return PheromoneSignal(self.agent_id, self.caste, self.token,
                Signal.HOLD, 0.05, metadata=self._analysis)

        buy_score = sell_score = 0.0

        # Near 24h low + oversold 7d = mean reversion buy
        if pos < 0.25 and c7d < -10:  buy_score  += 0.4
        elif pos < 0.3:               buy_score  += 0.2

        # Near 24h high + extended 7d = potential sell
        if pos > 0.75 and c7d > 20:   sell_score += 0.4
        elif pos > 0.7:               sell_score += 0.2

        # 1h momentum
        if c1h > 2:    buy_score  += 0.3
        elif c1h < -2: sell_score += 0.3

        # Deep ATH discount = value
        if disc > 0.8:   buy_score += 0.3
        elif disc > 0.5: buy_score += 0.1

        if buy_score > sell_score:
            return PheromoneSignal(self.agent_id, self.caste, self.token,
                Signal.BUY,  min(buy_score, 1.0),  metadata=self._analysis)
        elif sell_score > buy_score:
            return PheromoneSignal(self.agent_id, self.caste, self.token,
                Signal.SELL, min(sell_score, 1.0), metadata=self._analysis)
        return PheromoneSignal(self.agent_id, self.caste, self.token,
            Signal.HOLD, 0.1, metadata=self._analysis)
