from __future__ import annotations

import json

from agents.base import BaseAgent
from core.blackboard import Blackboard, ArtifactType
from core.cache import ContextCompressor


class BackendDeveloperAgent(BaseAgent):
    name = "backend_developer"
    display_name = "后端开发"
    description = "根据PRD文档设计API接口、数据库Schema并实现后端代码"
    required_fields = {"api_design": [], "db_schema": "", "files": []}
    can_negotiate = True

    def get_dependencies(self) -> list[ArtifactType]:
        return [ArtifactType.PRD]

    def get_output_type(self) -> ArtifactType:
        return ArtifactType.BACKEND_CODE

    def get_system_prompt(self, blackboard: Blackboard, **kwargs) -> str:
        is_fix = kwargs.get("is_fix", False)
        if is_fix:
            return """你是一位资深后端开发工程师。现在需要你根据测试报告和安全审计报告修复代码中的问题。

【重要】每个文件的content必须是完整的、可直接运行的代码，不能省略任何部分，不能用...或# 省略代替。代码必须包含完整的import语句、错误处理、数据验证。

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
    "files": [
        {"path": "app/main.py", "content": "完整的main.py文件内容，包含所有import和完整实现", "description": "后端主程序入口"},
        {"path": "app/models.py", "content": "完整的models.py文件内容", "description": "数据模型定义"},
        {"path": "app/api_routes.py", "content": "完整的api_routes.py文件内容", "description": "API路由定义"},
        {"path": "app/database.py", "content": "完整的database.py文件内容", "description": "数据库连接配置"},
        {"path": "requirements.txt", "content": "完整的依赖列表", "description": "Python依赖"},
        {"path": ".env.example", "content": "完整的环境变量示例", "description": "环境变量模板"}
    ],
    "fix_summary": ["修复说明1", "修复说明2"]
}"""
        return """你是一位资深后端开发工程师，擅长API设计和后端开发。你的任务是：
1. 设计RESTful API接口
2. 设计数据库Schema
3. 实现后端业务逻辑代码

【重要规则】
- 每个文件的content必须是完整的、可直接运行的代码，不能省略任何部分，不能用...或# 省略代替
- 代码必须包含完整的import语句、错误处理、数据验证
- 每个文件都必须是可以独立运行的完整代码，不要只写片段

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
    "files": [
        {"path": "app/main.py", "content": "完整的main.py文件内容，包含所有import和完整实现", "description": "后端主程序入口"},
        {"path": "app/models.py", "content": "完整的models.py文件内容", "description": "数据模型定义"},
        {"path": "app/api_routes.py", "content": "完整的api_routes.py文件内容", "description": "API路由定义"},
        {"path": "app/database.py", "content": "完整的database.py文件内容", "description": "数据库连接配置"},
        {"path": "requirements.txt", "content": "完整的依赖列表", "description": "Python依赖"},
        {"path": ".env.example", "content": "完整的环境变量示例", "description": "环境变量模板"}
    ],
    "tech_stack": ["使用的技术栈"],
    "notes": ["实现备注"],
    "negotiations": [
        {"to_agent": "product_manager", "issue": "问题描述", "suggestion": "建议修改方案"},
        {"to_agent": "ui_designer", "issue": "问题描述", "suggestion": "建议修改方案"},
        {"to_agent": "frontend_developer", "issue": "问题描述", "suggestion": "建议修改方案"}
    ]
}

协商机制：如果你在实现后端代码时发现PRD需求不明确、UI设计影响API设计、或前端需要配合调整等问题，请在输出的JSON中添加"negotiations"字段：
"negotiations": [
    {"to_agent": "product_manager", "issue": "问题描述", "suggestion": "建议修改方案"},
    {"to_agent": "ui_designer", "issue": "问题描述", "suggestion": "建议修改方案"},
    {"to_agent": "frontend_developer", "issue": "问题描述", "suggestion": "建议修改方案"}
]
你可以对产品经理、UI设计师或前端开发提出协商请求。如果没有问题，则不需要添加此字段。"""

    def get_user_prompt(self, blackboard: Blackboard, **kwargs) -> str:
        is_fix = kwargs.get("is_fix", False)
        prd = blackboard.get_artifact(ArtifactType.PRD)
        prd_text = json.dumps(prd, ensure_ascii=False, indent=2) if isinstance(prd, dict) else str(prd)

        if is_fix:
            test_report = blackboard.get_artifact(ArtifactType.TEST_REPORT)
            security_report = blackboard.get_artifact(ArtifactType.SECURITY_REPORT)
            current_code = blackboard.get_artifact(ArtifactType.BACKEND_CODE)
            current_code_text = ContextCompressor.summarize_for_fix(current_code)
            test_text = ContextCompressor.summarize_for_fix(test_report)
            security_text = ContextCompressor.summarize_for_fix(security_report)

            return f"""请修复以下后端代码中的问题：

当前后端代码：
{current_code_text}

测试报告：
{test_text}

安全审计报告：
{security_text}

请修复所有发现的问题，并输出修复后的完整代码。请确保每个文件都是完整的、可直接运行的代码。不要省略任何import、函数实现或错误处理。"""

        return f"""请根据以下PRD文档，设计API接口、数据库Schema并实现后端代码：

PRD文档：
{prd_text}

请确保：
1. API设计遵循RESTful规范
2. 数据库设计合理，考虑索引和关系
3. 代码使用Python FastAPI框架
4. 包含错误处理和数据验证
5. 考虑安全性（参数校验、SQL注入防护等）

请确保每个文件都是完整的、可直接运行的代码。不要省略任何import、函数实现或错误处理。"""

    def parse_response(self, response: str, blackboard: Blackboard):
        result = self._extract_json(response)
        if result is None:
            result = {
                "api_design": [],
                "db_schema": "",
                "files": [{"path": "app/main.py", "content": response, "description": "后端主程序"}],
                "tech_stack": [],
                "notes": [],
            }

        if "api_design" in result:
            blackboard.set_artifact(ArtifactType.API_DESIGN, result["api_design"])
        if "db_schema" in result:
            blackboard.set_artifact(ArtifactType.DB_SCHEMA, result["db_schema"])

        if "code" in result and "files" not in result:
            result["files"] = [{"path": "app/main.py", "content": result["code"], "description": "后端主程序"}]

        return result
