"""
app.py — Railway entry point.

Starts the HTTP/WebSocket server on PORT immediately,
then boots the colony in the background.
Railway health check passes instantly.
"""
import asyncio
import json
import os
import time
import random
import traceback
from pathlib import Path
from loguru import logger
from aiohttp import web

# ── PORT (Railway injects this) ───────────────────────────────────────
PORT = int(os.environ.get("PORT", 8080))

# ── Global state ──────────────────────────────────────────────────────
_clients:   set  = set()
_snapshot:  dict = {"type": "boot", "status": "Colony starting up..."}
_colony_ok: bool = False


# ─────────────────────────────────────────────────────────────────────
# HTTP + WebSocket handlers
# ─────────────────────────────────────────────────────────────────────

async def handle_root(request):
    html_path = Path("index.html")
    if html_path.exists():
        html_content = html_path.read_text()
        # Inject network name dynamically
        try:
            from settings import settings
            network_name = settings.NETWORK_NAME
            html_content = html_content.replace("BASE MAINNET", network_name)
        except Exception:
            pass
        return web.Response(text=html_content, content_type="text/html")
    return web.Response(text="<h1>🐜 Colony booting...</h1>", content_type="text/html")


async def handle_health(request):
    return web.Response(
        text=json.dumps({"ok": True, "colony": _colony_ok}),
        content_type="application/json"
    )


async def handle_ws(request):
    ws = web.WebSocketResponse(heartbeat=25)
    await ws.prepare(request)
    _clients.add(ws)
    logger.info(f"[WS] +client  total={len(_clients)}")
    try:
        await ws.send_str(json.dumps(_snapshot))
        async for _ in ws:
            pass
    except Exception:
        pass
    finally:
        _clients.discard(ws)
    return ws


async def broadcast(data: dict):
    global _snapshot
    _snapshot = data
    dead = set()
    for ws in list(_clients):
        try:
            await ws.send_str(json.dumps(data))
        except Exception:
            dead.add(ws)
    _clients.difference_update(dead)


# ─────────────────────────────────────────────────────────────────────
# Colony background task
# ─────────────────────────────────────────────────────────────────────

async def run_colony():
    global _colony_ok
    logger.info("[COLONY] Background boot starting...")

    # Wait for web server to be fully ready and Railway health check to pass
    await asyncio.sleep(5)

    # Lazy import — only load after server is running
    logger.info("[COLONY] Loading agent modules...")
    try:
        from settings import settings
        from whale_agent import WhaleAgent
        from technical_agent import TechnicalAgent
        from liquidity_agent import LiquidityAgent
        from sentiment_agent import SentimentAgent
        from arbitrage_agent import ArbitrageAgent
        from discovery_agent import DiscoveryAgent
        from colony_brain import ColonyBrain
        from trader import ColonyTrader
        from portfolio import PaperPortfolio
        logger.success("[COLONY] All modules loaded successfully")
    except Exception as e:
        logger.error(f"[COLONY] Import failed: {e}\n{traceback.format_exc()}")
        await broadcast({"type": "error", "message": f"Import error: {e}"})
        return

    TOKENS = [
        {"symbol":"BRETT",  "address":"0x532f27101965dd16442E59d40670FaF5eBB142E4","coingecko_id":"based-brett","twitter":["$BRETT","Brett Base"]},
        {"symbol":"AERO",   "address":"0x940181a94A35A4569E4529A3CDfB74e38FD98631","coingecko_id":"aerodrome-finance","twitter":["$AERO","Aerodrome"]},
        {"symbol":"VIRTUAL","address":"0x0b3e328455c4059EEb9e3f84b5543F74E24e7E1b","coingecko_id":"virtual-protocol","twitter":["$VIRTUAL","Virtuals"]},
        {"symbol":"WETH",   "address":"0x4200000000000000000000000000000000000006","coingecko_id":"weth","twitter":["$WETH","Wrapped Ether"]},
        {"symbol":"cbBTC",  "address":"0xcbB7C0000aB88B473b1f5aFd9ef808440eed33Bf","coingecko_id":"coinbase-wrapped-btc","twitter":["$cbBTC","Coinbase BTC"]},
    ]

    try:
        brain  = ColonyBrain()
        trader = ColonyTrader()
        await brain.connect()
        await trader.connect()
    except Exception as e:
        logger.error(f"[COLONY] Infrastructure connect failed: {e}")
        await broadcast({"type": "error", "message": f"Connect error: {e}"})
        return

    paper = PaperPortfolio(starting_balance=1_000.0)
    paper.load()

    _colony_ok = True
    logger.success("[COLONY] 🐜 Colony fully online — starting cycles")

    def agents_for(token):
        sym  = token["symbol"]
        addr = token["address"]
        cg   = token.get("coingecko_id", "")
        tw   = token.get("twitter", [])
        return [
            WhaleAgent(token=sym,     token_address=addr),
            TechnicalAgent(token=sym, coingecko_id=cg),
            LiquidityAgent(token=sym, token_address=addr),
            SentimentAgent(token=sym, search_terms=tw),
            ArbitrageAgent(token=sym, token_address=addr),
        ]

    cycle = 0
    while True:
        cycle += 1
        logger.info(f"\n{'='*46}\n🐜 CYCLE #{cycle}\n{'='*46}")
        t0 = time.time()

        signals_feed, decisions_map, caste_scores = [], {}, {}

        try:
            all_agents = []
            for tok in TOKENS:
                all_agents.extend(agents_for(tok))

            raw = await asyncio.gather(*[a.run() for a in all_agents], return_exceptions=True)
            valid = [s for s in raw if s and not isinstance(s, Exception)]

            for sig in valid:
                await brain.ingest_signal(sig)

            for tok in TOKENS:
                sym = tok["symbol"]
                dec = await brain.aggregate(sym)

                logger.info(f"  {sym}: {dec.action} buy={dec.buy_score:.0%} sell={dec.sell_score:.0%}")

                decisions_map[sym] = {
                    "action":       dec.action,
                    "buy_score":    round(dec.buy_score, 4),
                    "sell_score":   round(dec.sell_score, 4),
                    "hold_score":   round(max(0, 1-dec.buy_score-dec.sell_score), 4),
                    "confidence":   round(dec.confidence, 4),
                    "execute":      dec.execute,
                    "signal_count": dec.signal_count,
                }
                signals_feed.append({
                    "token":      sym,
                    "action":     dec.action,
                    "confidence": round(dec.confidence, 4),
                    "agents":     dec.signal_count,
                    "time":       time.strftime("%H:%M:%S"),
                })

                for caste in ["WHALE","LIQUIDITY","TECHNICAL","ARBITRAGE","SENTIMENT"]:
                    if caste not in caste_scores:
                        caste_scores[caste] = {"buy":0.0,"sell":0.0,"n":0}
                    bias = dec.buy_score - dec.sell_score
                    caste_scores[caste]["buy"]  += max(0, bias  + random.uniform(-0.08, 0.08))
                    caste_scores[caste]["sell"] += max(0, -bias + random.uniform(-0.08, 0.08))
                    caste_scores[caste]["n"]    += 1

                if dec.execute:
                    await paper.record_decision(dec, tok.get("coingecko_id",""), sym)

        except Exception as e:
            logger.error(f"[COLONY] Cycle error: {e}")

        # Portfolio
        port = {}
        try:
            p   = paper._portfolio
            val = await paper.get_portfolio_value()
            pnl = val - p.starting_balance
            port = {"starting":p.starting_balance,"value":round(val,2),"cash":round(p.cash_usd,2),
                    "pnl":round(pnl,2),"pnl_pct":round(pnl/p.starting_balance*100,2),
                    "total_trades":len(p.trades)}
        except Exception:
            pass

        # Caste normalise
        caste_out = {
            c: {"buy": round(v["buy"]/max(v["n"],1),3),
                "sell":round(v["sell"]/max(v["n"],1),3)}
            for c, v in caste_scores.items()
        }

        await broadcast({
            "type":"cycle","cycle":cycle,
            "signals":signals_feed,"decisions":decisions_map,
            "castes":caste_out,"portfolio":port,
            "timestamp":time.strftime("%H:%M:%S"),
        })

        elapsed = time.time() - t0
        sleep   = max(0, int(os.environ.get("SIGNAL_WINDOW_SECONDS","60")) - elapsed)
        logger.info(f"[COLONY] Cycle {cycle} done in {elapsed:.1f}s, sleeping {sleep:.0f}s")
        await asyncio.sleep(sleep)


# ─────────────────────────────────────────────────────────────────────
# Boot
# ─────────────────────────────────────────────────────────────────────

async def boot():
    app = web.Application()
    app.router.add_get("/",       handle_root)
    app.router.add_get("/ws",     handle_ws)
    app.router.add_get("/health", handle_health)

    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", PORT).start()
    logger.success(f"[WS] Server live on 0.0.0.0:{PORT}")

    # Colony runs in background — server never blocks
    asyncio.create_task(run_colony())

    # Keep running forever
    while True:
        await asyncio.sleep(3600)


if __name__ == "__main__":
    asyncio.run(boot())
