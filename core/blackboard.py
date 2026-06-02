from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Coroutine
import asyncio


class Phase(str, Enum):
    REQUIREMENT = "requirement"
    DESIGN_DEV = "design_dev"
    QA = "qa"
    FIX = "fix"
    DONE = "done"


class ArtifactType(str, Enum):
    USER_REQUIREMENT = "user_requirement"
    PRD = "prd"
    UI_SPEC = "ui_spec"
    API_DESIGN = "api_design"
    DB_SCHEMA = "db_schema"
    FRONTEND_CODE = "frontend_code"
    BACKEND_CODE = "backend_code"
    TEST_REPORT = "test_report"
    SECURITY_REPORT = "security_report"
    BUG_LIST = "bug_list"
    FIX_HISTORY = "fix_history"
    NEGOTIATION_LOG = "negotiation_log"
    USAGE_REPORT = "usage_report"


class ApprovalPoint(str, Enum):
    AFTER_PRD = "after_prd"
    AFTER_DESIGN = "after_design"
    AFTER_FRONTEND = "after_frontend"


@dataclass
class ApprovalStatus:
    point: str
    status: str = "pending"
    feedback: str = ""
    history: list[dict] = field(default_factory=list)
    snapshots: list[dict] = field(default_factory=list)


@dataclass
class Artifact:
    artifact_type: ArtifactType
    content: Any
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)


@dataclass
class AgentStatus:
    name: str
    display_name: str
    phase: Phase
    status: str = "waiting"
    progress: int = 0
    message: str = ""
    started_at: float | None = None
    finished_at: float | None = None


APPROVAL_POINT_INFO = {
    ApprovalPoint.AFTER_PRD: {
        "label": "PRD审批",
        "description": "产品经理已完成需求分析，请审核PRD文档",
        "review_artifacts": ["prd"],
    },
    ApprovalPoint.AFTER_DESIGN: {
        "label": "设计审批",
        "description": "UI设计和后端API已完成，请审核设计方案",
        "review_artifacts": ["ui_spec", "api_design", "db_schema", "backend_code"],
    },
    ApprovalPoint.AFTER_FRONTEND: {
        "label": "前端审批",
        "description": "前端开发已完成，请审核前端代码",
        "review_artifacts": ["frontend_code"],
    },
}


class Blackboard:
    def __init__(self, project_id: str):
        self.project_id = project_id
        self.artifacts: dict[str, Artifact] = {}
        self.agent_statuses: dict[str, AgentStatus] = {}
        self.current_phase: Phase = Phase.REQUIREMENT
        self.fix_round: int = 0
        self.logs: list[dict] = []
        self.negotiation_log: list[dict] = []
        self._event_callbacks: list[Callable] = []
        # 缓存检测：记录每个 Agent 上次运行时的输入指纹，避免重复调用
        self._input_fingerprints: dict[str, str] = {}
        self._cache_stats: dict[str, int] = {"hits": 0, "skipped_calls": 0, "tokens_saved_est": 0}

        self.approval_enabled: bool = True
        self.approvals: dict[str, ApprovalStatus] = {
            ApprovalPoint.AFTER_PRD.value: ApprovalStatus(point=ApprovalPoint.AFTER_PRD.value),
            ApprovalPoint.AFTER_DESIGN.value: ApprovalStatus(point=ApprovalPoint.AFTER_DESIGN.value),
            ApprovalPoint.AFTER_FRONTEND.value: ApprovalStatus(point=ApprovalPoint.AFTER_FRONTEND.value),
        }
        self.current_approval: str | None = None
        self._approval_event: asyncio.Event | None = None
        self._approval_decision: dict | None = None

        self._init_agent_statuses()

    def _init_agent_statuses(self):
        agents = [
            ("product_manager", "产品经理", Phase.REQUIREMENT),
            ("ui_designer", "UI设计师", Phase.DESIGN_DEV),
            ("backend_developer", "后端开发", Phase.DESIGN_DEV),
            ("frontend_developer", "前端开发", Phase.DESIGN_DEV),
            ("qa_engineer", "质量工程师", Phase.QA),
        ]
        for name, display, phase in agents:
            self.agent_statuses[name] = AgentStatus(
                name=name, display_name=display, phase=phase
            )

    def on_event(self, callback: Callable):
        self._event_callbacks.append(callback)

    async def emit_event(self, event_type: str, data: dict):
        event = {
            "type": event_type,
            "project_id": self.project_id,
            "timestamp": time.time(),
            **data,
        }
        self.logs.append(event)
        for cb in self._event_callbacks:
            try:
                if asyncio.iscoroutinefunction(cb):
                    await cb(event)
                else:
                    cb(event)
            except Exception:
                pass

    def set_artifact(self, artifact_type: ArtifactType | str, content: Any):
        key = artifact_type.value if isinstance(artifact_type, ArtifactType) else artifact_type
        now = time.time()
        if key in self.artifacts:
            self.artifacts[key].content = content
            self.artifacts[key].updated_at = now
        else:
            try:
                at = ArtifactType(key) if isinstance(artifact_type, str) else artifact_type
            except ValueError:
                at = ArtifactType.NEGOTIATION_LOG
            self.artifacts[key] = Artifact(
                artifact_type=at,
                content=content,
                created_at=now,
                updated_at=now,
            )

    def get_artifact(self, artifact_type: ArtifactType | str) -> Any | None:
        key = artifact_type.value if isinstance(artifact_type, ArtifactType) else artifact_type
        art = self.artifacts.get(key)
        return art.content if art else None

    def update_agent_status(self, agent_name: str, status: str, progress: int = 0, message: str = ""):
        if agent_name in self.agent_statuses:
            s = self.agent_statuses[agent_name]
            s.status = status
            s.progress = progress
            s.message = message
            if status == "running" and s.started_at is None:
                s.started_at = time.time()
            if status in ("completed", "failed"):
                s.finished_at = time.time()

    async def wait_for_approval(self, point: ApprovalPoint) -> dict:
        if not self.approval_enabled:
            return {"action": "approve"}

        self.current_approval = point.value
        approval = self.approvals[point.value]
        approval.status = "pending"

        info = APPROVAL_POINT_INFO[point]
        await self.emit_event("approval_required", {
            "point": point.value,
            "label": info["label"],
            "description": info["description"],
            "review_artifacts": info["review_artifacts"],
        })

        snapshot = {
            "timestamp": time.time(),
            "action": "pending",
            "artifacts": {k: {"type": v.artifact_type.value, "content_hash": hash(str(v.content))} for k, v in self.artifacts.items()},
        }

        self._approval_event = asyncio.Event()
        await self._approval_event.wait()

        decision = self._approval_decision or {"action": "approve"}
        self.current_approval = None
        self._approval_decision = None

        approval.history.append({
            "action": decision.get("action"),
            "feedback": decision.get("feedback", ""),
            "timestamp": time.time(),
        })

        snapshot["action"] = decision.get("action", "")
        snapshot["feedback"] = decision.get("feedback", "")
        snapshot["artifacts_content"] = {k: v.content for k, v in self.artifacts.items()}
        approval.snapshots.append(snapshot)

        if decision.get("action") == "approve":
            approval.status = "approved"
        elif decision.get("action") == "reject":
            approval.status = "rejected"
        elif decision.get("action") == "rerun":
            approval.status = "rerun"

        await self.emit_event("approval_decided", {
            "point": point.value,
            "action": decision.get("action"),
            "feedback": decision.get("feedback", ""),
        })

        return decision

    def resolve_approval(self, action: str, feedback: str = "", rerun_agents: list[str] | None = None):
        self._approval_decision = {
            "action": action,
            "feedback": feedback,
            "rerun_agents": rerun_agents or [],
        }
        if self._approval_event:
            self._approval_event.set()

    def add_negotiation(self, from_agent: str, to_agent: str, issue: str, suggestion: str) -> dict:
        entry = {
            "from_agent": from_agent,
            "to_agent": to_agent,
            "issue": issue,
            "suggestion": suggestion,
            "timestamp": time.time(),
            "resolved": False,
        }
        self.negotiation_log.append(entry)
        asyncio.ensure_future(self.emit_event("negotiation_raised", entry))
        return entry

    def resolve_negotiation(self, index: int):
        self.negotiation_log[index]["resolved"] = True
        asyncio.ensure_future(self.emit_event("negotiation_resolved", {
            "from_agent": self.negotiation_log[index]["from_agent"],
            "to_agent": self.negotiation_log[index]["to_agent"],
        }))

    def is_qa_passed(self) -> bool:
        """检查测试和安全审计是否都通过"""
        test = self.get_artifact(ArtifactType.TEST_REPORT)
        security = self.get_artifact(ArtifactType.SECURITY_REPORT)
        test_ok = test.get("all_passed", False) if isinstance(test, dict) else bool(test)
        sec_ok = security.get("all_passed", False) if isinstance(security, dict) else bool(security)
        return test_ok and sec_ok

    def get_status_summary(self) -> dict:
        return {
            "project_id": self.project_id,
            "current_phase": self.current_phase.value,
            "fix_round": self.fix_round,
            "approval_enabled": self.approval_enabled,
            "current_approval": self.current_approval,
            "approvals": {
                k: {
                    "point": v.point,
                    "status": v.status,
                    "feedback": v.feedback,
                    "history_count": len(v.history),
                }
                for k, v in self.approvals.items()
            },
            "agents": {
                name: {
                    "display_name": s.display_name,
                    "status": s.status,
                    "progress": s.progress,
                    "message": s.message,
                    "phase": s.phase.value,
                }
                for name, s in self.agent_statuses.items()
            },
            "artifacts": list(self.artifacts.keys()),
            "negotiation_log": self.negotiation_log,
        }

    def input_fingerprint(self, agent_name: str, dependencies: list[ArtifactType]) -> str:
        """计算输入指纹：对依赖产出物做SHA256，检测输入是否变化"""
        import hashlib
        parts = []
        for dep in sorted(dependencies, key=lambda d: d.value):
            artifact = self.get_artifact(dep)
            if artifact is not None:
                parts.append(json.dumps(artifact, ensure_ascii=False, sort_keys=True))
        raw = '|'.join(parts)
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def check_and_update_fingerprint(self, agent_name: str, fingerprint: str, est_tokens: int = 6000) -> bool:
        """检查输入指纹是否变化。返回 True 表示相同（可跳过），False 表示需执行"""
        prev = self._input_fingerprints.get(agent_name)
        self._input_fingerprints[agent_name] = fingerprint
        if prev == fingerprint:
            self._cache_stats["hits"] += 1
            self._cache_stats["skipped_calls"] += 1
            self._cache_stats["tokens_saved_est"] += est_tokens
            return True
        return False

    def get_cache_stats(self) -> dict:
        """获取输入去重统计"""
        return dict(self._cache_stats)

    def to_dict(self) -> dict:
        return {
            "project_id": self.project_id,
            "current_phase": self.current_phase.value,
            "fix_round": self.fix_round,
            "approval_enabled": self.approval_enabled,
            "current_approval": self.current_approval,
            "approvals": {
                k: {"status": v.status, "history_count": len(v.history)}
                for k, v in self.approvals.items()
            },
            "artifacts": {k: {"content": v.content, "type": v.artifact_type.value} for k, v in self.artifacts.items()},
            "agent_statuses": {
                name: {
                    "display_name": s.display_name,
                    "status": s.status,
                    "progress": s.progress,
                    "message": s.message,
                }
                for name, s in self.agent_statuses.items()
            },
            "logs": self.logs[-100:],
            "negotiation_log": self.negotiation_log,
        }
