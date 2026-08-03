#!/usr/bin/env python3
"""
SAMUDRA RAKSHAK - Cloud Backend Server
WebSocket + REST API Server for Base Station & Vessel Dashboards
Run this on a cloud server (AWS, DigitalOcean, Heroku, etc.)
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Set, Dict, List
from aiohttp import web
import aiohttp_cors

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============================================================================
# GLOBAL STATE
# ============================================================================

class DataStore:
    """In-memory data store for vessel and base station data"""
    def __init__(self):
        self.vessel_data: List[Dict] = []
        self.base_station_data: Dict = {}
        self.buoy_status: Dict = {}
        self.max_packets = 100
        
    def add_vessel_packet(self, packet: Dict):
        """Add vessel packet to store"""
        packet['received_at'] = datetime.now().isoformat()
        self.vessel_data.append(packet)
        # Keep only last 100 packets
        if len(self.vessel_data) > self.max_packets:
            self.vessel_data.pop(0)
    
    def update_base_station(self, data: Dict):
        """Update base station status"""
        self.base_station_data = data
        self.base_station_data['updated_at'] = datetime.now().isoformat()
    
    def update_buoy_status(self, data: Dict):
        """Update buoy status"""
        self.buoy_status = data
        self.buoy_status['updated_at'] = datetime.now().isoformat()
    
    def get_latest_vessel_data(self, count: int = 10):
        """Get latest vessel data"""
        return self.vessel_data[-count:]
    
    def get_base_station_data(self):
        """Get base station data"""
        return self.base_station_data
    
    def get_buoy_status(self):
        """Get buoy status"""
        return self.buoy_status

# Initialize data store
data_store = DataStore()

# WebSocket clients
websocket_clients: Set[web.WebSocketResponse] = set()

# ============================================================================
# WEBSOCKET HANDLERS
# ============================================================================

async def websocket_handler(request):
    """Handle WebSocket connections from dashboards"""
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    websocket_clients.add(ws)
    
    client_type = request.query.get('type', 'unknown')
    logger.info(f"WebSocket client connected: {client_type}")
    
    try:
        # Send initial data
        await ws.send_json({
            'type': 'initial_data',
            'vessel_data': data_store.get_latest_vessel_data(10),
            'base_station': data_store.get_base_station_data(),
            'buoy_status': data_store.get_buoy_status()
        })
        
        # Keep connection alive and handle incoming messages
        async for msg in ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                try:
                    data = json.loads(msg.data)
                    logger.info(f"Received from {client_type}: {data.get('type')}")
                except json.JSONDecodeError:
                    logger.error(f"Invalid JSON from {client_type}")
            elif msg.type == aiohttp.WSMsgType.ERROR:
                logger.error(f"WebSocket error: {ws.exception()}")
                
    except Exception as e:
        logger.error(f"WebSocket handler error: {e}")
    finally:
        websocket_clients.discard(ws)
        logger.info(f"WebSocket client disconnected: {client_type}")
    
    return ws

# ============================================================================
# BROADCAST FUNCTION
# ============================================================================

async def broadcast_to_clients(message: Dict):
    """Broadcast message to all connected WebSocket clients"""
    if not websocket_clients:
        return
    
    disconnected = set()
    for ws in websocket_clients:
        try:
            await ws.send_json(message)
        except Exception as e:
            logger.error(f"Failed to send to client: {e}")
            disconnected.add(ws)
    
    # Remove disconnected clients
    for ws in disconnected:
        websocket_clients.discard(ws)

# ============================================================================
# REST API ENDPOINTS
# ============================================================================

async def handle_vessel_data(request):
    """
    Endpoint for Vessel ESP32 to send data
    POST /api/vessel/data
    """
    try:
        data = await request.json()
        
        # Validate required fields
        if 'id' not in data:
            return web.json_response({'error': 'Missing vessel ID'}, status=400)
        
        # Store data
        data_store.add_vessel_packet(data)
        logger.info(f"Vessel data received: {data.get('id')}")
        
        # Broadcast to WebSocket clients
        await broadcast_to_clients({
            'type': 'vessel_data',
            'data': data
        })
        
        return web.json_response({'status': 'success'})
        
    except json.JSONDecodeError:
        return web.json_response({'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        logger.error(f"Error handling vessel data: {e}")
        return web.json_response({'error': str(e)}, status=500)

async def handle_base_station_data(request):
    """
    Endpoint for Base Station to send status updates
    POST /api/base/data
    """
    try:
        data = await request.json()
        
        # Store data
        data_store.update_base_station(data)
        logger.info("Base station data received")
        
        # Broadcast to WebSocket clients
        await broadcast_to_clients({
            'type': 'base_station_data',
            'data': data
        })
        
        return web.json_response({'status': 'success'})
        
    except json.JSONDecodeError:
        return web.json_response({'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        logger.error(f"Error handling base station data: {e}")
        return web.json_response({'error': str(e)}, status=500)

async def handle_buoy_data(request):
    """
    Endpoint for Buoy to send status updates
    POST /api/buoy/data
    """
    try:
        data = await request.json()
        
        # Store data
        data_store.update_buoy_status(data)
        logger.info(f"Buoy data received: {data.get('buoy_id')}")
        
        # Broadcast to WebSocket clients
        await broadcast_to_clients({
            'type': 'buoy_data',
            'data': data
        })
        
        return web.json_response({'status': 'success'})
        
    except json.JSONDecodeError:
        return web.json_response({'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        logger.error(f"Error handling buoy data: {e}")
        return web.json_response({'error': str(e)}, status=500)

async def get_vessel_data(request):
    """
    Get latest vessel data
    GET /api/vessel/data?count=10
    """
    count = int(request.query.get('count', 10))
    data = data_store.get_latest_vessel_data(count)
    return web.json_response({'data': data})

async def get_base_station_data(request):
    """
    Get base station data
    GET /api/base/data
    """
    data = data_store.get_base_station_data()
    return web.json_response({'data': data})

async def get_buoy_data(request):
    """
    Get buoy status
    GET /api/buoy/data
    """
    data = data_store.get_buoy_status()
    return web.json_response({'data': data})

async def health_check(request):
    """Health check endpoint"""
    return web.json_response({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'connected_clients': len(websocket_clients),
        'vessel_packets': len(data_store.vessel_data)
    })

# ============================================================================
# APPLICATION SETUP
# ============================================================================

def create_app():
    """Create and configure the application"""
    app = web.Application()
    
    # Configure CORS
    cors = aiohttp_cors.setup(app, defaults={
        "*": aiohttp_cors.ResourceOptions(
            allow_credentials=True,
            expose_headers="*",
            allow_headers="*",
            allow_methods="*"
        )
    })
    
    # Add routes
    app.router.add_get('/ws', websocket_handler)
    app.router.add_get('/health', health_check)
    
    # Vessel endpoints
    vessel_post = app.router.add_post('/api/vessel/data', handle_vessel_data)
    vessel_get = app.router.add_get('/api/vessel/data', get_vessel_data)
    
    # Base station endpoints
    base_post = app.router.add_post('/api/base/data', handle_base_station_data)
    base_get = app.router.add_get('/api/base/data', get_base_station_data)
    
    # Buoy endpoints
    buoy_post = app.router.add_post('/api/buoy/data', handle_buoy_data)
    buoy_get = app.router.add_get('/api/buoy/data', get_buoy_data)
    
    # Enable CORS for all routes
    for route in [vessel_post, vessel_get, base_post, base_get, buoy_post, buoy_get]:
        cors.add(route)
    
    return app

# ============================================================================
# MAIN
# ============================================================================

if __name__ == '__main__':
    app = create_app()
    
    logger.info("=" * 60)
    logger.info("SAMUDRA RAKSHAK - Cloud Backend Server")
    logger.info("=" * 60)
    logger.info("Starting server...")
    logger.info("WebSocket endpoint: ws://0.0.0.0:8000/ws")
    logger.info("REST API: http://0.0.0.0:8000/api/")
    logger.info("Health check: http://0.0.0.0:8000/health")
    logger.info("=" * 60)
    
    web.run_app(app, host='0.0.0.0', port=8000)
