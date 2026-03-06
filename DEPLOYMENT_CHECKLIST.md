# 🚀 Railway Deployment Checklist

## Files Ready for Deployment

✅ **ws_server.py** - WebSocket server for live dashboard  
✅ **main.py** - Integrated with WebSocket broadcasting  
✅ **index.html** - Connects to Railway WebSocket automatically  
✅ **requirements.txt** - Fixed dependency conflicts  
✅ **railway.toml** - Railway configuration  
✅ **Procfile** - Starts colony in paper trading mode  

## What Happens When You Deploy

1. **Railway builds** your project with fixed dependencies
2. **Colony starts** in paper trading mode (`python main.py --paper`)
3. **WebSocket server** starts on Railway's PORT (auto-assigned)
4. **Dashboard** is served at your Railway URL
5. **Live data** streams from colony to dashboard via WebSocket

## How to Deploy

```bash
git add .
git commit -m "Ready for Railway deployment with live dashboard"
git push origin main
```

Railway will automatically redeploy.

## Access Your Dashboard

Once deployed, Railway gives you a URL like:
```
https://your-service.up.railway.app
```

Open that URL in your browser and you'll see:
- 🔗 "COLONY LIVE" indicator (green dot)
- Real cycle numbers from your colony
- Live agent decisions
- Paper portfolio updates

## Environment Variables Needed in Railway

Make sure these are set in Railway → Variables tab:

```
COINGECKO_API_KEY=your_key
CDP_API_KEY_NAME=your_name
CDP_API_KEY_PRIVATE_KEY=your_key
CDP_PROJECT_ID=your_id
TREASURY_ADDRESS=your_address
BASESCAN_API_KEY=your_key
COLONY_CONTRACT_ADDRESS=0xb686D1AE38FfD6404C78f41570D90Dfbd02646E0
REDIS_URL=(auto-set by Railway when you add Redis)
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Build fails | Check Railway logs for dependency errors |
| WebSocket won't connect | Ensure PORT is not hardcoded, use `os.environ.get("PORT")` |
| Dashboard shows "Connecting..." | Check Railway logs - colony might not be running |
| No data updating | Verify `broadcast()` is being called in main.py |

## Next Steps After Deployment

1. Check Railway logs to see colony running
2. Open your Railway URL to see live dashboard
3. Monitor paper trades in real-time
4. When ready, switch from `--paper` to live trading

---

**Ready to deploy!** Just push to GitHub and Railway will handle the rest.
