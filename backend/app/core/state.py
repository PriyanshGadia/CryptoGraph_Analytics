import asyncio
from typing import List
from fastapi import WebSocket

class WebSocketConnectionManager:
    def __init__(self):
        self.predictions_clients: List[WebSocket] = []
        self.screener_clients: List[WebSocket] = []
        self.predictions_lock = asyncio.Lock()
        self.screener_lock = asyncio.Lock()
        self.prediction_refresh_event = asyncio.Event()

ws_manager = WebSocketConnectionManager()

class SchedulerState:
    def __init__(self):
        self.status = "idle"
        self.last_run = None
        self.last_duration_sec = 0.0
        self.last_result = None
        self.is_running = False

scheduler_state = SchedulerState()
trading_lock = asyncio.Lock()
