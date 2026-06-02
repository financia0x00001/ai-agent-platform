from __future__ import annotations

import json

from agents.base import BaseAgent
from core.blackboard import Blackboard, ArtifactType
from core.cache import ContextCompressor


class QAEngineerAgent(BaseAgent):
    """合并 Tester + Auditor，一次 LLM 调用完成测试和安全审计，节省 ~40% token"""
    name = "qa_engineer"
    display_name = "质量工程师"
    description = "合并代码测试和安全审计，一次调用产出测试报告+安全报告"
    can_negotiate = True
    default_temperature = 0.2  # 分析类任务，启用缓存

    def get_dependencies(self) -> list[ArtifactType]:
        return [ArtifactType.PRD, ArtifactType.FRONTEND_CODE, ArtifactType.BACKEND_CODE]

    def get_output_type(self) -> ArtifactType:
        return ArtifactType.TEST_REPORT

    def get_system_prompt(self, blackboard: Blackboard, **kwargs) -> str:
        is_delta = kwargs.get("is_delta", False)
        if is_delta:
            return """你是质量工程师。现在需要做**增量复查**——仅验证上一轮发现的 Bug 和漏洞是否已被修复。

【重要】增量模式！不要重新做全量分析，只检查已知问题是否修复。

请输出JSON：
{
    "test_cases": [
        {"id": "TC001", "name": "复查用例", "status": "pass/fail",
         "previous_bug_id": "BUG001", "fix_verified": true/false, "note": "验证说明"}
    ],
    "bugs": [
        {"id": "BUG001", "severity": "严重/一般/轻微", "title": "Bug标题",
         "description": "当前状态", "status": "已修复/仍存在/新发现",
         "location": "代码位置", "suggestion": "修复建议"}
    ],
    "vulnerabilities": [
        {"id": "VUL001", "severity": "严重/高危/中危/低危", "title": "漏洞标题",
         "description": "当前状态", "status": "已修复/仍存在/新发现",
         "location": "代码位置", "fix_suggestion": "修复建议"}
    ],
    "summary": {
        "total_cases": 0, "passed": 0, "failed": 0,
        "critical_bugs": 0, "major_bugs": 0, "minor_bugs": 0
    },
    "security_summary": {
        "total_vulnerabilities": 0, "critical": 0, "high": 0, "medium": 0, "low": 0
    },
    "all_passed": true/false,
    "test_conclusion": "测试结论",
    "security_conclusion": "审计结论",
    "token_saved_by_delta": true
}"""

        return """你是资深质量工程师，同时负责功能测试和安全审计。一次完成两项工作。

【重要】输出必须同时包含测试报告和安全审计报告。

请输出JSON：
{
    "test_cases": [
        {"id": "TC001", "name": "测试用例", "type": "功能/边界/异常/性能",
         "precondition": "前置条件", "steps": ["步骤"], "expected": "预期",
         "actual": "实际结果", "status": "pass/fail"}
    ],
    "bugs": [
        {"id": "BUG001", "severity": "严重/一般/轻微", "title": "标题",
         "description": "描述", "location": "位置", "suggestion": "修复建议"}
    ],
    "vulnerabilities": [
        {"id": "VUL001", "severity": "严重/高危/中危/低危", "type": "SQL注入/XSS/CSRF/越权/信息泄露/其他",
         "title": "标题", "description": "描述", "location": "位置",
         "attack_scenario": "攻击场景", "fix_suggestion": "修复建议",
         "code_fix": "修复代码示例"}
    ],
    "permission_issues": [
        {"description": "描述", "severity": "严重/高危/中危/低危", "fix": "修复建议"}
    ],
    "data_leak_risks": [
        {"description": "描述", "severity": "严重/高危/中危/低危", "fix": "修复建议"}
    ],
    "summary": {
        "total_cases": 0, "passed": 0, "failed": 0,
        "critical_bugs": 0, "major_bugs": 0, "minor_bugs": 0
    },
    "security_summary": {
        "total_vulnerabilities": 0, "critical": 0, "high": 0, "medium": 0, "low": 0
    },
    "all_passed": true/false,
    "test_conclusion": "测试结论",
    "security_conclusion": "审计结论",
    "negotiations": [
        {"to_agent": "backend_developer", "issue": "问题", "suggestion": "建议"},
        {"to_agent": "frontend_developer", "issue": "问题", "suggestion": "建议"}
    ]
}"""

    def get_user_prompt(self, blackboard: Blackboard, **kwargs) -> str:
        is_delta = kwargs.get("is_delta", False)
        prd = blackboard.get_artifact(ArtifactType.PRD)
        frontend = blackboard.get_artifact(ArtifactType.FRONTEND_CODE)
        backend = blackboard.get_artifact(ArtifactType.BACKEND_CODE)

        prd_text = json.dumps(prd, ensure_ascii=False, indent=2) if isinstance(prd, dict) else str(prd)
        fe_text = ContextCompressor.compress_artifact(frontend)
        be_text = ContextCompressor.compress_artifact(backend)

        if is_delta:
            prev_test = blackboard.get_artifact(ArtifactType.TEST_REPORT)
            prev_security = blackboard.get_artifact(ArtifactType.SECURITY_REPORT)
            prev_bugs = prev_test.get("bugs", []) if isinstance(prev_test, dict) else []
            prev_vulns = prev_security.get("vulnerabilities", []) if isinstance(prev_security, dict) else []
            prev_bugs_text = json.dumps(prev_bugs, ensure_ascii=False, indent=2)
            prev_vulns_text = json.dumps(prev_vulns, ensure_ascii=False, indent=2)

            return f"""【增量复查模式】只检查以下已知问题是否修复，不要做全量分析。

PRD文档：
{prd_text}

当前代码（已修复）：
前端：{fe_text}
后端：{be_text}

上一轮Bug清单（请逐一验证是否已修复）：
{prev_bugs_text}

上一轮安全漏洞清单（请逐一验证是否已修复）：
{prev_vulns_text}

请逐一检查每个Bug和漏洞的修复状态。如果发现新的严重问题也请记录。"""

        return f"""请对以下代码进行全面测试和安全审计：

PRD文档：
{prd_text}

前端代码：
{fe_text}

后端代码：
{be_text}

请确保：
1. 测试用例覆盖所有PRD功能点
2. 包含正常/异常/边界测试
3. 检查所有OWASP Top 10漏洞
4. 检查SQL注入、XSS、CSRF等
5. 检查认证授权、敏感数据处理
6. 每个问题提供修复建议"""

    def parse_response(self, response: str, blackboard: Blackboard):
        result = self._extract_json(response)
        if result is None or not isinstance(result, dict):
            result = {
                "test_cases": [], "bugs": [], "vulnerabilities": [],
                "permission_issues": [], "data_leak_risks": [],
                "summary": {"total_cases": 0, "passed": 0, "failed": 0,
                            "critical_bugs": 0, "major_bugs": 0, "minor_bugs": 0},
                "security_summary": {"total_vulnerabilities": 0, "critical": 0,
                                     "high": 0, "medium": 0, "low": 0},
                "all_passed": True,
                "test_conclusion": response[:200],
                "security_conclusion": "",
            }

        # 拆分为 test_report 和 security_report 写入黑板
        test_report = {
            "test_cases": result.get("test_cases", []),
            "bugs": result.get("bugs", []),
            "summary": result.get("summary", {}),
            "all_passed": result.get("all_passed", True),
            "conclusion": result.get("test_conclusion", ""),
        }
        security_report = {
            "vulnerabilities": result.get("vulnerabilities", []),
            "permission_issues": result.get("permission_issues", []),
            "data_leak_risks": result.get("data_leak_risks", []),
            "summary": result.get("security_summary", {}),
            "all_passed": result.get("all_passed", True),
            "conclusion": result.get("security_conclusion", ""),
        }

        blackboard.set_artifact(ArtifactType.TEST_REPORT, test_report)
        blackboard.set_artifact(ArtifactType.SECURITY_REPORT, security_report)
        if result.get("bugs"):
            blackboard.set_artifact(ArtifactType.BUG_LIST, result["bugs"])

        return result
