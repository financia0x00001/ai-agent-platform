from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ProjectFile:
    path: str
    content: str
    description: str = ""


class DeliveryPackager:
    def __init__(self, artifacts: dict[str, Any], project_name: str = "project"):
        self.artifacts = artifacts
        self.project_name = self._safe_name(project_name)

    def _safe_name(self, name: str) -> str:
        return re.sub(r'[^\w\u4e00-\u9fff\-]', '_', name).strip('_') or "project"

    def package(self) -> list[ProjectFile]:
        files = []
        files.extend(self._generate_docs())
        files.extend(self._generate_backend())
        files.extend(self._generate_frontend())
        files.extend(self._generate_config())
        files.append(self._generate_delivery_report())
        return files

    def _generate_docs(self) -> list[ProjectFile]:
        files = []
        prd = self.artifacts.get("prd")
        if prd:
            files.append(ProjectFile(
                path=f"{self.project_name}/docs/PRD.md",
                content=self._dict_to_markdown(prd, "产品需求文档 (PRD)"),
                description="产品需求文档",
            ))

        ui_spec = self.artifacts.get("ui_spec")
        if ui_spec:
            files.append(ProjectFile(
                path=f"{self.project_name}/docs/UI_SPEC.md",
                content=self._dict_to_markdown(ui_spec, "UI设计规范"),
                description="UI设计规范",
            ))

        api_design = self.artifacts.get("api_design")
        if api_design:
            files.append(ProjectFile(
                path=f"{self.project_name}/docs/API.md",
                content=self._dict_to_markdown(api_design, "API接口文档"),
                description="API接口文档",
            ))

        db_schema = self.artifacts.get("db_schema")
        if db_schema:
            files.append(ProjectFile(
                path=f"{self.project_name}/docs/DATABASE.md",
                content=f"# 数据库设计\n\n{db_schema}" if isinstance(db_schema, str) else self._dict_to_markdown(db_schema, "数据库设计"),
                description="数据库设计文档",
            ))

        test_report = self.artifacts.get("test_report")
        if test_report:
            files.append(ProjectFile(
                path=f"{self.project_name}/docs/TEST_REPORT.md",
                content=self._dict_to_markdown(test_report, "测试报告"),
                description="测试报告",
            ))

        security_report = self.artifacts.get("security_report")
        if security_report:
            files.append(ProjectFile(
                path=f"{self.project_name}/docs/SECURITY_REPORT.md",
                content=self._dict_to_markdown(security_report, "安全审计报告"),
                description="安全审计报告",
            ))

        return files

    def _generate_backend(self) -> list[ProjectFile]:
        files = []
        backend = self.artifacts.get("backend_code")
        if not backend:
            return files

        if isinstance(backend, dict):
            code = backend.get("code", "")
            if code:
                files.append(ProjectFile(
                    path=f"{self.project_name}/backend/app/main.py",
                    content=self._extract_code(code),
                    description="后端主程序",
                ))

            api_design = backend.get("api_design") or self.artifacts.get("api_design")
            if api_design:
                files.append(ProjectFile(
                    path=f"{self.project_name}/backend/app/api_routes.py",
                    content=self._generate_api_routes(api_design),
                    description="API路由定义",
                ))

            db_schema = backend.get("db_schema") or self.artifacts.get("db_schema")
            if db_schema:
                files.append(ProjectFile(
                    path=f"{self.project_name}/backend/app/models.py",
                    content=self._generate_models(db_schema),
                    description="数据模型",
                ))

            files.append(ProjectFile(
                path=f"{self.project_name}/backend/requirements.txt",
                content="fastapi==0.115.6\nuvicorn[standard]==0.34.0\npydantic==2.10.4\nsqlalchemy==2.0.36\npython-dotenv==1.0.1\n",
                description="后端依赖",
            ))

            files.append(ProjectFile(
                path=f"{self.project_name}/backend/README.md",
                content=f"# {self.project_name} - 后端服务\n\n## 启动\n\n```bash\ncd backend\npip install -r requirements.txt\npython -m uvicorn app.main:app --reload\n```\n",
                description="后端说明",
            ))
        else:
            files.append(ProjectFile(
                path=f"{self.project_name}/backend/app/main.py",
                content=self._extract_code(str(backend)),
                description="后端主程序",
            ))

        return files

    def _generate_frontend(self) -> list[ProjectFile]:
        files = []
        frontend = self.artifacts.get("frontend_code")
        if not frontend:
            return files

        if isinstance(frontend, dict):
            pages = frontend.get("pages", [])
            for i, page in enumerate(pages):
                if isinstance(page, dict):
                    name = page.get("name", f"page_{i}")
                    code = page.get("code", "")
                    route = page.get("route", f"/{name}")
                    safe_name = self._safe_name(name)
                    files.append(ProjectFile(
                        path=f"{self.project_name}/frontend/pages/{safe_name}.html",
                        content=self._extract_code(code),
                        description=f"页面: {name} ({route})",
                    ))

            components = frontend.get("components", [])
            for i, comp in enumerate(components):
                if isinstance(comp, dict):
                    name = comp.get("name", f"component_{i}")
                    code = comp.get("code", "")
                    safe_name = self._safe_name(name)
                    files.append(ProjectFile(
                        path=f"{self.project_name}/frontend/components/{safe_name}.html",
                        content=self._extract_code(code),
                        description=f"组件: {name}",
                    ))

            api_layer = frontend.get("api_layer", "")
            if api_layer:
                files.append(ProjectFile(
                    path=f"{self.project_name}/frontend/js/api.js",
                    content=self._extract_code(api_layer),
                    description="API调用层",
                ))

            router = frontend.get("router", "")
            if router:
                files.append(ProjectFile(
                    path=f"{self.project_name}/frontend/js/router.js",
                    content=self._extract_code(router),
                    description="路由配置",
                ))

            files.append(ProjectFile(
                path=f"{self.project_name}/frontend/README.md",
                content=f"# {self.project_name} - 前端项目\n\n## 使用\n\n直接用浏览器打开 `pages/` 目录下的HTML文件即可。\n",
                description="前端说明",
            ))
        else:
            files.append(ProjectFile(
                path=f"{self.project_name}/frontend/index.html",
                content=self._extract_code(str(frontend)),
                description="前端页面",
            ))

        return files

    def _generate_config(self) -> list[ProjectFile]:
        files = []

        readme_content = f"# {self.project_name}\n\n"
        readme_content += "## 项目说明\n\n本项目由AI智能体协作平台自动生成。\n\n"
        readme_content += "## 目录结构\n\n```\n{project_name}/\n├── docs/           # 文档\n"
        readme_content += "│   ├── PRD.md          # 产品需求文档\n│   ├── UI_SPEC.md      # UI设计规范\n"
        readme_content += "│   ├── API.md          # API接口文档\n│   └── DATABASE.md     # 数据库设计\n"
        readme_content += "├── backend/        # 后端代码\n│   ├── app/\n│   │   ├── main.py      # 主程序\n"
        readme_content += "│   │   ├── api_routes.py # API路由\n│   │   └── models.py    # 数据模型\n"
        readme_content += "│   └── requirements.txt\n├── frontend/       # 前端代码\n"
        readme_content += "│   ├── pages/          # 页面\n│   ├── components/     # 组件\n"
        readme_content += "│   └── js/             # JS脚本\n└── DELIVERY.md     # 交付报告\n```\n"

        files.append(ProjectFile(
            path=f"{self.project_name}/README.md",
            content=readme_content,
            description="项目说明",
        ))

        return files

    def _generate_delivery_report(self) -> ProjectFile:
        prd = self.artifacts.get("prd", {})
        test_report = self.artifacts.get("test_report", {})
        security_report = self.artifacts.get("security_report", {})

        prd_title = prd.get("title", "未命名项目") if isinstance(prd, dict) else "未命名项目"

        test_summary = test_report.get("summary", {}) if isinstance(test_report, dict) else {}
        sec_summary = security_report.get("summary", {}) if isinstance(security_report, dict) else {}

        test_passed = test_report.get("all_passed", True) if isinstance(test_report, dict) else True
        sec_passed = security_report.get("all_passed", True) if isinstance(security_report, dict) else True

        features = prd.get("features", []) if isinstance(prd, dict) else []
        bugs = test_report.get("bugs", []) if isinstance(test_report, dict) else []
        vulns = security_report.get("vulnerabilities", []) if isinstance(security_report, dict) else []

        report = f"""# 交付报告

## 项目: {prd_title}

---

### 一、项目概述

{prd.get('overview', '无概述') if isinstance(prd, dict) else '无概述'}

### 二、功能清单

| # | 功能 | 优先级 | 复杂度 |
|---|------|--------|--------|
"""
        for i, f in enumerate(features, 1):
            if isinstance(f, dict):
                report += f"| {i} | {f.get('name', '-')} | {f.get('priority', '-')} | {f.get('complexity', '-')} |\n"

        report += f"""
### 三、测试结果

- **总用例数**: {test_summary.get('total_cases', 0)}
- **通过**: {test_summary.get('passed', 0)}
- **失败**: {test_summary.get('failed', 0)}
- **严重Bug**: {test_summary.get('critical_bugs', 0)}
- **一般Bug**: {test_summary.get('major_bugs', 0)}
- **轻微Bug**: {test_summary.get('minor_bugs', 0)}
- **测试结论**: {'✅ 全部通过' if test_passed else '❌ 存在问题'}

### 四、安全审计

- **漏洞总数**: {sec_summary.get('total_vulnerabilities', 0)}
- **严重**: {sec_summary.get('critical', 0)}
- **高危**: {sec_summary.get('high', 0)}
- **中危**: {sec_summary.get('medium', 0)}
- **低危**: {sec_summary.get('low', 0)}
- **审计结论**: {'✅ 全部通过' if sec_passed else '❌ 存在风险'}

### 五、Bug清单

"""
        for b in bugs:
            if isinstance(b, dict):
                report += f"- **[{b.get('severity', '?')}]** {b.get('title', '-')}: {b.get('description', '-')}\n"

        report += "\n### 六、安全漏洞\n\n"
        for v in vulns:
            if isinstance(v, dict):
                report += f"- **[{v.get('severity', '?')}]** {v.get('title', '-')}: {v.get('description', '-')}\n"

        report += f"""
### 七、交付物清单

- 📄 产品需求文档 (docs/PRD.md)
- 🎨 UI设计规范 (docs/UI_SPEC.md)
- 🔌 API接口文档 (docs/API.md)
- 🗄️ 数据库设计 (docs/DATABASE.md)
- 💻 后端代码 (backend/)
- 🌐 前端代码 (frontend/)
- 🧪 测试报告 (docs/TEST_REPORT.md)
- 🔒 安全审计报告 (docs/SECURITY_REPORT.md)

### 八、交付结论

**{'✅ 项目通过所有测试和安全审计，可以交付' if test_passed and sec_passed else '⚠️ 项目存在待解决问题，建议修复后再交付'}**

---
*本报告由AI智能体协作平台自动生成*
"""
        return ProjectFile(
            path=f"{self.project_name}/DELIVERY.md",
            content=report,
            description="交付报告",
        )

    def _dict_to_markdown(self, data: Any, title: str) -> str:
        if isinstance(data, str):
            return f"# {title}\n\n{data}"
        return f"# {title}\n\n```json\n{json.dumps(data, ensure_ascii=False, indent=2)}\n```"

    def _extract_code(self, text: str) -> str:
        if not text:
            return ""
        pattern = r'```(?:\w+)?\s*\n(.*?)```'
        matches = re.findall(pattern, text, re.DOTALL)
        if matches:
            longest = max(matches, key=len)
            return longest.strip()
        return text.strip()

    def _generate_api_routes(self, api_design: Any) -> str:
        if not api_design:
            return ""
        lines = ["from fastapi import APIRouter, HTTPException", "from pydantic import BaseModel", "from typing import Optional, List", "", "router = APIRouter()", ""]
        if isinstance(api_design, list):
            for api in api_design:
                if isinstance(api, dict):
                    method = api.get("method", "GET").lower()
                    path = api.get("path", "/")
                    desc = api.get("description", "")
                    lines.append(f"# {desc}")
                    func_name = path.strip("/").replace("/", "_").replace("-", "_") or "root"
                    if method == "get":
                        lines.append(f"@router.get('{path}')")
                    elif method == "post":
                        lines.append(f"@router.post('{path}')")
                    elif method == "put":
                        lines.append(f"@router.put('{path}')")
                    elif method == "delete":
                        lines.append(f"@router.delete('{path}')")
                    lines.append(f"async def {func_name}():")
                    lines.append(f"    \"\"\"{desc}\"\"\"")
                    lines.append(f"    pass")
                    lines.append("")
        return "\n".join(lines)

    def _generate_models(self, db_schema: Any) -> str:
        if not db_schema:
            return ""
        if isinstance(db_schema, str):
            return f"\"\"\"数据库模型\n\n{db_schema}\n\"\"\"\n\nfrom sqlalchemy import Column, Integer, String, Text, DateTime, Boolean\nfrom sqlalchemy.ext.declarative import declarative_base\n\nBase = declarative_base()\n"
        return f"\"\"\"数据库模型\"\"\"\n\nfrom sqlalchemy import Column, Integer, String, Text, DateTime, Boolean\nfrom sqlalchemy.ext.declarative import declarative_base\n\nBase = declarative_base()\n\n# {json.dumps(db_schema, ensure_ascii=False, indent=2)}\n"
