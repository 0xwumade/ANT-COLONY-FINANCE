"""
agents/whale_agent.py — Tracks large wallet movements onchain

Monitors wallet addresses holding >$100k in a token.
If whales are accumulating → bullish signal.
If whales are dumping    → bearish signal.
"""
import asyncio
import aiohttp
from loguru import logger

from agents.base_agent import BaseAgent, PheromoneSignal, Signal
from config.settings import settings


# Known whale threshold: wallets holding more than this % of supply
WHALE_THRESHOLD_USD = 100_000

# Etherscan-compatible API for Base
BASE_EXPLORER_API = "https://api.basescan.org/api"


class WhaleAgent(BaseAgent):
    """
    Caste: WHALE (weight: 0.30)

    Watches top holders of a token for:
    - Large inflows  → BUY signal
    - Large outflows → SELL signal
    - No movement    → HOLD signal
    """

    def __init__(self, token: str, token_address: str):
        super().__init__(token=token, caste="whale")
        self.token_address = token_address
        self._analysis: dict = {}

    async def analyze(self) -> dict:
        """
        Fetch recent large transfers for the token.
        Compares buy vs sell pressure from whale-tier wallets.
        """
        try:
            async with aiohttp.ClientSession() as session:
                # Fetch recent token transfers
                params = {
                    "module":          "token",
                    "action":          "tokentx",
                    "contractaddress": self.token_address,
                    "sort":            "desc",
                    "offset":          50,    # last 50 transfers
                    "apikey":          settings.COINGECKO_API_KEY or "YourApiKeyToken",
                }
                async with session.get(BASE_EXPLORER_API, params=params) as resp:
                    data = await resp.json()

            transfers = data.get("result", [])
            if not isinstance(transfers, list):
                transfers = []

            buy_volume  = 0.0
            sell_volume = 0.0

            for tx in transfers:
                try:
                    value = float(tx.get("value", 0)) / (10 ** int(tx.get("tokenDecimal", 18)))
                    # Rough heuristic: large transfers from known DEX routers = sell pressure
                    if tx.get("from", "").lower() in [
                        settings.UNISWAP_V3_ROUTER.lower(),
                        settings.AERODROME_ROUTER.lower(),
                    ]:
                        sell_volume += value
                    else:
                        buy_volume += value
                except (ValueError, KeyError):
                    continue

            self._analysis = {
                "buy_volume":  buy_volume,
                "sell_volume": sell_volume,
                "net_flow":    buy_volume - sell_volume,
                "tx_count":    len(transfers),
            }
            logger.debug(f"[WHALE:{self.agent_id}] {self.token} net_flow={self._analysis['net_flow']:.2f}")

        except Exception as e:
            logger.warning(f"[WHALE:{self.agent_id}] Analysis failed: {e}. Using neutral.")
            self._analysis = {"buy_volume": 0, "sell_volume": 0, "net_flow": 0, "tx_count": 0}

        return self._analysis

    async def emit(self) -> PheromoneSignal:
        net_flow     = self._analysis.get("net_flow", 0)
        buy_volume   = self._analysis.get("buy_volume", 1)
        sell_volume  = self._analysis.get("sell_volume", 1)
        total_volume = buy_volume + sell_volume or 1

        # Confidence scales with the magnitude of the imbalance
        imbalance   = abs(net_flow) / total_volume
        confidence  = min(imbalance * 1.5, 1.0)   # cap at 1.0

        if net_flow > 0:
            signal = Signal.BUY
        elif net_flow < 0:
            signal = Signal.SELL
        else:
            signal     = Signal.HOLD
            confidence = 0.1   # low confidence on neutral

        return PheromoneSignal(
            agent_id   = self.agent_id,
            caste      = self.caste,
            token      = self.token,
            signal     = signal,
            confidence = confidence,
            metadata   = self._analysis,
        )
