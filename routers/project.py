from __future__ import annotations

import uuid
import json
import asyncio
from datetime import datetime
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from config import PROJECTS_DIR
from core.blackboard import Blackboard
from core.orchestrator import Orchestrator
from core.persistence import save_project, load_project, load_all_projects, delete_project_file, restore_blackboard

router = APIRouter(prefix="/api/projects", tags=["项目管理"])

_projects: dict[str, dict] = {}
_orchestrators: dict[str, Orchestrator] = {}
_blackboards: dict[str, Blackboard] = {}


def _init_from_disk():
    for meta in load_all_projects():
        pid = meta.get("id")
        if pid:
            if meta.get("status") == "running":
                meta["status"] = "interrupted"
            _projects[pid] = meta
            bb = restore_blackboard(pid)
            if bb:
                _blackboards[pid] = bb


class ProjectCreate(BaseModel):
    name: str
    requirement: str
    llm_config_id: Optional[str] = None


@router.post("")
async def create_project(data: ProjectCreate):
    project_id = str(uuid.uuid4())
    project = {
        "id": project_id,
        "name": data.name,
        "requirement": data.requirement,
        "llm_config_id": data.llm_config_id,
        "status": "created",
        "created_at": datetime.now().isoformat(),
    }
    _projects[project_id] = project

    blackboard = Blackboard(project_id)
    _blackboards[project_id] = blackboard

    save_project(project_id, project, blackboard)

    return {"message": "项目创建成功", "project_id": project_id}


@router.get("")
async def list_projects():
    return {"projects": list(_projects.values())}


@router.get("/{project_id}")
async def get_project(project_id: str):
    if project_id not in _projects:
        raise HTTPException(status_code=404, detail="项目不存在")
    project = _projects[project_id]
    blackboard = _blackboards.get(project_id)
    status_summary = blackboard.get_status_summary() if blackboard else {}
    return {**project, "status_summary": status_summary}


@router.post("/{project_id}/start")
async def start_project(project_id: str):
    if project_id not in _projects:
        raise HTTPException(status_code=404, detail="项目不存在")

    if project_id in _orchestrators and _orchestrators[project_id].is_running:
        raise HTTPException(status_code=400, detail="项目正在运行中")

    project = _projects[project_id]
    project["status"] = "running"

    blackboard = _blackboards[project_id]

    llm_config = None
    if project.get("llm_config_id"):
        from core.llm_provider import get_provider_by_id
        provider = get_provider_by_id(project["llm_config_id"])
        if provider:
            llm_config = provider.config

    orchestrator = Orchestrator(blackboard, llm_config, project_meta=project)
    _orchestrators[project_id] = orchestrator

    asyncio.create_task(_run_project(project_id, orchestrator, project, blackboard))

    return {"message": "项目已启动", "project_id": project_id}


async def _run_project(project_id: str, orchestrator: Orchestrator, project: dict, blackboard: Blackboard):
    try:
        await orchestrator.run(project["requirement"])
        project["status"] = "completed"
    except Exception as e:
        project["status"] = "failed"
        project["error"] = str(e)
    finally:
        save_project(project_id, project, blackboard)


@router.post("/{project_id}/stop")
async def stop_project(project_id: str):
    if project_id not in _orchestrators:
        raise HTTPException(status_code=404, detail="项目不存在")
    _orchestrators[project_id].cancel()
    _projects[project_id]["status"] = "stopped"
    bb = _blackboards.get(project_id)
    if bb:
        save_project(project_id, _projects[project_id], bb)
    return {"message": "项目已停止"}


@router.get("/{project_id}/status")
async def get_project_status(project_id: str):
    blackboard = _blackboards.get(project_id)
    if not blackboard:
        raise HTTPException(status_code=404, detail="项目不存在")
    return blackboard.get_status_summary()


@router.get("/{project_id}/artifacts")
async def get_project_artifacts(project_id: str):
    blackboard = _blackboards.get(project_id)
    if not blackboard:
        raise HTTPException(status_code=404, detail="项目不存在")
    return {
        "artifacts": {
            k: {"type": v.artifact_type.value, "content": v.content, "updated_at": v.updated_at}
            for k, v in blackboard.artifacts.items()
        }
    }


@router.get("/{project_id}/artifacts/{artifact_type}")
async def get_artifact_detail(project_id: str, artifact_type: str):
    blackboard = _blackboards.get(project_id)
    if not blackboard:
        raise HTTPException(status_code=404, detail="项目不存在")
    content = blackboard.get_artifact(artifact_type)
    if content is None:
        raise HTTPException(status_code=404, detail="产出物不存在")
    return {"type": artifact_type, "content": content}


@router.get("/{project_id}/logs")
async def get_project_logs(project_id: str):
    blackboard = _blackboards.get(project_id)
    if not blackboard:
        raise HTTPException(status_code=404, detail="项目不存在")
    return {"logs": blackboard.logs}


@router.delete("/{project_id}")
async def delete_project(project_id: str):
    if project_id not in _projects:
        raise HTTPException(status_code=404, detail="项目不存在")
    if project_id in _orchestrators and _orchestrators[project_id].is_running:
        raise HTTPException(status_code=400, detail="项目正在运行中，无法删除")
    _projects.pop(project_id, None)
    _blackboards.pop(project_id, None)
    _orchestrators.pop(project_id, None)
    delete_project_file(project_id)
    return {"message": "项目已删除"}


@router.on_event("startup")
async def on_startup():
    _init_from_disk()
