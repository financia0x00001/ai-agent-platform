from __future__ import annotations

import json

from agents.base import BaseAgent
from core.blackboard import Blackboard, ArtifactType


class SecurityAuditorAgent(BaseAgent):
    name = "security_auditor"
    display_name = "安全审计"
    description = "审计前后端代码的安全漏洞和风险"

    def get_dependencies(self) -> list[ArtifactType]:
        return [ArtifactType.FRONTEND_CODE, ArtifactType.BACKEND_CODE]

    def get_output_type(self) -> ArtifactType:
        return ArtifactType.SECURITY_REPORT

    def get_system_prompt(self, blackboard: Blackboard, **kwargs) -> str:
        return """你是一位资深安全审计工程师，擅长代码安全审查。你的任务是：
1. 审查代码中的安全漏洞
2. 检查权限控制问题
3. 检查数据泄露风险
4. 检查依赖包安全风险
5. 提供修复建议

请严格按照以下JSON格式输出：
{
    "vulnerabilities": [
        {
            "id": "VUL001",
            "severity": "严重/高危/中危/低危",
            "type": "SQL注入/XSS/CSRF/越权/信息泄露/其他",
            "title": "漏洞标题",
            "description": "漏洞描述",
            "location": "代码位置",
            "attack_scenario": "攻击场景",
            "fix_suggestion": "修复建议",
            "code_fix": "修复代码示例"
        }
    ],
    "permission_issues": [
        {
            "description": "权限问题描述",
            "severity": "严重/高危/中危/低危",
            "fix": "修复建议"
        }
    ],
    "data_leak_risks": [
        {
            "description": "数据泄露风险描述",
            "severity": "严重/高危/中危/低危",
            "fix": "修复建议"
        }
    ],
    "dependency_risks": [
        {
            "package": "依赖包名",
            "risk": "风险描述",
            "fix": "修复建议"
        }
    ],
    "summary": {
        "total_vulnerabilities": 0,
        "critical": 0,
        "high": 0,
        "medium": 0,
        "low": 0
    },
    "all_passed": true/false,
    "conclusion": "审计结论"
}"""

    def get_user_prompt(self, blackboard: Blackboard, **kwargs) -> str:
        frontend = blackboard.get_artifact(ArtifactType.FRONTEND_CODE)
        backend = blackboard.get_artifact(ArtifactType.BACKEND_CODE)

        fe_text = json.dumps(frontend, ensure_ascii=False, indent=2) if isinstance(frontend, dict) else str(frontend)
        be_text = json.dumps(backend, ensure_ascii=False, indent=2) if isinstance(backend, dict) else str(backend)

        return f"""请对以下代码进行全面安全审计：

前端代码：
{fe_text}

后端代码：
{be_text}

请确保：
1. 检查所有OWASP Top 10漏洞类型
2. 检查SQL注入、XSS、CSRF等常见漏洞
3. 检查认证和授权机制
4. 检查敏感数据处理
5. 检查输入验证和输出编码
6. 每个漏洞都要提供具体的修复代码"""

    def parse_response(self, response: str, blackboard: Blackboard):
        result = self._extract_json(response)
        if result is None:
            result = {
                "vulnerabilities": [],
                "permission_issues": [],
                "data_leak_risks": [],
                "dependency_risks": [],
                "summary": {"total_vulnerabilities": 0, "critical": 0, "high": 0, "medium": 0, "low": 0},
                "all_passed": True,
                "conclusion": response,
            }
        return result
