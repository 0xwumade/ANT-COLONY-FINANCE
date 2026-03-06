"""
websocket_server.py — Real-time Colony Data Broadcaster

Streams live colony data to the dashboard via WebSocket.
Reads from Redis pheromone bus and broadcasts to connected clients.
"""
import asyncio
import json
from loguru import logger
from aiohttp import web
import aiohttp
import redis.asyncio as redis
from settings import settings


class ColonyBroadcaster:
    """Broadcasts colony signals and decisions to WebSocket clients."""
    
    def __init__(self):
        self.clients = set()
        self.redis_client = None
        
    async def connect_redis(self):
        """Connect to Redis pheromone bus."""
        try:
            self.redis_client = await redis.from_url(
                settings.REDIS_URL,
                db=settings.REDIS_DB,
                decode_responses=True
            )
            logger.info("[WS] Connected to Redis pheromone bus")
        except Exception as e:
            logger.error(f"[WS] Redis connection failed: {e}")
    
    async def websocket_handler(self, request):
        """Handle WebSocket connections from dashboard."""
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        
        self.clients.add(ws)
        logger.info(f"[WS] Client connected. Total clients: {len(self.clients)}")
        
        try:
            async for msg in ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    # Echo back for ping/pong
                    if msg.data == 'ping':
                        await ws.send_str('pong')
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    logger.error(f"[WS] Connection error: {ws.exception()}")
        finally:
            self.clients.discard(ws)
            logger.info(f"[WS] Client disconnected. Total clients: {len(self.clients)}")
        
        return ws
    
    async def broadcast(self, data: dict):
        """Broadcast data to all connected clients."""
        if not self.clients:
            return
        
        message = json.dumps(data)
        dead_clients = set()
        
        for client in self.clients:
            try:
                await client.send_str(message)
            except Exception as e:
                logger.warning(f"[WS] Failed to send to client: {e}")
                dead_clients.add(client)
        
        # Remove dead connections
        self.clients -= dead_clients
    
    async def listen_redis(self):
        """Listen to Redis pub/sub for colony events."""
        if not self.redis_client:
            await self.connect_redis()
        
        pubsub = self.redis_client.pubsub()
        await pubsub.subscribe('colony:signals', 'colony:decisions', 'colony:trades')
        
        logger.info("[WS] Listening to Redis pub/sub channels")
        
        async for message in pubsub.listen():
            if message['type'] == 'message':
                try:
                    data = json.loads(message['data'])
                    await self.broadcast(data)
                except Exception as e:
                    logger.error(f"[WS] Broadcast error: {e}")


async def start_server():
    """Start WebSocket server."""
    broadcaster = ColonyBroadcaster()
    
    app = web.Application()
    app.router.add_get('/ws', broadcaster.websocket_handler)
    
    runner = web.AppRunner(app)
    await runner.setup()
    
    site = web.TCPSite(runner, 'localhost', 8765)
    await site.start()
    
    logger.info("[WS] WebSocket server started on ws://localhost:8765/ws")
    
    # Start Redis listener
    await broadcaster.listen_redis()


if __name__ == '__main__':
    asyncio.run(start_server())
