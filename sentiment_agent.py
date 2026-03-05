"""
agents/sentiment_agent.py — Social sentiment analysis

Analyzes Twitter/X and on-chain social signals for a token.
Lowest trust caste (weight: 0.10) — social is noisy.
"""
import asyncio
import aiohttp
import re
from textblob import TextBlob
from loguru import logger

from base_agent import BaseAgent, PheromoneSignal, Signal
from settings import settings


TWITTER_API_BASE  = "https://api.twitter.com/2"
LUNARCRUSH_BASE   = "https://lunarcrush.com/api4/public"


class SentimentAgent(BaseAgent):
    """
    Caste: SENTIMENT (weight: 0.10)

    Sources:
    1. Twitter/X search — recent tweets about the token
    2. LunarCrush social volume (if available)

    Uses TextBlob polarity for simple NLP scoring.
    """

    def __init__(self, token: str, search_terms: list[str]):
        super().__init__(token=token, caste="sentiment")
        self.search_terms = search_terms   # e.g. ["$BRETT", "Brett token Base"]
        self._analysis: dict = {}

    async def _fetch_tweets(self, session: aiohttp.ClientSession) -> list[str]:
        """Fetch recent tweets for the token's search terms."""
        if not settings.TWITTER_BEARER_TOKEN:
            return []

        headers = {"Authorization": f"Bearer {settings.TWITTER_BEARER_TOKEN}"}
        query   = " OR ".join(self.search_terms) + " -is:retweet lang:en"
        params  = {
            "query":       query,
            "max_results": 50,
            "tweet.fields": "text,public_metrics",
        }

        try:
            async with session.get(
                f"{TWITTER_API_BASE}/tweets/search/recent",
                headers=headers,
                params=params,
            ) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json()
                return [t["text"] for t in data.get("data", [])]
        except Exception:
            return []

    def _score_tweets(self, tweets: list[str]) -> tuple[float, int]:
        """
        Returns (average_polarity, tweet_count).
        Polarity: -1.0 (very negative) → +1.0 (very positive)
        """
        if not tweets:
            return 0.0, 0

        scores = []
        for tweet in tweets:
            clean = re.sub(r"http\S+|@\w+|#\w+|\$\w+", "", tweet)
            blob  = TextBlob(clean)
            scores.append(blob.sentiment.polarity)

        return sum(scores) / len(scores), len(scores)

    async def analyze(self) -> dict:
        try:
            async with aiohttp.ClientSession() as session:
                tweets = await self._fetch_tweets(session)

            avg_polarity, tweet_count = self._score_tweets(tweets)

            self._analysis = {
                "avg_polarity": avg_polarity,
                "tweet_count":  tweet_count,
                "bullish_ratio": sum(1 for t in tweets
                                     if TextBlob(t).sentiment.polarity > 0.1) / (len(tweets) or 1),
                "bearish_ratio": sum(1 for t in tweets
                                     if TextBlob(t).sentiment.polarity < -0.1) / (len(tweets) or 1),
            }
            logger.debug(
                f"[SENTIMENT:{self.agent_id}] {self.token} "
                f"polarity={avg_polarity:.3f} tweets={tweet_count}"
            )

        except Exception as e:
            logger.warning(f"[SENTIMENT:{self.agent_id}] Analysis failed: {e}")
            self._analysis = {
                "avg_polarity": 0, "tweet_count": 0,
                "bullish_ratio": 0, "bearish_ratio": 0,
            }

        return self._analysis

    async def emit(self) -> PheromoneSignal:
        polarity    = self._analysis.get("avg_polarity", 0)
        tweet_count = self._analysis.get("tweet_count", 0)

        # Low sample size → reduce confidence significantly
        volume_factor = min(tweet_count / 20, 1.0)

        if polarity > 0.15:
            signal     = Signal.BUY
            confidence = min(abs(polarity) * volume_factor, 1.0)
        elif polarity < -0.15:
            signal     = Signal.SELL
            confidence = min(abs(polarity) * volume_factor, 1.0)
        else:
            signal     = Signal.HOLD
            confidence = 0.05

        return PheromoneSignal(
            agent_id   = self.agent_id,
            caste      = self.caste,
            token      = self.token,
            signal     = signal,
            confidence = confidence,
            metadata   = self._analysis,
        )
