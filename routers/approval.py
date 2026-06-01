from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List

from core.blackboard import ApprovalPoint, APPROVAL_POINT_INFO
from routers.project import _blackboards, _projects, _orchestrators

router = APIRouter(prefix="/api/approval", tags=["审批管理"])


class ApprovalDecision(BaseModel):
    action: str
    feedback: str = ""
    rerun_agents: List[str] = []


@router.get("/{project_id}/status")
async def get_approval_status(project_id: str):
    blackboard = _blackboards.get(project_id)
    if not blackboard:
        raise HTTPException(status_code=404, detail="项目不存在")

    current = blackboard.current_approval
    result = {
        "approval_enabled": blackboard.approval_enabled,
        "current_approval": current,
        "approvals": {},
    }

    for k, v in blackboard.approvals.items():
        info = APPROVAL_POINT_INFO.get(ApprovalPoint(k), {})
        result["approvals"][k] = {
            "point": v.point,
            "status": v.status,
            "label": info.get("label", k),
            "description": info.get("description", ""),
            "review_artifacts": info.get("review_artifacts", []),
            "history_count": len(v.history),
        }

    if current:
        info = APPROVAL_POINT_INFO.get(ApprovalPoint(current), {})
        result["current_info"] = {
            "label": info.get("label", current),
            "description": info.get("description", ""),
            "review_artifacts": info.get("review_artifacts", []),
        }

    return result


@router.post("/{project_id}/decide")
async def make_approval_decision(project_id: str, decision: ApprovalDecision):
    blackboard = _blackboards.get(project_id)
    if not blackboard:
        raise HTTPException(status_code=404, detail="项目不存在")

    if not blackboard.current_approval:
        raise HTTPException(status_code=400, detail="当前没有待审批的内容")

    if decision.action not in ("approve", "reject", "rerun"):
        raise HTTPException(status_code=400, detail="无效的审批操作，支持: approve/reject/rerun")

    blackboard.resolve_approval(
        action=decision.action,
        feedback=decision.feedback,
        rerun_agents=decision.rerun_agents,
    )

    return {
        "message": f"审批操作已提交: {decision.action}",
        "action": decision.action,
    }


@router.post("/{project_id}/toggle")
async def toggle_approval(project_id: str):
    blackboard = _blackboards.get(project_id)
    if not blackboard:
        raise HTTPException(status_code=404, detail="项目不存在")

    blackboard.approval_enabled = not blackboard.approval_enabled
    return {
        "message": f"审批模式已{'开启' if blackboard.approval_enabled else '关闭'}",
        "approval_enabled": blackboard.approval_enabled,
    }


@router.get("/{project_id}/rerun-options/{approval_point}")
async def get_rerun_options(project_id: str, approval_point: str):
    options_map = {
        "after_prd": [
            {"name": "product_manager", "display_name": "产品经理", "description": "重新生成PRD文档"},
        ],
        "after_design": [
            {"name": "ui_designer", "display_name": "UI设计师", "description": "重新设计UI规范"},
            {"name": "backend_developer", "display_name": "后端开发", "description": "重新设计API和后端代码"},
            {"name": "ui_designer", "display_name": "UI设计师+后端开发", "description": "同时重跑UI和后端"},
        ],
        "after_frontend": [
            {"name": "frontend_developer", "display_name": "前端开发", "description": "重新实现前端代码"},
        ],
    }
    return {"options": options_map.get(approval_point, [])}
