"""Quick script to verify agent signatures"""
import inspect
from whale_agent import WhaleAgent
from technical_agent import TechnicalAgent
from liquidity_agent import LiquidityAgent
from sentiment_agent import SentimentAgent
from arbitrage_agent import ArbitrageAgent

print("Agent Signatures:")
print(f"WhaleAgent: {inspect.signature(WhaleAgent.__init__)}")
print(f"TechnicalAgent: {inspect.signature(TechnicalAgent.__init__)}")
print(f"LiquidityAgent: {inspect.signature(LiquidityAgent.__init__)}")
print(f"SentimentAgent: {inspect.signature(SentimentAgent.__init__)}")
print(f"ArbitrageAgent: {inspect.signature(ArbitrageAgent.__init__)}")
