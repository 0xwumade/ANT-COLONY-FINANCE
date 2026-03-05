"""
execution/trader.py — Trade execution via Coinbase CDP Swap API

Replaces direct Uniswap V3 calls with the CDP Swap API.

Why CDP Swap API vs raw web3.py:
  ✅ Handles token approvals automatically
  ✅ Sources best pricing across 130+ exchanges via 0x
  ✅ Built-in slippage protection
  ✅ Qualifies project for CDP Builder Grant
  ✅ Sub-500ms latency, no infrastructure to manage
  ✅ Single call: quote → sign → broadcast

Docs: https://docs.cdp.coinbase.com/trade-api/quickstart
"""
import time
from typing import Optional
from loguru import logger

from cdp import CdpClient
from settings import settings
from colony_brain import ColonyDecision


# Base token addresses
WETH_ADDRESS = "0x4200000000000000000000000000000000000006"
USDC_ADDRESS = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"

# CDP Swap slippage: 100 bps = 1%
SLIPPAGE_BPS = 100


class ColonyTrader:
    """
    Executes swaps on Base via the Coinbase CDP Swap API.

    Decision flow:
        BUY  -> swap USDC -> token   (colony is accumulating)
        SELL -> swap token -> USDC   (colony is exiting)
        HOLD -> no action

    CDP Swap API handles:
        - Token approval transactions
        - Route optimisation across DEXes
        - Transaction signing & broadcasting
        - Gas estimation and optimisation
    """

    def __init__(self):
        self._cdp     = None
        self._account = None
        self.simulate: bool = not bool(settings.CDP_API_KEY_NAME)
        self.trade_history: list[dict] = []

    async def connect(self):
        """
        Initialise the CDP client and load (or create) the treasury account.
        The treasury account is a CDP EVM account managed inside a TEE.
        """
        if self.simulate:
            logger.warning(
                "[TRADER] No CDP API key configured — running in simulation mode. "
                "Set CDP_API_KEY_NAME and CDP_API_KEY_PRIVATE_KEY in .env to go live."
            )
            return

        try:
            self._cdp = CdpClient(
                api_key_id     = settings.CDP_API_KEY_NAME,
                api_key_secret = settings.CDP_API_KEY_PRIVATE_KEY,
            )

            # get_or_create_account is idempotent — safe to call every startup
            self._account = await self._cdp.evm.get_or_create_account(
                name="AntColonyTreasury"
            )
            logger.success(
                f"[TRADER] CDP treasury account ready: {self._account.address}"
            )

        except Exception as e:
            logger.error(f"[TRADER] CDP connect failed: {e}. Falling back to simulation.")
            self.simulate = True

    async def execute_decision(self, decision: ColonyDecision) -> dict:
        """
        Execute a trade based on a ColonyDecision.
        Returns a trade receipt dict.
        """
        if not decision.execute:
            logger.debug(f"[TRADER] {decision.token} -> HOLD, skipping")
            return {"status": "skipped", "reason": "HOLD"}

        if self.simulate:
            return self._simulate(decision)

        try:
            if decision.action == "BUY":
                from_token  = USDC_ADDRESS
                to_token    = decision.token
                amount_usdc = self._size_trade_usdc(decision.confidence)
                # USDC has 6 decimals
                from_amount = str(int(amount_usdc * 1_000_000))

            elif decision.action == "SELL":
                from_token  = decision.token
                to_token    = USDC_ADDRESS
                # Token decimals vary — use ETH-equivalent sizing
                from_amount = str(int(self._size_trade_eth(decision.confidence) * 1e18))
            else:
                return {"status": "skipped", "reason": "HOLD"}

            trade_log = await self._cdp_swap(
                from_token  = from_token,
                to_token    = to_token,
                from_amount = from_amount,
                decision    = decision,
            )
            self.trade_history.append(trade_log)
            return trade_log

        except Exception as e:
            logger.error(f"[TRADER] Trade failed for {decision.token}: {e}")
            return {"status": "error", "error": str(e), "token": decision.token}

    async def _cdp_swap(
        self,
        from_token:  str,
        to_token:    str,
        from_amount: str,
        decision:    ColonyDecision,
    ) -> dict:
        """
        Execute a swap via CDP Swap API.

        Step 1: quote_swap() — gets best route, checks liquidity
        Step 2: swap_quote.execute() — signs + broadcasts onchain
        """
        # Step 1: Get swap quote
        swap_quote = await self._account.quote_swap(
            from_token   = from_token,
            to_token     = to_token,
            from_amount  = from_amount,
            network      = "base",
            slippage_bps = SLIPPAGE_BPS,
        )

        if not swap_quote.liquidity_available:
            logger.warning(
                f"[TRADER] Insufficient liquidity for {decision.action} "
                f"{decision.token} — skipping"
            )
            return {
                "status": "skipped",
                "reason": "insufficient_liquidity",
                "token":  decision.token,
            }

        logger.info(
            f"[TRADER] Quote: {decision.action} {decision.token} "
            f"in={from_amount} out~{swap_quote.to_amount} "
            f"(slippage={SLIPPAGE_BPS / 100:.1f}%)"
        )

        # Step 2: Execute the swap — CDP handles approvals + signing + broadcast
        result = await swap_quote.execute()

        trade_log = {
            "status":       "executed",
            "action":       decision.action,
            "token":        decision.token,
            "from_amount":  from_amount,
            "to_amount":    swap_quote.to_amount,
            "tx_hash":      result.transaction_hash,
            "confidence":   decision.confidence,
            "signal_count": decision.signal_count,
            "timestamp":    time.time(),
            "via":          "cdp_swap_api",
        }

        logger.success(
            f"[TRADER] EXECUTED {decision.action} {decision.token} "
            f"tx={result.transaction_hash[:12]}..."
        )
        return trade_log

    def _simulate(self, decision: ColonyDecision) -> dict:
        """Log a simulated trade without hitting any API."""
        amount = self._size_trade_usdc(decision.confidence)
        logger.info(
            f"[TRADER:SIM] Would {decision.action} {decision.token} "
            f"~${amount:.2f} USDC (confidence={decision.confidence:.1%})"
        )
        return {
            "status":     "simulated",
            "action":     decision.action,
            "token":      decision.token,
            "amount_usd": amount,
            "confidence": decision.confidence,
            "timestamp":  time.time(),
        }

    def _size_trade_usdc(self, confidence: float) -> float:
        """Kelly-inspired sizing in USDC. Scales with confidence."""
        min_usd = settings.MIN_TRADE_SIZE_ETH * 3000
        max_usd = settings.MAX_TRADE_SIZE_ETH * 3000
        raw     = min_usd + confidence * (max_usd - min_usd)
        return round(min(max(raw, min_usd), max_usd), 2)

    def _size_trade_eth(self, confidence: float) -> float:
        """ETH-denominated size for SELL orders."""
        raw = settings.MIN_TRADE_SIZE_ETH + (
            confidence * (settings.MAX_TRADE_SIZE_ETH - settings.MIN_TRADE_SIZE_ETH)
        )
        return round(min(max(raw, settings.MIN_TRADE_SIZE_ETH), settings.MAX_TRADE_SIZE_ETH), 6)
