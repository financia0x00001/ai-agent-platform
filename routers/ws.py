from __future__ import annotations

import asyncio
import json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import Dict, Set

router = APIRouter(tags=["WebSocket"])


class ConnectionManager:
    def __init__(self):
        self.active: Dict[str, Set[WebSocket]] = {}

    async def connect(self, project_id: str, websocket: WebSocket):
        await websocket.accept()
        if project_id not in self.active:
            self.active[project_id] = set()
        self.active[project_id].add(websocket)

    def disconnect(self, project_id: str, websocket: WebSocket):
        if project_id in self.active:
            self.active[project_id].discard(websocket)
            if not self.active[project_id]:
                del self.active[project_id]

    async def broadcast(self, project_id: str, data: dict):
        if project_id in self.active:
            message = json.dumps(data, ensure_ascii=False)
            dead = set()
            for ws in self.active[project_id]:
                try:
                    await ws.send_text(message)
                except Exception:
                    dead.add(ws)
            self.active[project_id] -= dead


manager = ConnectionManager()


def get_ws_callback(project_id: str):
    async def callback(event: dict):
        await manager.broadcast(project_id, event)
    return callback


@router.websocket("/ws/{project_id}")
async def websocket_endpoint(websocket: WebSocket, project_id: str):
    await manager.connect(project_id, websocket)

    from routers.project import _blackboards

    blackboard = _blackboards.get(project_id)
    if blackboard:
        status = blackboard.get_status_summary()
        await websocket.send_text(json.dumps({"type": "init_status", **status}, ensure_ascii=False))

        if not blackboard._event_callbacks:
            blackboard.on_event(get_ws_callback(project_id))

    try:
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                if msg.get("type") == "ping":
                    await websocket.send_text(json.dumps({"type": "pong"}))
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        manager.disconnect(project_id, websocket)
