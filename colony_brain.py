"""
consensus/colony_brain.py — Weighted Quorum Consensus Engine

This is the heart of the ant colony. It:
1. Collects PheromoneSignals from all agents
2. Aggregates them by caste weight × confidence
3. Emits a ColonyDecision when threshold is crossed
4. Publishes results to Redis for the execution layer

"Pheromone trails" metaphor:
- Strong signals reinforce the trail
- Weak/conflicting signals fade out
- When the trail is strong enough → the colony acts
"""
import asyncio
import json
import time
from dataclasses import dataclass, asdict
from typing import Optional

import redis.asyncio as aioredis
from loguru import logger

from base_agent import PheromoneSignal, Signal
from settings import settings


@dataclass
class ColonyDecision:
    """Output of consensus — what the colony decided to do."""
    token:           str
    action:          str          # "BUY" | "SELL" | "HOLD"
    confidence:      float        # 0.0 → 1.0
    buy_score:       float
    sell_score:      float
    hold_score:      float
    signal_count:    int
    caste_breakdown: dict         # per-caste weighted scores
    timestamp:       float
    execute:         bool         # True if threshold crossed


REDIS_DECISIONS_KEY   = "colony:decisions"
REDIS_SIGNALS_KEY     = "colony:signals:{token}"
REDIS_PHEROMONE_KEY   = "colony:pheromone:{token}"


class ColonyBrain:
    """
    Aggregates swarm signals using weighted quorum consensus.

    Consensus formula:
        weighted_score = Σ (caste_weight × signal_confidence × direction)
        direction: +1 for BUY, -1 for SELL, 0 for HOLD

        If weighted_score > threshold → BUY
        If weighted_score < -threshold → SELL
        Otherwise → HOLD

    Caste weights (from config):
        whale:      0.30
        liquidity:  0.25
        technical:  0.20
        arbitrage:  0.15
        sentiment:  0.10
    """

    def __init__(self):
        self.redis: Optional[aioredis.Redis] = None
        self.caste_weights = settings.CASTE_WEIGHTS
        self.threshold     = settings.CONSENSUS_THRESHOLD
        self._signal_buffer: dict[str, list[PheromoneSignal]] = {}

    async def connect(self):
        self.redis = await aioredis.from_url(settings.REDIS_URL, db=settings.REDIS_DB)
        logger.info("ColonyBrain connected to Redis")

    async def ingest_signal(self, signal: PheromoneSignal):
        """Accept a signal from an agent and store in Redis."""
        token = signal.token
        key   = REDIS_SIGNALS_KEY.format(token=token)

        # Serialize and store in Redis list (with TTL = signal window)
        payload = json.dumps({
            "agent_id":   signal.agent_id,
            "caste":      signal.caste,
            "signal":     signal.signal.value,
            "confidence": signal.confidence,
            "timestamp":  time.time(),
        })
        if self.redis:
            await self.redis.rpush(key, payload)
            await self.redis.expire(key, settings.SIGNAL_WINDOW_SECONDS * 2)

        # Also buffer in-memory for immediate aggregation
        if token not in self._signal_buffer:
            self._signal_buffer[token] = []
        self._signal_buffer[token].append(signal)

    async def aggregate(self, token: str) -> ColonyDecision:
        """
        Run weighted quorum consensus on all buffered signals for a token.
        """
        signals = self._signal_buffer.get(token, [])

        if not signals:
            return ColonyDecision(
                token=token, action="HOLD", confidence=0.0,
                buy_score=0.0, sell_score=0.0, hold_score=0.0,
                signal_count=0, caste_breakdown={},
                timestamp=time.time(), execute=False,
            )

        # Per-caste accumulation
        caste_scores: dict[str, dict] = {
            caste: {"buy": 0.0, "sell": 0.0, "hold": 0.0, "count": 0}
            for caste in self.caste_weights
        }

        for sig in signals:
            caste  = sig.caste
            weight = self.caste_weights.get(caste, 0.1)
            score  = sig.confidence * weight

            if caste not in caste_scores:
                caste_scores[caste] = {"buy": 0.0, "sell": 0.0, "hold": 0.0, "count": 0}

            if sig.signal == Signal.BUY:
                caste_scores[caste]["buy"]  += score
            elif sig.signal == Signal.SELL:
                caste_scores[caste]["sell"] += score
            else:
                caste_scores[caste]["hold"] += score

            caste_scores[caste]["count"] += 1

        # Aggregate across castes
        total_buy  = sum(c["buy"]  for c in caste_scores.values())
        total_sell = sum(c["sell"] for c in caste_scores.values())
        total_hold = sum(c["hold"] for c in caste_scores.values())
        total      = total_buy + total_sell + total_hold or 1

        buy_pct  = total_buy  / total
        sell_pct = total_sell / total

        if buy_pct >= self.threshold:
            action     = "BUY"
            confidence = buy_pct
            execute    = True
        elif sell_pct >= self.threshold:
            action     = "SELL"
            confidence = sell_pct
            execute    = True
        else:
            action     = "HOLD"
            confidence = max(buy_pct, sell_pct)
            execute    = False

        decision = ColonyDecision(
            token           = token,
            action          = action,
            confidence      = round(confidence, 4),
            buy_score       = round(buy_pct, 4),
            sell_score      = round(sell_pct, 4),
            hold_score      = round(total_hold / total, 4),
            signal_count    = len(signals),
            caste_breakdown = {
                caste: {
                    "buy":   round(v["buy"],  4),
                    "sell":  round(v["sell"], 4),
                    "count": v["count"],
                }
                for caste, v in caste_scores.items()
            },
            timestamp = time.time(),
            execute   = execute,
        )

        logger.info(
            f"[COLONY] {token} → {action} "
            f"(buy={buy_pct:.1%} sell={sell_pct:.1%} "
            f"agents={len(signals)} execute={execute})"
        )

        # Publish decision to Redis for execution layer
        if self.redis:
            await self.redis.rpush(
                REDIS_DECISIONS_KEY,
                json.dumps(asdict(decision))
            )
            await self.redis.expire(REDIS_DECISIONS_KEY, 300)

        # Clear buffer after aggregation
        self._signal_buffer[token] = []
        return decision

    async def listen_for_decisions(self):
        """Generator that yields ColonyDecisions as they arrive via Redis pubsub."""
        if not self.redis:
            raise RuntimeError("Redis not connected. Call connect() first.")

        pubsub = self.redis.pubsub()
        await pubsub.subscribe(REDIS_DECISIONS_KEY)

        async for message in pubsub.listen():
            if message["type"] == "message":
                try:
                    data = json.loads(message["data"])
                    yield ColonyDecision(**data)
                except Exception as e:
                    logger.error(f"[COLONY] Failed to parse decision: {e}")
