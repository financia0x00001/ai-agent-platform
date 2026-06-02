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
                # 修正旧数据：已完成的项目若QA未通过，改为needs_review
                if meta.get("status") == "completed" and not bb.is_qa_passed():
                    meta["status"] = "needs_review"


class ProjectCreate(BaseModel):
    name: str
    requirement: str
    llm_config_id: Optional[str] = None


class ProjectFork(BaseModel):
    source_project_id: str
    name: str
    requirement: str = ""
    copy_artifacts: bool = True


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


@router.post("/fork")
async def fork_project(data: ProjectFork):
    if data.source_project_id not in _projects:
        raise HTTPException(status_code=404, detail="源项目不存在")

    source_bb = _blackboards.get(data.source_project_id)
    if not source_bb:
        raise HTTPException(status_code=404, detail="源项目数据不存在")

    project_id = str(uuid.uuid4())
    requirement = data.requirement or _projects[data.source_project_id].get("requirement", "")
    project = {
        "id": project_id,
        "name": data.name,
        "requirement": requirement,
        "llm_config_id": _projects[data.source_project_id].get("llm_config_id"),
        "status": "created",
        "created_at": datetime.now().isoformat(),
        "source_project_id": data.source_project_id,
    }
    _projects[project_id] = project

    blackboard = Blackboard(project_id)
    if data.copy_artifacts:
        for k, v in source_bb.artifacts.items():
            blackboard.set_artifact(k, v.content)

    _blackboards[project_id] = blackboard
    save_project(project_id, project, blackboard)

    return {"message": "项目已基于模板创建", "project_id": project_id, "copied_artifacts": list(blackboard.artifacts.keys())}


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
    blackboard = _blackboards[project_id]

    llm_config = None
    if project.get("llm_config_id"):
        from core.llm_provider import get_provider_by_id
        provider = get_provider_by_id(project["llm_config_id"])
        if provider:
            llm_config = provider.config

    orchestrator = Orchestrator(blackboard, llm_config, project_meta=project)
    _orchestrators[project_id] = orchestrator

    # 重置成本追踪（新一次运行）
    blackboard.set_artifact("usage_report", None)

    # needs_review 项目仅重跑 QA+修复，保留所有已有产出物
    if project["status"] == "needs_review":
        project["status"] = "running"
        asyncio.create_task(_retry_project(project_id, orchestrator, project, blackboard, llm_config))
    else:
        project["status"] = "running"
        asyncio.create_task(_run_project(project_id, orchestrator, project, blackboard, llm_config))

    return {"message": "项目已启动", "project_id": project_id}


async def _run_project(project_id: str, orchestrator: Orchestrator, project: dict, blackboard: Blackboard, llm_config: dict | None = None):
    try:
        await orchestrator.run(project["requirement"])
        _finalize_project_status(project_id, orchestrator, project, blackboard)
    except Exception as e:
        project["status"] = "failed"
        project["error"] = str(e)
    finally:
        save_project(project_id, project, blackboard)


async def _retry_project(project_id: str, orchestrator: Orchestrator, project: dict, blackboard: Blackboard, llm_config: dict | None = None):
    """仅重跑 QA + 修复，保留已有 PRD/设计/代码等产出物"""
    try:
        await orchestrator.retry_qa()
        _finalize_project_status(project_id, orchestrator, project, blackboard)
    except Exception as e:
        project["status"] = "failed"
        project["error"] = str(e)
    finally:
        save_project(project_id, project, blackboard)


def _finalize_project_status(project_id: str, orchestrator: Orchestrator, project: dict, blackboard: Blackboard):
    """统一处理项目完成后的状态判定和用量保存"""
    # 保存 LLM 用量报告
    usage = orchestrator.get_usage_summary()
    if usage:
        blackboard.set_artifact("usage_report", usage)

    if orchestrator._cancelled:
        if project.get("status") != "stopped":
            project["status"] = "interrupted"
    elif blackboard.is_qa_passed():
        project["status"] = "completed"
    else:
        project["status"] = "needs_review"


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


class ArtifactUpdate(BaseModel):
    content: str

@router.put("/{project_id}/artifacts/{artifact_type}")
async def update_artifact(project_id: str, artifact_type: str, data: ArtifactUpdate):
    """手动编辑产出物（审批阶段使用）"""
    blackboard = _blackboards.get(project_id)
    if not blackboard:
        raise HTTPException(status_code=404, detail="项目不存在")

    # 尝试解析为 JSON，保留原始结构
    try:
        parsed = json.loads(data.content)
    except json.JSONDecodeError:
        parsed = data.content

    blackboard.set_artifact(artifact_type, parsed)

    # 持久化
    project = _projects.get(project_id)
    if project:
        save_project(project_id, project, blackboard)

    return {"message": "产出物已更新", "type": artifact_type}


@router.get("/{project_id}/logs")
async def get_project_logs(project_id: str):
    blackboard = _blackboards.get(project_id)
    if not blackboard:
        raise HTTPException(status_code=404, detail="项目不存在")
    return {"logs": blackboard.logs}


@router.get("/{project_id}/negotiations")
async def get_negotiations(project_id: str):
    blackboard = _blackboards.get(project_id)
    if not blackboard:
        raise HTTPException(status_code=404, detail="项目不存在")
    return {"negotiations": blackboard.negotiation_log}


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
