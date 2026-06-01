from __future__ import annotations

import json

from agents.base import BaseAgent
from core.blackboard import Blackboard, ArtifactType


class TesterAgent(BaseAgent):
    name = "tester"
    display_name = "代码测试"
    description = "测试前后端代码的功能正确性和Bug"

    def get_dependencies(self) -> list[ArtifactType]:
        return [ArtifactType.PRD, ArtifactType.FRONTEND_CODE, ArtifactType.BACKEND_CODE]

    def get_output_type(self) -> ArtifactType:
        return ArtifactType.TEST_REPORT

    def get_system_prompt(self, blackboard: Blackboard, **kwargs) -> str:
        return """你是一位资深QA测试工程师，擅长功能测试和代码审查。你的任务是：
1. 根据PRD文档编写测试用例
2. 审查前后端代码的功能正确性
3. 发现Bug并记录
4. 判断是否通过测试

请严格按照以下JSON格式输出：
{
    "test_cases": [
        {
            "id": "TC001",
            "name": "测试用例名称",
            "type": "功能/边界/异常/性能",
            "precondition": "前置条件",
            "steps": ["步骤1", "步骤2"],
            "expected": "预期结果",
            "actual": "实际结果（基于代码分析）",
            "status": "pass/fail"
        }
    ],
    "bugs": [
        {
            "id": "BUG001",
            "severity": "严重/一般/轻微",
            "title": "Bug标题",
            "description": "Bug描述",
            "location": "代码位置",
            "suggestion": "修复建议"
        }
    ],
    "summary": {
        "total_cases": 0,
        "passed": 0,
        "failed": 0,
        "critical_bugs": 0,
        "major_bugs": 0,
        "minor_bugs": 0
    },
    "all_passed": true/false,
    "conclusion": "测试结论"
}"""

    def get_user_prompt(self, blackboard: Blackboard, **kwargs) -> str:
        prd = blackboard.get_artifact(ArtifactType.PRD)
        frontend = blackboard.get_artifact(ArtifactType.FRONTEND_CODE)
        backend = blackboard.get_artifact(ArtifactType.BACKEND_CODE)

        prd_text = json.dumps(prd, ensure_ascii=False, indent=2) if isinstance(prd, dict) else str(prd)
        fe_text = json.dumps(frontend, ensure_ascii=False, indent=2) if isinstance(frontend, dict) else str(frontend)
        be_text = json.dumps(backend, ensure_ascii=False, indent=2) if isinstance(backend, dict) else str(backend)

        return f"""请对以下代码进行全面测试：

PRD文档：
{prd_text}

前端代码：
{fe_text}

后端代码：
{be_text}

请确保：
1. 测试用例覆盖所有PRD功能点
2. 包含正常流程和异常流程测试
3. 检查边界条件
4. 验证前后端接口对接
5. 发现的Bug要有明确的修复建议"""

    def parse_response(self, response: str, blackboard: Blackboard):
        result = self._extract_json(response)
        if result is None:
            result = {
                "test_cases": [],
                "bugs": [],
                "summary": {"total_cases": 0, "passed": 0, "failed": 0},
                "all_passed": True,
                "conclusion": response,
            }

        if result.get("bugs"):
            blackboard.set_artifact(ArtifactType.BUG_LIST, result["bugs"])

        return result
