"""
Base agent class for Ant Colony Finance
"""
from dataclasses import dataclass
from enum import Enum


class Signal(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


@dataclass
class PheromoneSignal:
    """Signal emitted by an agent"""
    token: str
    caste: str
    signal: Signal
    confidence: float  # 0.0 to 1.0
    timestamp: float


class BaseAgent:
    """Base class for all agent castes"""
    
    def __init__(self, token: str, **kwargs):
        self.token = token
        self.caste = self.__class__.__name__.replace("Agent", "").upper()
    
    async def run(self) -> PheromoneSignal:
        """Override this in subclasses"""
        raise NotImplementedError
