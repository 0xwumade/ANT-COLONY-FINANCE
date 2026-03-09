"""
agents/technical_agent.py — RSI, MACD, momentum from CoinGecko OHLCV
"""
import aiohttp
import numpy as np
from loguru import logger

from base_agent import BaseAgent, PheromoneSignal, Signal
from settings import settings

COINGECKO_BASE = "https://api.coingecko.com/api/v3"


def compute_rsi(prices: list, period: int = 14) -> float:
    if len(prices) < period + 1:
        return 50.0
    deltas   = np.diff(prices)
    gains    = np.where(deltas > 0, deltas, 0)
    losses   = np.where(deltas < 0, -deltas, 0)
    avg_gain = np.mean(gains[-period:])
    avg_loss = np.mean(losses[-period:]) or 1e-10
    return 100 - (100 / (1 + avg_gain / avg_loss))


def compute_macd(prices: list) -> tuple:
    if len(prices) < 26:
        return 0.0, 0.0
    def ema(arr, n):
        k, e = 2/(n+1), arr[0]
        for p in arr[1:]: e = p*k + e*(1-k)
        return e
    a = np.array(prices, dtype=float)
    macd = ema(a, 12) - ema(a, 26)
    return macd, ema(np.full(9, macd), 9)


class TechnicalAgent(BaseAgent):
    def __init__(self, token: str, coingecko_id: str):
        super().__init__(token=token, caste="technical")
        self.coingecko_id = coingecko_id
        self._analysis: dict = {}

    async def analyze(self) -> dict:
        try:
            headers = {}
            if settings.COINGECKO_API_KEY:
                headers["x-cg-demo-api-key"] = settings.COINGECKO_API_KEY

            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{COINGECKO_BASE}/coins/{self.coingecko_id}/ohlc",
                    params={"vs_currency": "usd", "days": "1"},
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    data = await resp.json()

            closes = [c[4] for c in data if len(c) == 5]
            if not closes:
                raise ValueError("No OHLC data returned")

            rsi       = compute_rsi(closes)
            macd, sig = compute_macd(closes)
            momentum  = (closes[-1] - closes[-12]) / closes[-12] if len(closes) >= 12 else 0.0

            self._analysis = {
                "rsi": rsi, "macd": macd, "macd_signal": sig,
                "momentum": momentum, "last_price": closes[-1],
            }
            logger.info(f"[TECHNICAL:{self.agent_id}] {self.token} RSI={rsi:.1f} momentum={momentum:.3f}")

        except Exception as e:
            logger.warning(f"[TECHNICAL:{self.agent_id}] Failed: {e}")
            self._analysis = {"rsi": 50, "macd": 0, "macd_signal": 0, "momentum": 0}
        return self._analysis

    async def emit(self) -> PheromoneSignal:
        rsi      = self._analysis.get("rsi", 50)
        macd     = self._analysis.get("macd", 0)
        macd_sig = self._analysis.get("macd_signal", 0)
        momentum = self._analysis.get("momentum", 0)

        buy_score = sell_score = 0.0

        if rsi < 30:    buy_score  += 0.4
        elif rsi > 70:  sell_score += 0.4
        elif rsi < 45:  buy_score  += 0.15
        elif rsi > 55:  sell_score += 0.15

        if macd > macd_sig:   buy_score  += 0.3
        elif macd < macd_sig: sell_score += 0.3

        if momentum > 0.02:    buy_score  += 0.3
        elif momentum < -0.02: sell_score += 0.3

        if buy_score > sell_score:
            return PheromoneSignal(self.agent_id, self.caste, self.token,
                Signal.BUY,  min(buy_score, 1.0),  metadata=self._analysis)
        elif sell_score > buy_score:
            return PheromoneSignal(self.agent_id, self.caste, self.token,
                Signal.SELL, min(sell_score, 1.0), metadata=self._analysis)
        return PheromoneSignal(self.agent_id, self.caste, self.token,
            Signal.HOLD, 0.1, metadata=self._analysis)
