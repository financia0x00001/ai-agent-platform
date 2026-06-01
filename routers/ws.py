from __future__ import annotations

import asyncio
import json
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import Dict, Set

logger = logging.getLogger("uvicorn")

router = APIRouter(tags=["WebSocket"])

HEARTBEAT_INTERVAL = 30  # 服务端心跳间隔(秒)，低于大部分代理超时(60s)
HEARTBEAT_TIMEOUT = 90   # 客户端无响应超时


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
            for ws in list(self.active[project_id]):
                try:
                    await ws.send_text(message)
                except Exception:
                    dead.add(ws)
            if dead:
                self.active[project_id] -= dead

    async def send_safe(self, websocket: WebSocket, data: dict) -> bool:
        """安全发送消息，连接断开时返回 False 而非抛异常"""
        try:
            await websocket.send_text(json.dumps(data, ensure_ascii=False))
            return True
        except Exception:
            return False


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
        # 安全发送 init_status，客户端可能已断开
        await manager.send_safe(websocket, {"type": "init_status", **status})

        if not blackboard._event_callbacks:
            blackboard.on_event(get_ws_callback(project_id))

    # 启动服务端心跳任务
    heartbeat_task = asyncio.create_task(
        _heartbeat_loop(websocket, project_id)
    )

    try:
        while True:
            try:
                data = await asyncio.wait_for(
                    websocket.receive_text(), timeout=HEARTBEAT_TIMEOUT
                )
            except asyncio.TimeoutError:
                # 客户端太久没发消息（包括心跳），主动断开
                logger.warning(f"WebSocket heartbeat timeout for project {project_id}")
                break

            try:
                msg = json.loads(data)
                if msg.get("type") == "ping":
                    await manager.send_safe(websocket, {"type": "pong"})
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"WebSocket error for project {project_id}: {e}")
    finally:
        heartbeat_task.cancel()
        try:
            await heartbeat_task
        except asyncio.CancelledError:
            pass
        manager.disconnect(project_id, websocket)


async def _heartbeat_loop(websocket: WebSocket, project_id: str):
    """服务端主动发送心跳 ping，保持代理/NAT 连接活跃"""
    while True:
        await asyncio.sleep(HEARTBEAT_INTERVAL)
        success = await manager.send_safe(websocket, {"type": "ping"})
        if not success:
            logger.warning(f"Heartbeat failed for project {project_id}, closing")
            break
