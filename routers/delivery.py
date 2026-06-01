from __future__ import annotations

import io
import json
import zipfile
from urllib.parse import quote
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from core.blackboard import ArtifactType
from core.delivery import DeliveryPackager
from routers.project import _blackboards, _projects

router = APIRouter(prefix="/api/delivery", tags=["交付管理"])


@router.get("/{project_id}/preview")
async def preview_delivery(project_id: str):
    if project_id not in _blackboards:
        raise HTTPException(status_code=404, detail="项目不存在")

    blackboard = _blackboards[project_id]
    project = _projects.get(project_id, {})
    project_name = project.get("name", "project")

    artifacts = {k: v.content for k, v in blackboard.artifacts.items()}
    packager = DeliveryPackager(artifacts, project_name)
    files = packager.package()

    return {
        "project_id": project_id,
        "project_name": project_name,
        "total_files": len(files),
        "files": [
            {
                "path": f.path,
                "description": f.description,
                "size": len(f.content),
            }
            for f in files
        ],
    }


@router.get("/{project_id}/download")
async def download_delivery(project_id: str):
    if project_id not in _blackboards:
        raise HTTPException(status_code=404, detail="项目不存在")

    blackboard = _blackboards[project_id]
    project = _projects.get(project_id, {})
    project_name = project.get("name", "project")

    artifacts = {k: v.content for k, v in blackboard.artifacts.items()}
    packager = DeliveryPackager(artifacts, project_name)
    files = packager.package()

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        for f in files:
            zf.writestr(f.path, f.content.encode('utf-8') if isinstance(f.content, str) else f.content)

    zip_buffer.seek(0)

    filename = f"{packager.project_name}.zip"
    encoded_filename = quote(filename)
    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}",
        },
    )


@router.get("/{project_id}/report")
async def delivery_report(project_id: str):
    if project_id not in _blackboards:
        raise HTTPException(status_code=404, detail="项目不存在")

    blackboard = _blackboards[project_id]
    project = _projects.get(project_id, {})
    project_name = project.get("name", "project")

    artifacts = {k: v.content for k, v in blackboard.artifacts.items()}
    packager = DeliveryPackager(artifacts, project_name)
    report_file = packager._generate_delivery_report()

    prd = artifacts.get("prd", {})
    test_report = artifacts.get("test_report", {})
    security_report = artifacts.get("security_report", {})

    prd_title = prd.get("title", "未命名项目") if isinstance(prd, dict) else "未命名项目"
    test_passed = test_report.get("all_passed", True) if isinstance(test_report, dict) else True
    sec_passed = security_report.get("all_passed", True) if isinstance(security_report, dict) else True

    test_summary = test_report.get("summary", {}) if isinstance(test_report, dict) else {}
    sec_summary = security_report.get("summary", {}) if isinstance(security_report, dict) else {}

    usage = artifacts.get("usage_report", {})

    return {
        "project_name": prd_title,
        "can_deliver": test_passed and sec_passed,
        "test_passed": test_passed,
        "security_passed": sec_passed,
        "test_summary": {
            "total": test_summary.get("total_cases", 0),
            "passed": test_summary.get("passed", 0),
            "failed": test_summary.get("failed", 0),
            "critical_bugs": test_summary.get("critical_bugs", 0),
        },
        "security_summary": {
            "total": sec_summary.get("total_vulnerabilities", 0),
            "critical": sec_summary.get("critical", 0),
            "high": sec_summary.get("high", 0),
            "medium": sec_summary.get("medium", 0),
            "low": sec_summary.get("low", 0),
        },
        "usage": usage if usage else {},
        "report_markdown": report_file.content,
        "artifacts_count": len(artifacts),
    }


@router.get("/{project_id}/file/{file_path:path}")
async def get_delivery_file(project_id: str, file_path: str):
    if project_id not in _blackboards:
        raise HTTPException(status_code=404, detail="项目不存在")

    blackboard = _blackboards[project_id]
    project = _projects.get(project_id, {})
    project_name = project.get("name", "project")

    artifacts = {k: v.content for k, v in blackboard.artifacts.items()}
    packager = DeliveryPackager(artifacts, project_name)
    files = packager.package()

    for f in files:
        if f.path == file_path or f.path == f"{project_name}/{file_path}":
            return {"path": f.path, "content": f.content, "description": f.description}

    raise HTTPException(status_code=404, detail="文件不存在")
