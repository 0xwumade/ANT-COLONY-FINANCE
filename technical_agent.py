"""
agents/technical_agent.py — Technical indicator analysis

Computes RSI, MACD, and price momentum from OHLCV data.
"""
import asyncio
import aiohttp
import numpy as np
from loguru import logger

from base_agent import BaseAgent, PheromoneSignal, Signal
from settings import settings


COINGECKO_BASE = "https://api.coingecko.com/api/v3"


def compute_rsi(prices: list[float], period: int = 14) -> float:
    """Standard RSI calculation."""
    if len(prices) < period + 1:
        return 50.0   # neutral if not enough data
    deltas = np.diff(prices)
    gains  = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)
    avg_gain = np.mean(gains[-period:])
    avg_loss = np.mean(losses[-period:]) or 1e-10
    rs  = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def compute_macd(prices: list[float]) -> tuple[float, float]:
    """Returns (MACD line, signal line)."""
    if len(prices) < 26:
        return 0.0, 0.0
    prices_arr = np.array(prices)
    ema12 = _ema(prices_arr, 12)
    ema26 = _ema(prices_arr, 26)
    macd_line   = ema12 - ema26
    signal_line = _ema(np.array([macd_line] * 9), 9)  # simplified
    return float(macd_line), float(signal_line)


def _ema(prices: np.ndarray, period: int) -> float:
    k = 2 / (period + 1)
    ema = prices[0]
    for p in prices[1:]:
        ema = p * k + ema * (1 - k)
    return ema


class TechnicalAgent(BaseAgent):
    """
    Caste: TECHNICAL (weight: 0.20)

    Signals from:
    - RSI < 30  → oversold → BUY
    - RSI > 70  → overbought → SELL
    - MACD crossover → BUY/SELL
    - Price momentum (5m vs 1h) → directional bias
    """

    def __init__(self, token: str, coingecko_id: str):
        super().__init__(token=token, caste="technical")
        self.coingecko_id = coingecko_id
        self._prices: list[float] = []
        self._analysis: dict = {}

    async def analyze(self) -> dict:
        try:
            async with aiohttp.ClientSession() as session:
                headers = {}
                if settings.COINGECKO_API_KEY:
                    headers["x-cg-demo-api-key"] = settings.COINGECKO_API_KEY

                url = f"{COINGECKO_BASE}/coins/{self.coingecko_id}/ohlc"
                params = {"vs_currency": "usd", "days": "1"}
                async with session.get(url, params=params, headers=headers) as resp:
                    data = await resp.json()

            # data is list of [timestamp, open, high, low, close]
            closes = [candle[4] for candle in data if len(candle) == 5]
            self._prices = closes

            rsi            = compute_rsi(closes)
            macd, signal   = compute_macd(closes)

            # Price momentum: compare last price to 12 candles ago (~1h on 5m chart)
            momentum = 0.0
            if len(closes) >= 12:
                momentum = (closes[-1] - closes[-12]) / closes[-12]

            self._analysis = {
                "rsi":       rsi,
                "macd":      macd,
                "macd_signal": signal,
                "momentum":  momentum,
                "last_price": closes[-1] if closes else 0,
            }
            logger.debug(f"[TECHNICAL:{self.agent_id}] RSI={rsi:.1f} MACD={macd:.4f} momentum={momentum:.3f}")

        except Exception as e:
            logger.warning(f"[TECHNICAL:{self.agent_id}] Analysis failed: {e}")
            self._analysis = {"rsi": 50, "macd": 0, "macd_signal": 0, "momentum": 0}

        return self._analysis

    async def emit(self) -> PheromoneSignal:
        rsi      = self._analysis.get("rsi", 50)
        macd     = self._analysis.get("macd", 0)
        macd_sig = self._analysis.get("macd_signal", 0)
        momentum = self._analysis.get("momentum", 0)

        buy_score  = 0.0
        sell_score = 0.0

        # RSI signals
        if rsi < 30:
            buy_score  += 0.4
        elif rsi > 70:
            sell_score += 0.4
        elif rsi < 45:
            buy_score  += 0.15
        elif rsi > 55:
            sell_score += 0.15

        # MACD crossover
        if macd > macd_sig:
            buy_score  += 0.3
        elif macd < macd_sig:
            sell_score += 0.3

        # Momentum
        if momentum > 0.02:
            buy_score  += 0.3
        elif momentum < -0.02:
            sell_score += 0.3

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
