# 🚂 Deploying Ant Colony Finance to Railway
# Runs 24/7 in the cloud — no PC needed

---

## What Railway gives you
- 24/7 uptime — colony keeps running when your PC is off
- Built-in Redis — no separate setup needed
- Free tier: $5 credit/month (enough for the colony)
- Auto-restarts if the process crashes
- Live logs in the browser

---

## Step 1 — Push your code to GitHub

Railway deploys directly from GitHub. If you haven't already:

1. Go to github.com and create a new repository
   - Name it: ant-colony-finance
   - Set it to Private (your .env has sensitive keys)
   - Do NOT initialise with a README

2. Open a terminal in C:\ACF and run:
```
git init
git add .
git commit -m "initial colony deploy"
git branch -M main
git remote add origin https://github.com/0xwumade/ant-colony-finance.git
git push -u origin main
```

IMPORTANT — before pushing, make sure your .gitignore
contains these lines so your keys are never uploaded:
```
.env
paper_portfolio.json
__pycache__/
*.pyc
node_modules/
artifacts/
cache/
```

---

## Step 2 — Create Railway account

1. Go to railway.app
2. Click "Login" → "Login with GitHub"
3. Authorise Railway to access your GitHub

---

## Step 3 — Create a new project

1. Click "New Project"
2. Select "Deploy from GitHub repo"
3. Find and select "ant-colony-finance"
4. Railway will detect it's a Python project automatically

---

## Step 4 — Add Redis

The colony needs Redis for the pheromone signal bus.
Railway provides it for free inside your project.

1. Inside your Railway project, click "+ New"
2. Select "Database" → "Add Redis"
3. Railway creates a Redis instance and automatically
   sets the REDIS_URL variable — you don't have to do anything else

---

## Step 5 — Add your environment variables

This is where you paste all the values from your local .env file.

1. Click on your colony service (not Redis)
2. Click "Variables" tab
3. Click "Raw Editor" and paste everything from your .env file

Your variables should include:
```
CDP_API_KEY_NAME=
CDP_API_KEY_PRIVATE_KEY=
CDP_PROJECT_ID=
COLONY_CONTRACT_ADDRESS=
BASESCAN_API_KEY=
COINGECKO_API_KEY=
BASE_RPC_URL=https://mainnet.base.org
BASE_CHAIN_ID=8453
CONSENSUS_THRESHOLD=0.65
SWARM_SIZE=100
MAX_TRADE_SIZE_ETH=0.1
MIN_TRADE_SIZE_ETH=0.01
```

NOTE — Do NOT add REDIS_URL manually.
Railway links it automatically from the Redis service.

---

## Step 6 — Deploy

1. Railway will auto-deploy as soon as you save variables
2. Click "Deploy" if it doesn't start automatically
3. Click on your service → "Logs" tab
4. You should see:

```
[PAPER] New portfolio created — starting balance: $1,000.00
[COLONY] Swarm initialized — 5 castes active
[WHALE] Scanning wallets for BRETT...
[LIQUIDITY] Fetching Aerodrome pools...
```

If you see those lines — the colony is live and running 24/7.

---

## Step 7 — Check logs anytime

You don't need to be at your PC to check what the colony is doing.

1. Go to railway.app → your project
2. Click your service → Logs tab
3. You'll see every cycle, every vote, every paper trade

You can also check paper_portfolio.json by going to:
Service → Files (if Railway shows the filesystem)

---

## Switching from paper to real trading

When you're ready to trade with real money:

1. In Railway Variables, change the start command by editing Procfile:
```
worker: python main.py
```
2. Make sure TREASURY_PRIVATE_KEY is set in variables
3. Push the Procfile change to GitHub → Railway auto-redeploys

---

## Costs

Railway free tier gives $5 credit per month.
The colony (Python worker + Redis) uses roughly $2-3/month.
You'll stay within the free tier easily.

If you exceed it, the Hobby plan is $5/month flat.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| Build fails | Check requirements.txt is in C:\ACF root |
| Redis connection error | Make sure Redis service is running in Railway |
| CDP key error | Double-check variables tab — no extra spaces |
| Colony stops after a few minutes | Check logs for Python errors |
| Port error | Ignore it — worker processes don't need a port |
