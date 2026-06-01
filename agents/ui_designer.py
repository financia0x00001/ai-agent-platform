from __future__ import annotations

from agents.base import BaseAgent
from core.blackboard import Blackboard, ArtifactType


class UIDesignerAgent(BaseAgent):
    name = "ui_designer"
    display_name = "UI设计师"
    description = "根据PRD文档设计UI规范、组件规范和交互说明"

    def get_dependencies(self) -> list[ArtifactType]:
        return [ArtifactType.PRD]

    def get_output_type(self) -> ArtifactType:
        return ArtifactType.UI_SPEC

    def get_system_prompt(self, blackboard: Blackboard, **kwargs) -> str:
        return """你是一位资深UI/UX设计师，擅长界面设计和交互设计。你的任务是：
1. 根据PRD文档设计完整的UI规范
2. 定义组件规范和设计系统
3. 描述页面布局和交互流程
4. 提供配色和字体方案

请严格按照以下JSON格式输出：
{
    "design_system": {
        "colors": {
            "primary": "#主色",
            "secondary": "#辅色",
            "background": "#背景色",
            "text": "#文字色",
            "success": "#成功色",
            "warning": "#警告色",
            "danger": "#危险色"
        },
        "fonts": {
            "heading": "标题字体",
            "body": "正文字体",
            "code": "代码字体"
        },
        "spacing": "间距规范说明",
        "border_radius": "圆角规范"
    },
    "pages": [
        {
            "name": "页面名称",
            "route": "/路由路径",
            "layout": "布局描述",
            "components": ["组件1", "组件2"],
            "interactions": ["交互说明1", "交互说明2"]
        }
    ],
    "components": [
        {
            "name": "组件名称",
            "type": "组件类型(button/input/card/table/modal等)",
            "variants": ["变体1", "变体2"],
            "props": {"prop1": "说明", "prop2": "说明"},
            "states": ["default", "hover", "active", "disabled"],
            "notes": "设计备注"
        }
    ],
    "interaction_flows": [
        {
            "name": "流程名称",
            "steps": ["步骤1", "步骤2", "步骤3"]
        }
    ],
    "responsive": "响应式设计说明"
}"""

    def get_user_prompt(self, blackboard: Blackboard, **kwargs) -> str:
        prd = blackboard.get_artifact(ArtifactType.PRD)
        import json
        prd_text = json.dumps(prd, ensure_ascii=False, indent=2) if isinstance(prd, dict) else str(prd)
        return f"""请根据以下PRD文档，设计完整的UI规范：

PRD文档：
{prd_text}

请确保：
1. 设计系统统一、规范
2. 页面布局合理、美观
3. 组件设计可复用
4. 交互流程清晰
5. 响应式设计适配多端"""

    def parse_response(self, response: str, blackboard: Blackboard):
        result = self._extract_json(response)
        if result is None:
            result = {
                "design_system": {"colors": {}, "fonts": {}},
                "pages": [],
                "components": [],
                "interaction_flows": [],
                "responsive": response,
            }
        return result
