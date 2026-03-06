"""
server/ws_server.py — WebSocket + HTTP server for the live dashboard

Runs inside the same process as the colony on Railway.
Serves:
  GET  /           → dashboard HTML
  GET  /ws         → WebSocket connection for live data
  GET  /health     → health check for Railway

Any connected browser receives a JSON push after every colony cycle.
"""
import asyncio
import json
import os
from pathlib import Path
from aiohttp import web
from loguru import logger

# All currently connected WebSocket clients
_clients: set[web.WebSocketResponse] = set()

# Latest snapshot — new clients get this immediately on connect
_latest_snapshot: dict = {}


async def ws_handler(request: web.Request) -> web.WebSocketResponse:
    """Handle a new WebSocket connection from the dashboard."""
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    _clients.add(ws)
    logger.info(f"[WS] Client connected — {len(_clients)} total")

    # Send the latest snapshot immediately so dashboard isn't blank
    if _latest_snapshot:
        await ws.send_str(json.dumps(_latest_snapshot))

    try:
        async for msg in ws:
            pass   # we only push, never receive
    finally:
        _clients.discard(ws)
        logger.info(f"[WS] Client disconnected — {len(_clients)} remaining")

    return ws


async def dashboard_handler(request: web.Request) -> web.Response:
    """Serve the dashboard HTML file."""
    html_path = Path(__file__).parent / "index.html"
    if html_path.exists():
        return web.Response(
            text=html_path.read_text(),
            content_type="text/html"
        )
    return web.Response(text="<h1>Dashboard not found</h1>", content_type="text/html")


async def health_handler(request: web.Request) -> web.Response:
    """Railway health check endpoint."""
    return web.Response(
        text=json.dumps({"status": "ok", "clients": len(_clients)}),
        content_type="application/json"
    )


async def broadcast(data: dict):
    """
    Push a data snapshot to all connected dashboard clients.
    Called by the colony after every cycle.
    """
    global _latest_snapshot
    _latest_snapshot = data

    if not _clients:
        return

    payload = json.dumps(data)
    dead = set()
    for ws in _clients:
        try:
            await ws.send_str(payload)
        except Exception:
            dead.add(ws)

    _clients.difference_update(dead)


async def start_server() -> web.AppRunner:
    """Create and start the aiohttp server. Returns runner for cleanup."""
    app = web.Application()
    app.router.add_get("/",       dashboard_handler)
    app.router.add_get("/ws",     ws_handler)
    app.router.add_get("/health", health_handler)

    port = int(os.environ.get("PORT", 8080))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.success(f"[WS] Dashboard server started on port {port}")
    return runner
