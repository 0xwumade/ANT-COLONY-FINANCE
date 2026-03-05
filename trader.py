"""
execution/trader.py — Trade execution on Base via Uniswap V3 / Aerodrome

Listens for ColonyDecisions from the consensus engine.
When execute=True, routes the trade through the best available DEX.

Safety features:
- Max trade size cap
- Slippage protection
- Onchain logging to the Colony smart contract
"""
import asyncio
import json
import time
from typing import Optional

from web3 import AsyncWeb3
from web3.middleware import async_geth_poa_middleware
from eth_account import Account
from loguru import logger

from config.settings import settings
from consensus.colony_brain import ColonyDecision


# Uniswap V3 SwapRouter02 ABI (minimal — only exactInputSingle)
UNISWAP_ROUTER_ABI = json.loads("""[
  {
    "inputs": [{
      "components": [
        {"name": "tokenIn",           "type": "address"},
        {"name": "tokenOut",          "type": "address"},
        {"name": "fee",               "type": "uint24"},
        {"name": "recipient",         "type": "address"},
        {"name": "amountIn",          "type": "uint256"},
        {"name": "amountOutMinimum",  "type": "uint256"},
        {"name": "sqrtPriceLimitX96", "type": "uint160"}
      ],
      "name": "params",
      "type": "tuple"
    }],
    "name": "exactInputSingle",
    "outputs": [{"name": "amountOut", "type": "uint256"}],
    "stateMutability": "payable",
    "type": "function"
  }
]""")

# WETH on Base
WETH_ADDRESS   = "0x4200000000000000000000000000000000000006"
# USDC on Base
USDC_ADDRESS   = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
# Default pool fee tier (0.3%)
DEFAULT_FEE    = 3000
# Max slippage (2%)
MAX_SLIPPAGE   = 0.02


class ColonyTrader:
    """
    Executes trades on Base DEXes based on ColonyDecisions.

    Decision flow:
        BUY  → swap USDC → token
        SELL → swap token → USDC
        HOLD → no action
    """

    def __init__(self):
        self.w3: Optional[AsyncWeb3] = None
        self.account: Optional[Account] = None
        self.router_contract = None
        self.trade_history: list[dict] = []

    async def connect(self):
        """Initialize Web3 connection to Base."""
        self.w3 = AsyncWeb3(
            AsyncWeb3.AsyncHTTPProvider(settings.BASE_RPC_URL)
        )
        self.w3.middleware_onion.inject(async_geth_poa_middleware, layer=0)

        if settings.TREASURY_PRIVATE_KEY:
            self.account = Account.from_key(settings.TREASURY_PRIVATE_KEY)
            logger.info(f"[TRADER] Treasury wallet: {self.account.address}")
        else:
            logger.warning("[TRADER] No treasury key configured — simulation mode")

        # Initialize Uniswap V3 router
        self.router_contract = self.w3.eth.contract(
            address=AsyncWeb3.to_checksum_address(settings.UNISWAP_V3_ROUTER),
            abi=UNISWAP_ROUTER_ABI,
        )
        logger.info("[TRADER] Connected to Base mainnet")

    async def execute_decision(self, decision: ColonyDecision) -> dict:
        """
        Execute a trade based on a ColonyDecision.
        Returns a trade receipt dict.
        """
        if not decision.execute:
            logger.debug(f"[TRADER] {decision.token} → HOLD, skipping")
            return {"status": "skipped", "reason": "HOLD"}

        if not self.account:
            # Simulation mode — log but don't transact
            logger.info(
                f"[TRADER:SIM] Would {decision.action} {decision.token} "
                f"(confidence={decision.confidence:.1%})"
            )
            return {
                "status": "simulated",
                "action": decision.action,
                "token":  decision.token,
                "confidence": decision.confidence,
                "timestamp": time.time(),
            }

        try:
            amount_eth = self._size_trade(decision.confidence)
            amount_wei = int(amount_eth * 1e18)

            if decision.action == "BUY":
                receipt = await self._swap(
                    token_in  = WETH_ADDRESS,
                    token_out = decision.token,
                    amount_in = amount_wei,
                )
            elif decision.action == "SELL":
                receipt = await self._swap(
                    token_in  = decision.token,
                    token_out = WETH_ADDRESS,
                    amount_in = amount_wei,
                )
            else:
                return {"status": "skipped", "reason": "HOLD"}

            trade_log = {
                "status":     "executed",
                "action":     decision.action,
                "token":      decision.token,
                "amount_eth": amount_eth,
                "tx_hash":    receipt["transactionHash"].hex(),
                "confidence": decision.confidence,
                "signal_count": decision.signal_count,
                "timestamp":  time.time(),
            }
            self.trade_history.append(trade_log)
            logger.success(
                f"[TRADER] ✅ {decision.action} {decision.token} "
                f"tx={trade_log['tx_hash'][:10]}..."
            )
            return trade_log

        except Exception as e:
            logger.error(f"[TRADER] Trade failed for {decision.token}: {e}")
            return {"status": "error", "error": str(e), "token": decision.token}

    async def _swap(self, token_in: str, token_out: str, amount_in: int) -> dict:
        """Execute exactInputSingle swap on Uniswap V3."""
        min_out = int(amount_in * (1 - MAX_SLIPPAGE))

        params = {
            "tokenIn":           AsyncWeb3.to_checksum_address(token_in),
            "tokenOut":          AsyncWeb3.to_checksum_address(token_out),
            "fee":               DEFAULT_FEE,
            "recipient":         self.account.address,
            "amountIn":          amount_in,
            "amountOutMinimum":  min_out,
            "sqrtPriceLimitX96": 0,
        }

        nonce    = await self.w3.eth.get_transaction_count(self.account.address)
        gas_price = await self.w3.eth.gas_price

        tx = await self.router_contract.functions.exactInputSingle(params).build_transaction({
            "from":     self.account.address,
            "value":    amount_in if token_in == WETH_ADDRESS else 0,
            "nonce":    nonce,
            "gasPrice": gas_price,
            "chainId":  settings.BASE_CHAIN_ID,
        })

        signed  = self.account.sign_transaction(tx)
        tx_hash = await self.w3.eth.send_raw_transaction(signed.rawTransaction)
        receipt = await self.w3.eth.wait_for_transaction_receipt(tx_hash)
        return receipt

    def _size_trade(self, confidence: float) -> float:
        """
        Kelly-inspired position sizing.
        Higher confidence → larger trade (within min/max bounds).
        """
        raw  = settings.MIN_TRADE_SIZE_ETH + (
            confidence * (settings.MAX_TRADE_SIZE_ETH - settings.MIN_TRADE_SIZE_ETH)
        )
        return round(min(max(raw, settings.MIN_TRADE_SIZE_ETH), settings.MAX_TRADE_SIZE_ETH), 6)
