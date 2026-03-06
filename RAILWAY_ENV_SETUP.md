# Railway Environment Variables Setup

## Critical Variables to Set in Railway

Go to your Railway project → Variables tab and add these:

### Network Configuration
```
USE_TESTNET=true
```
This will switch to Base Sepolia testnet where your contract is deployed.

### CDP (Coinbase Developer Platform) Keys
```
CDP_API_KEY_NAME=organizations/your-org-id/apiKeys/your-key-id
CDP_API_KEY_PRIVATE_KEY=-----BEGIN EC PRIVATE KEY-----\nYourKeyHere\n-----END EC PRIVATE KEY-----
```

**IMPORTANT:** The CDP private key must be in PEM format or base64 Ed25519 format.

To get your CDP keys:
1. Go to https://portal.cdp.coinbase.com/
2. Create a new API key
3. Download the JSON file
4. The `name` field goes in `CDP_API_KEY_NAME`
5. The `privateKey` field goes in `CDP_API_KEY_PRIVATE_KEY` (keep the `\n` newlines)

### Other Required Variables
```
COINGECKO_API_KEY=your_coingecko_key
BASESCAN_API_KEY=67ZXBCMXU21C39GTHMBUYCK6EP3PUK5JIX
TREASURY_ADDRESS=0x2DD651e259e9111cCAA8e977Ecc2798e320576fC
COLONY_CONTRACT_ADDRESS=0xb686D1AE38FfD6404C78f41570D90Dfbd02646E0
CDP_PROJECT_ID=62a0465b-ab53-4a13-97f3-37376939d73d
```

### Auto-Set by Railway
```
REDIS_URL=redis://...
PORT=8080
```
These are automatically set when you add the Redis addon.

## Current Issues from Logs

1. ✅ **Colony is running** - Paper trading active
2. ✅ **Server is responding** - No timeout errors
3. ❌ **CDP keys invalid** - Trader falling back to simulation
4. ❌ **Network mismatch** - Using mainnet but contract on testnet

## Fix Steps

1. Set `USE_TESTNET=true` in Railway Variables
2. Fix CDP keys format (see above)
3. Redeploy (Railway auto-deploys on variable changes)
4. Dashboard will show "BASE SEPOLIA TESTNET"
5. Trader will connect to CDP properly

## Testing CDP Keys Locally

Before adding to Railway, test locally:
```bash
python -c "from cdp import CdpClient; c = CdpClient(api_key_id='your_name', api_key_secret='your_key'); print('✅ CDP keys valid')"
```

If this fails, your key format is wrong.
