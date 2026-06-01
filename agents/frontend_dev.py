from __future__ import annotations

import json

from agents.base import BaseAgent
from core.blackboard import Blackboard, ArtifactType


class FrontendDeveloperAgent(BaseAgent):
    name = "frontend_developer"
    display_name = "前端开发"
    description = "根据PRD和UI规范实现前端页面和组件代码"

    def get_dependencies(self) -> list[ArtifactType]:
        return [ArtifactType.PRD, ArtifactType.UI_SPEC]

    def get_output_type(self) -> ArtifactType:
        return ArtifactType.FRONTEND_CODE

    def get_system_prompt(self, blackboard: Blackboard, **kwargs) -> str:
        is_fix = kwargs.get("is_fix", False)
        if is_fix:
            return """你是一位资深前端开发工程师。现在需要你根据测试报告修复前端代码中的问题。

请严格按照以下JSON格式输出修复后的完整代码：
{
    "pages": [
        {
            "name": "页面名称",
            "route": "/路由",
            "code": "修复后的完整页面代码（HTML+CSS+JS）"
        }
    ],
    "components": [
        {
            "name": "组件名称",
            "code": "修复后的完整组件代码"
        }
    ],
    "fix_summary": ["修复说明1", "修复说明2"]
}"""
        return """你是一位资深前端开发工程师，擅长现代前端开发。你的任务是：
1. 根据PRD和UI规范实现前端页面
2. 实现可复用的前端组件
3. 实现API调用层和状态管理
4. 实现路由配置

请严格按照以下JSON格式输出：
{
    "pages": [
        {
            "name": "页面名称",
            "route": "/路由",
            "code": "完整的页面代码（HTML+CSS+JS）"
        }
    ],
    "components": [
        {
            "name": "组件名称",
            "code": "完整的组件代码"
        }
    ],
    "api_layer": "API调用层代码",
    "router": "路由配置代码",
    "tech_stack": ["使用的技术栈"],
    "notes": ["实现备注"]
}"""

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
            current_code_text = json.dumps(current_code, ensure_ascii=False, indent=2) if isinstance(current_code, dict) else str(current_code)

            return f"""请修复以下前端代码中的问题：

当前前端代码：
{current_code_text}

测试报告：
{json.dumps(test_report, ensure_ascii=False, indent=2) if test_report else '无'}

安全审计报告：
{json.dumps(security_report, ensure_ascii=False, indent=2) if security_report else '无'}

请修复所有发现的问题，并输出修复后的完整代码。"""

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
5. 代码风格统一、注释清晰"""

    def parse_response(self, response: str, blackboard: Blackboard):
        result = self._extract_json(response)
        if result is None:
            result = {
                "pages": [],
                "components": [],
                "api_layer": response,
                "router": "",
                "tech_stack": [],
                "notes": [],
            }
        return result
