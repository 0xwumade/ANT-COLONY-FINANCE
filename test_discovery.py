"""
tests/test_discovery.py — Unit tests for the DiscoveryAgent filters

Tests the safety filter logic without hitting real APIs,
using mock subgraph responses.
"""
import asyncio
import time
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from agents.discovery_agent import DiscoveryAgent, MIN_TVL_USD, MIN_POOL_AGE_DAYS


def make_pool(
    token1_symbol="NEWTOKEN",
    token1_address="0xNewToken",
    tvl=100_000,
    vol_today=50_000,
    vol_yesterday=30_000,
    age_days=5,
    paired_with="0x4200000000000000000000000000000000000006",  # WETH
):
    """Helper to build a fake Aerodrome pool response."""
    created = int(time.time() - age_days * 86400)
    return {
        "id": "0xPoolAddress",
        "token0": {"id": paired_with,     "symbol": "WETH", "name": "Wrapped Ether"},
        "token1": {"id": token1_address,  "symbol": token1_symbol, "name": token1_symbol},
        "totalValueLockedUSD": str(tvl),
        "volumeUSD": str(vol_today),
        "createdAtTimestamp": str(created),
        "poolDayData": [
            {"date": "today",     "volumeUSD": str(vol_today),     "tvlUSD": str(tvl)},
            {"date": "yesterday", "volumeUSD": str(vol_yesterday),  "tvlUSD": str(tvl)},
        ],
    }


def mock_subgraph_response(pools: list):
    return {"data": {"pools": pools}}


@pytest.fixture
def discovery():
    discovered = []
    async def collector(token): discovered.append(token)
    agent = DiscoveryAgent(on_new_token=collector)
    agent._discovered = discovered
    return agent


@pytest.mark.asyncio
async def test_passes_all_filters(discovery):
    pool = make_pool(tvl=200_000, vol_today=80_000, vol_yesterday=50_000, age_days=7)
    with patch("aiohttp.ClientSession") as mock_session:
        mock_resp = AsyncMock()
        mock_resp.json = AsyncMock(return_value=mock_subgraph_response([pool]))
        mock_session.return_value.__aenter__.return_value.post.return_value.__aenter__.return_value = mock_resp

        results = await discovery.scan()
    assert len(results) == 1
    assert results[0].symbol == "NEWTOKEN"


@pytest.mark.asyncio
async def test_rejects_low_tvl(discovery):
    pool = make_pool(tvl=5_000)   # below MIN_TVL_USD
    with patch("aiohttp.ClientSession") as mock_session:
        mock_resp = AsyncMock()
        mock_resp.json = AsyncMock(return_value=mock_subgraph_response([pool]))
        mock_session.return_value.__aenter__.return_value.post.return_value.__aenter__.return_value = mock_resp

        results = await discovery.scan()
    assert len(results) == 0


@pytest.mark.asyncio
async def test_rejects_new_pool(discovery):
    pool = make_pool(age_days=0.5)   # less than MIN_POOL_AGE_DAYS
    with patch("aiohttp.ClientSession") as mock_session:
        mock_resp = AsyncMock()
        mock_resp.json = AsyncMock(return_value=mock_subgraph_response([pool]))
        mock_session.return_value.__aenter__.return_value.post.return_value.__aenter__.return_value = mock_resp

        results = await discovery.scan()
    assert len(results) == 0


@pytest.mark.asyncio
async def test_rejects_no_volume_growth(discovery):
    pool = make_pool(vol_today=10_000, vol_yesterday=10_000)   # 0% growth
    with patch("aiohttp.ClientSession") as mock_session:
        mock_resp = AsyncMock()
        mock_resp.json = AsyncMock(return_value=mock_subgraph_response([pool]))
        mock_session.return_value.__aenter__.return_value.post.return_value.__aenter__.return_value = mock_resp

        results = await discovery.scan()
    assert len(results) == 0


@pytest.mark.asyncio
async def test_rejects_unsafe_quote_token(discovery):
    pool = make_pool(paired_with="0xSomeRandomToken")   # not WETH/USDC
    with patch("aiohttp.ClientSession") as mock_session:
        mock_resp = AsyncMock()
        mock_resp.json = AsyncMock(return_value=mock_subgraph_response([pool]))
        mock_session.return_value.__aenter__.return_value.post.return_value.__aenter__.return_value = mock_resp

        results = await discovery.scan()
    assert len(results) == 0


@pytest.mark.asyncio
async def test_skips_already_known_token(discovery):
    pool = make_pool(token1_address="0xKnownToken")
    discovery.seed_known(["0xKnownToken"])

    with patch("aiohttp.ClientSession") as mock_session:
        mock_resp = AsyncMock()
        mock_resp.json = AsyncMock(return_value=mock_subgraph_response([pool]))
        mock_session.return_value.__aenter__.return_value.post.return_value.__aenter__.return_value = mock_resp

        results = await discovery.scan()
    assert len(results) == 0


@pytest.mark.asyncio
async def test_volume_growth_calculated_correctly(discovery):
    # 50k → 80k = 60% growth → should pass
    pool = make_pool(vol_today=80_000, vol_yesterday=50_000, age_days=5, tvl=150_000)
    with patch("aiohttp.ClientSession") as mock_session:
        mock_resp = AsyncMock()
        mock_resp.json = AsyncMock(return_value=mock_subgraph_response([pool]))
        mock_session.return_value.__aenter__.return_value.post.return_value.__aenter__.return_value = mock_resp

        results = await discovery.scan()
    assert len(results) == 1
    assert abs(results[0].volume_growth - 0.60) < 0.01
