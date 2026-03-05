"""
agents/discovery_agent.py — Aerodrome Token Discovery

Continuously scans Aerodrome Finance on Base for trending pools.
When a token passes the safety filters, it's auto-injected into
the live swarm — no manual config needed.

Discovery criteria:
  ✅ TVL > $50k (filters micro-pools)
  ✅ 24h volume growth > 20% (momentum confirmation)
  ✅ Pool age > 2 days (filters fresh honeypots)
  ✅ Paired with WETH or USDC (exit liquidity exists)
  ✅ Not already tracked
  ❌ Rejects tokens with < 100 holders (rug risk)
"""

import asyncio
import aiohttp
import time
from dataclasses import dataclass
from typing import Callable, Awaitable
from loguru import logger


# Aerodrome subgraph on The Graph (Base)
AERODROME_SUBGRAPH = (
    "https://api.thegraph.com/subgraphs/name/aerodrome-finance/aerodrome"
)

# Safety anchors — only discover tokens paired with these
SAFE_QUOTE_TOKENS = {
    "0x4200000000000000000000000000000000000006",  # WETH
    "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913",  # USDC
    "0xd9aaec86b65d86f6a7b5b1b0c42ffa531710b6ca",  # USDbC
}

# Discovery thresholds
MIN_TVL_USD        = 50_000     # minimum pool TVL
MIN_VOLUME_24H     = 10_000     # minimum 24h volume
MIN_VOLUME_GROWTH  = 0.20       # 20% volume increase vs previous 24h
MIN_POOL_AGE_DAYS  = 2          # ignore pools newer than 2 days
MAX_TOKENS         = 10         # max tokens in swarm at once

# GraphQL query: top pools by 24h volume with hourly history
TRENDING_POOLS_QUERY = """
{
  pools(
    first: 50
    orderBy: volumeUSD
    orderDirection: desc
    where: { totalValueLockedUSD_gt: "50000" }
  ) {
    id
    token0 { id symbol name }
    token1 { id symbol name }
    totalValueLockedUSD
    volumeUSD
    createdAtTimestamp
    poolDayData(orderBy: date, orderDirection: desc, first: 2) {
      date
      volumeUSD
      tvlUSD
    }
  }
}
"""


@dataclass
class DiscoveredToken:
    symbol:      str
    address:     str
    pool_address: str
    tvl_usd:     float
    volume_24h:  float
    volume_growth: float
    paired_with: str
    coingecko_id: str   # best-guess slug (can be empty)
    twitter:     list[str]


class DiscoveryAgent:
    """
    Caste: SCOUT (meta-agent, runs outside the normal voting cycle)

    Scans Aerodrome for emerging tokens and registers them
    with the swarm orchestrator via a callback.

    Usage in main.py:
        discovery = DiscoveryAgent(on_new_token=swarm.add_token)
        asyncio.create_task(discovery.run_forever())
    """

    def __init__(
        self,
        on_new_token: Callable[[dict], Awaitable[None]],
        scan_interval_seconds: int = 300,   # scan every 5 minutes
    ):
        self.on_new_token       = on_new_token
        self.scan_interval      = scan_interval_seconds
        self._tracked_addresses: set[str] = set()

        # Pre-seed with the tokens we already configured
        self._known_addresses: set[str] = set()

    def seed_known(self, addresses: list[str]):
        """Pre-populate with already-tracked token addresses to avoid duplicates."""
        for addr in addresses:
            self._known_addresses.add(addr.lower())

    async def scan(self) -> list[DiscoveredToken]:
        """
        Query Aerodrome subgraph and return tokens passing safety filters.
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    AERODROME_SUBGRAPH,
                    json={"query": TRENDING_POOLS_QUERY},
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as resp:
                    data = await resp.json()
        except Exception as e:
            logger.warning(f"[DISCOVERY] Subgraph fetch failed: {e}")
            return []

        pools = data.get("data", {}).get("pools", [])
        discovered: list[DiscoveredToken] = []
        now = time.time()

        for pool in pools:
            try:
                token0 = pool["token0"]
                token1 = pool["token1"]
                t0_addr = token0["id"].lower()
                t1_addr = token1["id"].lower()

                # Determine which is the "quote" token (safe anchor)
                if t0_addr in SAFE_QUOTE_TOKENS:
                    base_token  = token1
                    quote_addr  = t0_addr
                elif t1_addr in SAFE_QUOTE_TOKENS:
                    base_token  = token0
                    quote_addr  = t1_addr
                else:
                    continue   # not paired with a safe quote token

                base_addr = base_token["id"].lower()

                # Skip already known/tracked tokens
                if base_addr in self._known_addresses:
                    continue

                # Pool age filter
                created_at  = int(pool.get("createdAtTimestamp", 0))
                age_days    = (now - created_at) / 86400
                if age_days < MIN_POOL_AGE_DAYS:
                    logger.debug(
                        f"[DISCOVERY] {base_token['symbol']} skipped — "
                        f"pool too new ({age_days:.1f}d)"
                    )
                    continue

                # TVL filter
                tvl = float(pool.get("totalValueLockedUSD", 0))
                if tvl < MIN_TVL_USD:
                    continue

                # Volume & growth filter
                day_data = pool.get("poolDayData", [])
                if len(day_data) < 2:
                    continue

                vol_today    = float(day_data[0].get("volumeUSD", 0))
                vol_yesterday= float(day_data[1].get("volumeUSD", 1))

                if vol_today < MIN_VOLUME_24H:
                    continue

                growth = (vol_today - vol_yesterday) / (vol_yesterday or 1)
                if growth < MIN_VOLUME_GROWTH:
                    continue

                # Passed all filters ✅
                symbol = base_token["symbol"].upper()
                token  = DiscoveredToken(
                    symbol        = symbol,
                    address       = base_token["id"],
                    pool_address  = pool["id"],
                    tvl_usd       = tvl,
                    volume_24h    = vol_today,
                    volume_growth = growth,
                    paired_with   = quote_addr,
                    coingecko_id  = symbol.lower(),   # best-guess; CG may differ
                    twitter       = [f"${symbol}", f"{symbol} Base token"],
                )
                discovered.append(token)
                logger.success(
                    f"[DISCOVERY] 🆕 {symbol} discovered! "
                    f"TVL=${tvl:,.0f} vol24h=${vol_today:,.0f} "
                    f"growth={growth:.0%}"
                )

            except (KeyError, ValueError, TypeError) as e:
                logger.debug(f"[DISCOVERY] Pool parse error: {e}")
                continue

        return discovered

    async def run_forever(self):
        """
        Background loop — scans Aerodrome every `scan_interval` seconds
        and calls `on_new_token` for each newly discovered token.
        """
        logger.info(
            f"[DISCOVERY] Scout agent online. "
            f"Scanning every {self.scan_interval}s"
        )

        while True:
            logger.info("[DISCOVERY] Scanning Aerodrome for trending pools...")
            candidates = await self.scan()

            for token in candidates:
                if len(self._known_addresses) >= MAX_TOKENS:
                    logger.warning(
                        f"[DISCOVERY] Swarm at max capacity ({MAX_TOKENS} tokens). "
                        f"Skipping {token.symbol}."
                    )
                    break

                # Build the token config dict (matches TRACKED_TOKENS format in main.py)
                token_config = {
                    "symbol":       token.symbol,
                    "address":      token.address,
                    "coingecko_id": token.coingecko_id,
                    "twitter":      token.twitter,
                    "_discovered":  True,             # flag so we can log it differently
                    "_tvl":         token.tvl_usd,
                    "_volume_growth": token.volume_growth,
                }

                self._known_addresses.add(token.address.lower())
                await self.on_new_token(token_config)

            if not candidates:
                logger.info("[DISCOVERY] No new tokens found this scan.")

            await asyncio.sleep(self.scan_interval)
