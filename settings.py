"""
config/settings.py — Central config for Ant Colony Finance
"""
import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # ── Network ───────────────────────────────
    BASE_RPC_URL: str         = os.getenv("BASE_RPC_URL", "https://mainnet.base.org")
    BASE_CHAIN_ID: int        = int(os.getenv("BASE_CHAIN_ID", "8453"))
    BASE_TESTNET_RPC_URL: str = os.getenv("BASE_TESTNET_RPC_URL", "https://sepolia.base.org")
    BASE_TESTNET_CHAIN_ID: int= int(os.getenv("BASE_TESTNET_CHAIN_ID", "84532"))

    # ── CDP ───────────────────────────────────
    CDP_API_KEY_NAME: str     = os.getenv("CDP_API_KEY_NAME", "")
    CDP_API_KEY_PRIVATE_KEY: str = os.getenv("CDP_API_KEY_PRIVATE_KEY", "")
    CDP_WALLET_ID: str        = os.getenv("CDP_WALLET_ID", "")

    # ── Treasury ──────────────────────────────
    TREASURY_PRIVATE_KEY: str = os.getenv("TREASURY_PRIVATE_KEY", "")
    TREASURY_ADDRESS: str     = os.getenv("TREASURY_ADDRESS", "")

    # ── DEX Contracts ─────────────────────────
    UNISWAP_V3_ROUTER: str    = os.getenv("UNISWAP_V3_ROUTER", "0x2626664c2603336E57B271c5C0b26F421741e481")
    AERODROME_ROUTER: str     = os.getenv("AERODROME_ROUTER", "0xcF77a3Ba9A5CA399B7c97c74d54e5b1Beb874E43")

    # ── Redis ─────────────────────────────────
    REDIS_URL: str            = os.getenv("REDIS_URL", "redis://localhost:6379")
    REDIS_DB: int             = int(os.getenv("REDIS_DB", "0"))

    # ── Data Sources ──────────────────────────
    COINGECKO_API_KEY: str    = os.getenv("COINGECKO_API_KEY", "")
    BASESCAN_API_KEY: str     = os.getenv("BASESCAN_API_KEY", "")
    TWITTER_BEARER_TOKEN: str = os.getenv("TWITTER_BEARER_TOKEN", "")
    DUNE_API_KEY: str         = os.getenv("DUNE_API_KEY", "")

    # ── Swarm Parameters ──────────────────────
    SWARM_SIZE: int           = int(os.getenv("SWARM_SIZE", "100"))
    CONSENSUS_THRESHOLD: float= float(os.getenv("CONSENSUS_THRESHOLD", "0.65"))
    SIGNAL_WINDOW_SECONDS: int= int(os.getenv("SIGNAL_WINDOW_SECONDS", "60"))
    MAX_TRADE_SIZE_ETH: float = float(os.getenv("MAX_TRADE_SIZE_ETH", "0.1"))
    MIN_TRADE_SIZE_ETH: float = float(os.getenv("MIN_TRADE_SIZE_ETH", "0.01"))

    # ── Contract ──────────────────────────────
    COLONY_CONTRACT_ADDRESS: str = os.getenv("COLONY_CONTRACT_ADDRESS", "")

    # ── Agent Caste Weights ───────────────────
    # How much each agent type influences the final consensus score
    CASTE_WEIGHTS: dict = {
        "whale":       0.30,   # Whale wallet movements — highest trust
        "liquidity":   0.25,   # Liquidity pool changes
        "technical":   0.20,   # Technical indicators
        "arbitrage":   0.15,   # Arb opportunity hunters
        "sentiment":   0.10,   # Social sentiment — lowest trust
    }

settings = Config()
