"""
tests/test_consensus.py — Unit tests for the ColonyBrain consensus engine
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock

from agents.base_agent import PheromoneSignal, Signal
from consensus.colony_brain import ColonyBrain, ColonyDecision


@pytest.fixture
def brain():
    b = ColonyBrain()
    b.redis = None   # no Redis needed for unit tests
    return b


def make_signal(caste, signal, confidence, token="BRETT"):
    return PheromoneSignal(
        agent_id=f"test-{caste}",
        caste=caste,
        token=token,
        signal=signal,
        confidence=confidence,
    )


@pytest.mark.asyncio
async def test_no_signals_returns_hold(brain):
    decision = await brain.aggregate("BRETT")
    assert decision.action == "HOLD"
    assert decision.execute == False
    assert decision.signal_count == 0


@pytest.mark.asyncio
async def test_strong_buy_consensus(brain):
    """All high-weight castes voting BUY should cross the threshold."""
    signals = [
        make_signal("whale",     Signal.BUY, 0.90),
        make_signal("liquidity", Signal.BUY, 0.85),
        make_signal("technical", Signal.BUY, 0.80),
        make_signal("arbitrage", Signal.BUY, 0.70),
        make_signal("sentiment", Signal.BUY, 0.60),
    ]
    for sig in signals:
        await brain.ingest_signal(sig)

    decision = await brain.aggregate("BRETT")
    assert decision.action == "BUY"
    assert decision.execute == True
    assert decision.confidence >= 0.65


@pytest.mark.asyncio
async def test_strong_sell_consensus(brain):
    """All high-weight castes voting SELL should trigger a SELL."""
    signals = [
        make_signal("whale",     Signal.SELL, 0.90),
        make_signal("liquidity", Signal.SELL, 0.85),
        make_signal("technical", Signal.SELL, 0.80),
        make_signal("sentiment", Signal.SELL, 0.70),
    ]
    for sig in signals:
        await brain.ingest_signal(sig)

    decision = await brain.aggregate("BRETT")
    assert decision.action == "SELL"
    assert decision.execute == True


@pytest.mark.asyncio
async def test_mixed_signals_hold(brain):
    """Conflicting signals should not cross threshold → HOLD."""
    signals = [
        make_signal("whale",     Signal.BUY,  0.60),
        make_signal("liquidity", Signal.SELL, 0.60),
        make_signal("technical", Signal.BUY,  0.50),
        make_signal("sentiment", Signal.SELL, 0.50),
    ]
    for sig in signals:
        await brain.ingest_signal(sig)

    decision = await brain.aggregate("BRETT")
    assert decision.execute == False


@pytest.mark.asyncio
async def test_caste_weights_respected(brain):
    """
    Whale (0.30) saying BUY with high confidence + 3 low-weight castes saying SELL
    should NOT trigger SELL, showing whale weight dominates.
    """
    signals = [
        make_signal("whale",     Signal.BUY,  0.95),   # weight 0.30 × 0.95 = 0.285
        make_signal("sentiment", Signal.SELL, 0.80),   # weight 0.10 × 0.80 = 0.080
        make_signal("sentiment", Signal.SELL, 0.80),   # (second sentiment agent)
        make_signal("arbitrage", Signal.SELL, 0.70),   # weight 0.15 × 0.70 = 0.105
    ]
    for sig in signals:
        await brain.ingest_signal(sig)

    decision = await brain.aggregate("BRETT")
    # Whale's BUY should dominate over noise
    assert decision.buy_score > decision.sell_score


@pytest.mark.asyncio
async def test_buffer_cleared_after_aggregate(brain):
    """Signal buffer should be empty after aggregation."""
    await brain.ingest_signal(make_signal("whale", Signal.BUY, 0.8))
    await brain.aggregate("BRETT")

    # Second aggregate should see no signals
    decision2 = await brain.aggregate("BRETT")
    assert decision2.signal_count == 0


@pytest.mark.asyncio
async def test_per_token_isolation(brain):
    """Signals for BRETT should not affect DEGEN decision."""
    await brain.ingest_signal(make_signal("whale", Signal.BUY, 0.95, token="BRETT"))
    await brain.ingest_signal(make_signal("whale", Signal.BUY, 0.95, token="BRETT"))
    await brain.ingest_signal(make_signal("whale", Signal.BUY, 0.95, token="BRETT"))

    decision_degen = await brain.aggregate("DEGEN")
    assert decision_degen.signal_count == 0
    assert decision_degen.execute == False
