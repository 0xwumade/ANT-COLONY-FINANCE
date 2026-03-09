"""
agents/whale_agent.py — Large holder signals via Basescan token transfers
"""
import aiohttp
from loguru import logger

from base_agent import BaseAgent, PheromoneSignal, Signal
from settings import settings

BASESCAN_API = "https://api.basescan.org/api"
COINGECKO_BASE = "https://api.coingecko.com/api/v3"


class WhaleAgent(BaseAgent):
    def __init__(self, token: str, token_address: str):
        super().__init__(token=token, caste="whale")
        self.token_address = token_address
        self._analysis: dict = {}

    async def analyze(self) -> dict:
        try:
            async with aiohttp.ClientSession() as session:
                params = {
                    "module":          "token",
                    "action":          "tokentx",
                    "contractaddress": self.token_address,
                    "sort":            "desc",
                    "offset":          50,
                    "apikey":          settings.BASESCAN_API_KEY or "YourApiKeyToken",
                }
                async with session.get(
                    BASESCAN_API, params=params,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    data = await resp.json()

            transfers = data.get("result", [])
            if not isinstance(transfers, list):
                transfers = []

            dex_routers = {
                settings.UNISWAP_V3_ROUTER.lower(),
                settings.AERODROME_ROUTER.lower(),
                "0x4752ba5dbc23f44d87826276bf6fd6b1c372ad24",  # Uniswap v2 base
            }

            buy_vol = sell_vol = 0.0
            for tx in transfers:
                try:
                    val = float(tx.get("value", 0)) / (10 ** int(tx.get("tokenDecimal", 18)))
                    if tx.get("from", "").lower() in dex_routers:
                        sell_vol += val
                    else:
                        buy_vol  += val
                except (ValueError, KeyError):
                    continue

            total = buy_vol + sell_vol or 1
            self._analysis = {
                "buy_volume":  buy_vol,
                "sell_volume": sell_vol,
                "net_flow":    buy_vol - sell_vol,
                "tx_count":    len(transfers),
                "buy_pct":     buy_vol / total,
            }
            logger.info(
                f"[WHALE:{self.agent_id}] {self.token} "
                f"txs={len(transfers)} buy={buy_vol:.0f} sell={sell_vol:.0f}"
            )

        except Exception as e:
            logger.warning(f"[WHALE:{self.agent_id}] Failed: {e}")
            self._analysis = {
                "buy_volume": 0, "sell_volume": 0,
                "net_flow": 0, "tx_count": 0, "buy_pct": 0.5,
            }
        return self._analysis

    async def emit(self) -> PheromoneSignal:
        net_flow = self._analysis.get("net_flow", 0)
        buy_pct  = self._analysis.get("buy_pct", 0.5)
        tx_count = self._analysis.get("tx_count", 0)

        if tx_count == 0:
            return PheromoneSignal(self.agent_id, self.caste, self.token,
                Signal.HOLD, 0.05, metadata=self._analysis)

        total = self._analysis.get("buy_volume", 1) + self._analysis.get("sell_volume", 1) or 1
        imbalance  = abs(net_flow) / total
        confidence = min(imbalance * 1.5, 1.0)

        if buy_pct > 0.6:
            return PheromoneSignal(self.agent_id, self.caste, self.token,
                Signal.BUY, confidence, metadata=self._analysis)
        elif buy_pct < 0.4:
            return PheromoneSignal(self.agent_id, self.caste, self.token,
                Signal.SELL, confidence, metadata=self._analysis)
        return PheromoneSignal(self.agent_id, self.caste, self.token,
            Signal.HOLD, 0.1, metadata=self._analysis)
