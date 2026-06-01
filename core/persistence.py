from __future__ import annotations

import json
import time
from pathlib import Path

from config import PROJECTS_DIR
from core.blackboard import Blackboard, ArtifactType, Phase, ApprovalPoint


def _project_file(project_id: str) -> Path:
    return PROJECTS_DIR / f"{project_id}.json"


def save_project(project_id: str, project_meta: dict, blackboard: Blackboard):
    data = {
        "meta": project_meta,
        "artifacts": {},
        "status": blackboard.get_status_summary(),
    }
    for k, v in blackboard.artifacts.items():
        data["artifacts"][k] = {
            "type": v.artifact_type.value if hasattr(v.artifact_type, 'value') else str(v.artifact_type),
            "content": v.content,
            "updated_at": v.updated_at,
        }
    with open(_project_file(project_id), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_project(project_id: str) -> dict | None:
    pf = _project_file(project_id)
    if not pf.exists():
        return None
    with open(pf, "r", encoding="utf-8") as f:
        return json.load(f)


def load_all_projects() -> list[dict]:
    projects = []
    for pf in PROJECTS_DIR.glob("*.json"):
        try:
            with open(pf, "r", encoding="utf-8") as f:
                data = json.load(f)
            projects.append(data.get("meta", {}))
        except Exception:
            pass
    return projects


def delete_project_file(project_id: str):
    pf = _project_file(project_id)
    if pf.exists():
        pf.unlink()


def restore_blackboard(project_id: str) -> Blackboard | None:
    data = load_project(project_id)
    if not data:
        return None
    bb = Blackboard(project_id)
    for k, v in data.get("artifacts", {}).items():
        bb.set_artifact(k, v["content"])

    status = data.get("status", {})
    if status.get("current_phase"):
        try:
            bb.current_phase = Phase(status["current_phase"])
        except ValueError:
            pass
    if status.get("current_approval"):
        bb.current_approval = status["current_approval"]
    if status.get("approval_enabled") is not None:
        bb.approval_enabled = status["approval_enabled"]
    if status.get("approvals"):
        for point_key, point_data in status["approvals"].items():
            if point_key in bb.approvals:
                bb.approvals[point_key].status = point_data.get("status", "pending")

    return bb
