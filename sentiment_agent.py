"""
agents/sentiment_agent.py — Sentiment from CoinGecko community/sentiment data
"""
import aiohttp
from loguru import logger

from base_agent import BaseAgent, PheromoneSignal, Signal
from settings import settings

COINGECKO_BASE = "https://api.coingecko.com/api/v3"


class SentimentAgent(BaseAgent):
    def __init__(self, token: str, search_terms: list):
        super().__init__(token=token, caste="sentiment")
        self.search_terms = search_terms
        self._analysis: dict = {}

    async def analyze(self) -> dict:
        try:
            headers = {}
            if settings.COINGECKO_API_KEY:
                headers["x-cg-demo-api-key"] = settings.COINGECKO_API_KEY

            # Search CoinGecko for the token by name
            query = self.search_terms[0] if self.search_terms else self.token
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{COINGECKO_BASE}/search",
                    params={"query": query},
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    search_data = await resp.json()

            coins = search_data.get("coins", [])
            # Find matching coin
            coin_id = None
            for c in coins[:5]:
                if c.get("symbol", "").upper() == self.token.upper():
                    coin_id = c.get("id")
                    break

            if not coin_id:
                self._analysis = {"sentiment_score": 0, "trending": False, "found": False}
                return self._analysis

            # Get sentiment votes
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{COINGECKO_BASE}/coins/{coin_id}",
                    params={"localization": "false", "tickers": "false",
                            "market_data": "true", "community_data": "true"},
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    detail = await resp.json()

            votes_up   = detail.get("sentiment_votes_up_percentage", 50) or 50
            votes_down = 100 - votes_up
            change_24h = detail.get("market_data", {}).get(
                "price_change_percentage_24h", 0) or 0

            self._analysis = {
                "sentiment_score": (votes_up - 50) / 50,  # -1 to +1
                "votes_up":        votes_up,
                "votes_down":      votes_down,
                "change_24h":      change_24h,
                "found":           True,
            }
            logger.info(
                f"[SENTIMENT:{self.agent_id}] {self.token} "
                f"up={votes_up:.0f}% change={change_24h:.1f}%"
            )

        except Exception as e:
            logger.warning(f"[SENTIMENT:{self.agent_id}] Failed: {e}")
            self._analysis = {"sentiment_score": 0, "trending": False, "found": False}
        return self._analysis

    async def emit(self) -> PheromoneSignal:
        score  = self._analysis.get("sentiment_score", 0)
        change = self._analysis.get("change_24h", 0)
        found  = self._analysis.get("found", False)

        if not found:
            return PheromoneSignal(self.agent_id, self.caste, self.token,
                Signal.HOLD, 0.05, metadata=self._analysis)

        buy_score = sell_score = 0.0

        if score > 0.2:    buy_score  += 0.5
        elif score > 0.05: buy_score  += 0.25
        elif score < -0.2: sell_score += 0.5
        elif score < -0.05:sell_score += 0.25

        if change > 3:     buy_score  += 0.3
        elif change < -3:  sell_score += 0.3

        if buy_score > sell_score:
            return PheromoneSignal(self.agent_id, self.caste, self.token,
                Signal.BUY,  min(buy_score, 1.0),  metadata=self._analysis)
        elif sell_score > buy_score:
            return PheromoneSignal(self.agent_id, self.caste, self.token,
                Signal.SELL, min(sell_score, 1.0), metadata=self._analysis)
        return PheromoneSignal(self.agent_id, self.caste, self.token,
            Signal.HOLD, 0.1, metadata=self._analysis)
