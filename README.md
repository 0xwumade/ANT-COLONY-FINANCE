# 🐜 Ant Colony Finance

> Swarm Intelligence Trading on Base Network

A decentralized trading system where thousands of specialized AI agents collectively decide when to trade — like an ant colony navigating toward food.

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                    AGENT SWARM                       │
│  🐜 WhaleAgent    🐜 TechnicalAgent  🐜 LiquidityAgent │
│  🐜 SentimentAgent              🐜 ArbitrageAgent     │
└──────────────────────┬──────────────────────────────┘
                       │  PheromoneSignals
                       ▼
┌─────────────────────────────────────────────────────┐
│               COLONY BRAIN (Redis)                   │
│  Weighted Quorum Consensus                           │
│  threshold: 65% weighted score → ColonyDecision      │
└──────────────────────┬──────────────────────────────┘
                       │  ColonyDecision (execute=True)
                       ▼
┌─────────────────────────────────────────────────────┐
│          EXECUTION LAYER (CDP Swap API)              │
│  ColonyTrader → CDP Swap API (130+ DEXes via 0x)    │
│  Auto-approval, best pricing, sub-500ms latency      │
│  AntColonyFinance.sol → onchain audit log            │
└─────────────────────────────────────────────────────┘
```

### Why CDP Swap API?

Instead of direct Uniswap V3 calls, we use the Coinbase Developer Platform Swap API:

- ✅ Automatic token approvals (no separate approval tx)
- ✅ Best pricing across 130+ exchanges via 0x aggregation
- ✅ Built-in slippage protection
- ✅ Sub-500ms latency, no infrastructure to manage
- ✅ Single API call: quote → sign → broadcast
- ✅ Qualifies for CDP Builder Grant

### Caste Weights

| Caste      | Weight | Analyzes                        |
|------------|--------|---------------------------------|
| 🐋 Whale   | 30%    | Large wallet movements onchain  |
| 💧 Liquidity | 25%  | Pool TVL & volume changes       |
| 📈 Technical | 20%  | RSI, MACD, price momentum       |
| ⚡ Arbitrage | 15%  | Cross-DEX price gaps            |
| 💬 Sentiment | 10%  | Twitter/social signals          |

---

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env with your API keys and wallet info
```

### 3. Start Redis

```bash
docker run -d -p 6379:6379 redis:alpine
# or: brew install redis && redis-server
```

### 4. Deploy the smart contract

```bash
cd contracts/
# Using Hardhat or Foundry — deploy AntColonyFinance.sol to Base
# Then set COLONY_CONTRACT_ADDRESS in .env
```

### 5. Run the colony

```bash
# Simulation mode (no real trades — recommended to start)
python main.py --simulate

# Live mode
python main.py
```

### 6. Open the dashboard

```bash
# Serve with treasury address injected from .env
python serve_dashboard.py
# Then open http://localhost:8000

# Or open the HTML directly (you'll need to manually set treasury address)
# Open index.html in your browser
```

---

## CDP Builder Grant

This project qualifies for the [Coinbase Developer Platform Builder Grants](https://www.coinbase.com/en-gb/blog/cdp-builder-grants-30k-in-funding-for-developers-building-on-base) ($30k):

- ✅ Built on Base network
- ✅ Uses CDP Swap API for trade execution (130+ DEXes via 0x)
- ✅ Uses CDP Wallet API for treasury management
- ✅ Onchain contract (AntColonyFinance.sol) logs all decisions
- ✅ Consumer-facing dashboard with Coinbase Onramp integration
- ✅ One-click treasury funding via "Fund Treasury" button

### CDP Integration Features

1. CDP Swap API
   - Automatic token approvals (no separate approval transactions)
   - Best pricing across 130+ exchanges via 0x aggregation
   - Built-in slippage protection
   - Sub-500ms latency

2. Coinbase Onramp Integration
   - "Fund Treasury" button in dashboard
   - Purchase ETH or USDC with fiat (credit card, bank transfer)
   - Funds sent directly to colony treasury on Base
   - No manual wallet setup required

---

## Project Structure

```
ant-colony-finance/
├── agents/
│   ├── base_agent.py        # Abstract base class
│   ├── whale_agent.py       # Onchain whale tracking
│   ├── technical_agent.py   # RSI / MACD / momentum
│   ├── liquidity_agent.py   # Pool depth analysis
│   ├── sentiment_agent.py   # Social signals
│   └── arbitrage_agent.py   # Cross-DEX arb detection
├── consensus/
│   └── colony_brain.py      # Weighted quorum engine
├── execution/
│   └── trader.py            # Base DEX execution
├── contracts/
│   └── AntColonyFinance.sol # Onchain audit log
├── dashboard/
│   └── index.html           # Live monitoring UI
├── serve_dashboard.py       # Dashboard server with env injection
├── tests/
│   └── test_consensus.py    # Unit tests
├── config/
│   └── settings.py          # Central config
├── main.py                  # Orchestrator
├── requirements.txt
└── .env.example
```

---

## Adding New Tokens

Edit `TRACKED_TOKENS` in `main.py`:

```python
TRACKED_TOKENS = [
    {
        "symbol":       "MYTOKEN",
        "address":      "0xTokenAddress",
        "coingecko_id": "my-token-coingecko-id",
        "twitter":      ["$MYTOKEN", "MyToken Base"],
    },
]
```

## Running Tests

```bash
pytest tests/ -v
```

---

## Disclaimer

This software is for educational purposes. Crypto trading carries significant risk. Never trade with funds you cannot afford to lose.
