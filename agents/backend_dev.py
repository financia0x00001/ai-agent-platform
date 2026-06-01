from __future__ import annotations

import json

from agents.base import BaseAgent
from core.blackboard import Blackboard, ArtifactType


class BackendDeveloperAgent(BaseAgent):
    name = "backend_developer"
    display_name = "后端开发"
    description = "根据PRD文档设计API接口、数据库Schema并实现后端代码"

    def get_dependencies(self) -> list[ArtifactType]:
        return [ArtifactType.PRD]

    def get_output_type(self) -> ArtifactType:
        return ArtifactType.BACKEND_CODE

    def get_system_prompt(self, blackboard: Blackboard, **kwargs) -> str:
        is_fix = kwargs.get("is_fix", False)
        if is_fix:
            return """你是一位资深后端开发工程师。现在需要你根据测试报告和安全审计报告修复代码中的问题。

请严格按照以下JSON格式输出修复后的完整代码：
{
    "api_design": [
        {
            "method": "GET/POST/PUT/DELETE",
            "path": "/api/xxx",
            "description": "接口描述",
            "request": {"field": "type"},
            "response": {"field": "type"}
        }
    ],
    "db_schema": "数据库Schema描述",
    "code": "修复后的完整后端代码",
    "fix_summary": ["修复说明1", "修复说明2"]
}"""
        return """你是一位资深后端开发工程师，擅长API设计和后端开发。你的任务是：
1. 设计RESTful API接口
2. 设计数据库Schema
3. 实现后端业务逻辑代码

请严格按照以下JSON格式输出：
{
    "api_design": [
        {
            "method": "GET/POST/PUT/DELETE",
            "path": "/api/xxx",
            "description": "接口描述",
            "request": {"field": "type"},
            "response": {"field": "type"}
        }
    ],
    "db_schema": "数据库Schema描述（包含表名、字段、类型、关系）",
    "code": "完整的后端代码实现（Python FastAPI）",
    "tech_stack": ["使用的技术栈"],
    "notes": ["实现备注"]
}"""

    def get_user_prompt(self, blackboard: Blackboard, **kwargs) -> str:
        is_fix = kwargs.get("is_fix", False)
        prd = blackboard.get_artifact(ArtifactType.PRD)
        prd_text = json.dumps(prd, ensure_ascii=False, indent=2) if isinstance(prd, dict) else str(prd)

        if is_fix:
            test_report = blackboard.get_artifact(ArtifactType.TEST_REPORT)
            security_report = blackboard.get_artifact(ArtifactType.SECURITY_REPORT)
            current_code = blackboard.get_artifact(ArtifactType.BACKEND_CODE)
            current_code_text = json.dumps(current_code, ensure_ascii=False, indent=2) if isinstance(current_code, dict) else str(current_code)

            return f"""请修复以下后端代码中的问题：

当前后端代码：
{current_code_text}

测试报告：
{json.dumps(test_report, ensure_ascii=False, indent=2) if test_report else '无'}

安全审计报告：
{json.dumps(security_report, ensure_ascii=False, indent=2) if security_report else '无'}

请修复所有发现的问题，并输出修复后的完整代码。"""

        return f"""请根据以下PRD文档，设计API接口、数据库Schema并实现后端代码：

PRD文档：
{prd_text}

请确保：
1. API设计遵循RESTful规范
2. 数据库设计合理，考虑索引和关系
3. 代码使用Python FastAPI框架
4. 包含错误处理和数据验证
5. 考虑安全性（参数校验、SQL注入防护等）"""

    def parse_response(self, response: str, blackboard: Blackboard):
        result = self._extract_json(response)
        if result is None:
            result = {
                "api_design": [],
                "db_schema": "",
                "code": response,
                "tech_stack": [],
                "notes": [],
            }

        if "api_design" in result:
            blackboard.set_artifact(ArtifactType.API_DESIGN, result["api_design"])
        if "db_schema" in result:
            blackboard.set_artifact(ArtifactType.DB_SCHEMA, result["db_schema"])

        return result
