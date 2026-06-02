from __future__ import annotations

import json

from agents.base import BaseAgent
from core.blackboard import Blackboard, ArtifactType
from core.cache import ContextCompressor


class FrontendDeveloperAgent(BaseAgent):
    name = "frontend_developer"
    display_name = "前端开发"
    description = "根据PRD和UI规范实现前端页面和组件代码"
    required_fields = {"pages": [], "files": []}
    can_negotiate = True

    def get_dependencies(self) -> list[ArtifactType]:
        return [ArtifactType.PRD, ArtifactType.UI_SPEC]

    def get_output_type(self) -> ArtifactType:
        return ArtifactType.FRONTEND_CODE

    def get_system_prompt(self, blackboard: Blackboard, **kwargs) -> str:
        is_fix = kwargs.get("is_fix", False)
        if is_fix:
            return """你是一位资深前端开发工程师。现在需要你根据测试报告修复前端代码中的问题。

【重要】每个文件的content必须是完整的、可直接运行的代码，不能省略任何部分，不能用...或# 省略代替。代码必须包含完整的HTML结构、CSS样式和JavaScript逻辑。

请严格按照以下JSON格式输出修复后的完整代码：
{
    "pages": [
        {
            "name": "页面名称",
            "route": "/路由",
            "files": [
                {"path": "pages/index.html", "content": "完整的HTML文件内容", "description": "页面描述"}
            ]
        }
    ],
    "components": [
        {
            "name": "组件名称",
            "files": [
                {"path": "components/Header.html", "content": "完整的组件代码", "description": "组件描述"}
            ]
        }
    ],
    "files": [
        {"path": "js/api.js", "content": "完整的API调用层代码", "description": "API调用层"},
        {"path": "js/router.js", "content": "完整的路由配置代码", "description": "路由配置"},
        {"path": "css/style.css", "content": "完整的样式表代码", "description": "全局样式"},
        {"path": "index.html", "content": "完整的入口HTML文件", "description": "入口页面"}
    ],
    "fix_summary": ["修复说明1", "修复说明2"]
}"""
        return """你是一位资深前端开发工程师，擅长现代前端开发。你的任务是：
1. 根据PRD和UI规范实现前端页面
2. 实现可复用的前端组件
3. 实现API调用层和状态管理
4. 实现路由配置

【重要规则】
- 每个文件的content必须是完整的、可直接运行的代码，不能省略任何部分，不能用...或# 省略代替
- 代码必须包含完整的HTML结构、CSS样式和JavaScript逻辑
- 每个文件都必须是可以独立运行的完整代码，不要只写片段

请严格按照以下JSON格式输出：
{
    "pages": [
        {
            "name": "页面名称",
            "route": "/路由",
            "files": [
                {"path": "pages/index.html", "content": "完整的HTML文件内容", "description": "页面描述"}
            ]
        }
    ],
    "components": [
        {
            "name": "组件名称",
            "files": [
                {"path": "components/Header.html", "content": "完整的组件代码", "description": "组件描述"}
            ]
        }
    ],
    "files": [
        {"path": "js/api.js", "content": "完整的API调用层代码", "description": "API调用层"},
        {"path": "js/router.js", "content": "完整的路由配置代码", "description": "路由配置"},
        {"path": "css/style.css", "content": "完整的样式表代码", "description": "全局样式"},
        {"path": "index.html", "content": "完整的入口HTML文件", "description": "入口页面"}
    ],
    "tech_stack": ["使用的技术栈"],
    "notes": ["实现备注"],
    "negotiations": [
        {
            "to_agent": "backend_developer",
            "issue": "问题描述",
            "suggestion": "建议修改方案"
        }
    ]
}

协商机制：如果你在实现前端代码时发现API设计存在问题（如接口缺失、字段不合理、请求方式不当等），请在输出的JSON中添加"negotiations"字段：
"negotiations": [
    {
        "to_agent": "backend_developer",
        "issue": "问题描述",
        "suggestion": "建议修改方案"
    }
]
你可以对后端开发或UI设计师提出协商请求。如果没有问题，则不需要添加此字段。"""

    def get_user_prompt(self, blackboard: Blackboard, **kwargs) -> str:
        is_fix = kwargs.get("is_fix", False)
        prd = blackboard.get_artifact(ArtifactType.PRD)
        ui_spec = blackboard.get_artifact(ArtifactType.UI_SPEC)
        api_design = blackboard.get_artifact(ArtifactType.API_DESIGN)

        prd_text = json.dumps(prd, ensure_ascii=False, indent=2) if isinstance(prd, dict) else str(prd)
        ui_text = json.dumps(ui_spec, ensure_ascii=False, indent=2) if isinstance(ui_spec, dict) else str(ui_spec) if ui_spec else "暂无UI规范"
        api_text = json.dumps(api_design, ensure_ascii=False, indent=2) if isinstance(api_design, (dict, list)) else str(api_design) if api_design else "暂无API设计"

        if is_fix:
            test_report = blackboard.get_artifact(ArtifactType.TEST_REPORT)
            security_report = blackboard.get_artifact(ArtifactType.SECURITY_REPORT)
            current_code = blackboard.get_artifact(ArtifactType.FRONTEND_CODE)
            current_code_text = ContextCompressor.summarize_for_fix(current_code)
            test_text = ContextCompressor.summarize_for_fix(test_report)
            security_text = ContextCompressor.summarize_for_fix(security_report)

            return f"""请修复以下前端代码中的问题：

当前前端代码：
{current_code_text}

测试报告：
{test_text}

安全审计报告：
{security_text}

请修复所有发现的问题，并输出修复后的完整代码。请确保每个文件都是完整的、可直接运行的代码。不要省略任何HTML结构、CSS样式或JavaScript逻辑。"""

        return f"""请根据以下PRD文档和UI规范，实现前端代码：

PRD文档：
{prd_text}

UI设计规范：
{ui_text}

API接口设计：
{api_text}

请确保：
1. 页面布局符合UI规范
2. 组件可复用、可维护
3. API调用层封装完善
4. 交互逻辑完整
5. 代码风格统一、注释清晰

请确保每个文件都是完整的、可直接运行的代码。不要省略任何HTML结构、CSS样式或JavaScript逻辑。"""

    def parse_response(self, response: str, blackboard: Blackboard):
        result = self._extract_json(response)
        if result is None:
            result = {
                "pages": [],
                "components": [],
                "files": [{"path": "index.html", "content": response, "description": "前端页面"}],
                "tech_stack": [],
                "notes": [],
            }

        if "pages" in result:
            for page in result["pages"]:
                if isinstance(page, dict) and "code" in page and "files" not in page:
                    page["files"] = [{"path": f"pages/{self._safe_name(page.get('name', 'page'))}.html", "content": page["code"], "description": f"页面: {page.get('name', '')}"}]

        if "components" in result:
            for comp in result["components"]:
                if isinstance(comp, dict) and "code" in comp and "files" not in comp:
                    comp["files"] = [{"path": f"components/{self._safe_name(comp.get('name', 'component'))}.html", "content": comp["code"], "description": f"组件: {comp.get('name', '')}"}]

        if "files" not in result:
            result["files"] = []

        old_fields = []
        if "api_layer" in result and result["api_layer"]:
            result["files"].append({"path": "js/api.js", "content": result["api_layer"], "description": "API调用层"})
            old_fields.append("api_layer")
        if "router" in result and result["router"]:
            result["files"].append({"path": "js/router.js", "content": result["router"], "description": "路由配置"})
            old_fields.append("router")

        return result

    @staticmethod
    def _safe_name(name: str) -> str:
        import re
        return re.sub(r'[^\w\u4e00-\u9fff\-]', '_', name).strip('_') or "untitled"
