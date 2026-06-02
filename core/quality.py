from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

QUALITY_CHECKS = {
    "product_manager": {
        "required_sections": ["title", "overview", "features", "acceptance_criteria"],
        "min_features": 1,
        "quality_prompt": """请检查以下PRD文档的质量，按0-10分评分。检查项：
1. 需求描述是否清晰完整
2. 功能清单是否足够详细
3. 验收标准是否可量化
4. 是否考虑了边界情况
5. 优先级是否合理

PRD文档：
{content}

请仅输出一个JSON：{{"score": 数字, "issues": ["问题1", "问题2"], "passed": true/false}}
passed为true当且仅当score>=7。"""
    },
    "ui_designer": {
        "required_sections": ["design_system", "pages", "components"],
        "min_pages": 1,
        "quality_prompt": """请检查以下UI设计规范的质量，按0-10分评分。检查项：
1. 设计系统是否完整（颜色、字体、间距）
2. 页面设计是否覆盖所有功能
3. 组件设计是否可复用
4. 交互流程是否清晰

UI设计规范：
{content}

请仅输出一个JSON：{{"score": 数字, "issues": ["问题1", "问题2"], "passed": true/false}}
passed为true当且仅当score>=7。"""
    },
    "backend_developer": {
        "required_sections": ["api_design", "db_schema", "files"],
        "min_apis": 1,
        "quality_prompt": """请检查以下后端设计的质量，按0-10分评分。检查项：
1. API设计是否RESTful
2. 数据库设计是否合理
3. 代码是否完整可运行
4. 是否包含错误处理
5. 是否有安全防护

后端设计：
{content}

请仅输出一个JSON：{{"score": 数字, "issues": ["问题1", "问题2"], "passed": true/false}}
passed为true当且仅当score>=7。"""
    },
    "frontend_developer": {
        "required_sections": ["pages", "files"],
        "min_pages": 1,
        "quality_prompt": """请检查以下前端代码的质量，按0-10分评分。检查项：
1. 页面是否覆盖所有功能
2. 代码是否完整可运行
3. 组件是否可复用
4. API调用层是否完善
5. 交互逻辑是否完整

前端代码：
{content}

请仅输出一个JSON：{{"score": 数字, "issues": ["问题1", "问题2"], "passed": true/false}}
passed为true当且仅当score>=7。"""
    },
    "tester": {
        "required_sections": ["test_cases", "bugs", "summary", "all_passed"],
        "quality_prompt": """请检查以下测试报告的质量，按0-10分评分。检查项：
1. 测试用例是否覆盖所有功能
2. Bug描述是否清晰
3. 测试结论是否合理

测试报告：
{content}

请仅输出一个JSON：{{"score": 数字, "issues": ["问题1", "问题2"], "passed": true/false}}
passed为true当且仅当score>=7。"""
    },
    "security_auditor": {
        "required_sections": ["vulnerabilities", "summary", "all_passed"],
        "quality_prompt": """请检查以下安全审计报告的质量，按0-10分评分。检查项：
1. 是否覆盖OWASP Top 10
2. 漏洞描述是否详细
3. 修复建议是否可行

安全审计报告：
{content}

请仅输出一个JSON：{{"score": 数字, "issues": ["问题1", "问题2"], "passed": true/false}}
passed为true当且仅当score>=7。"""
    },
}


class QualityChecker:
    def __init__(self, max_retries: int = 1):
        self.max_retries = max_retries
        self.quality_log: list[dict] = []

    def check_structure(self, agent_name: str, result: Any) -> dict:
        if agent_name not in QUALITY_CHECKS:
            return {"passed": True, "score": 10, "issues": []}

        checks = QUALITY_CHECKS[agent_name]
        issues = []
        score = 10

        if isinstance(result, dict):
            for section in checks.get("required_sections", []):
                if section not in result or not result[section]:
                    issues.append(f"缺少必要字段: {section}")
                    score -= 2

            min_items = checks.get("min_features", checks.get("min_apis", checks.get("min_pages", 0)))
            if min_items > 0:
                items = result.get("features", result.get("api_design", result.get("pages", [])))
                if isinstance(items, list) and len(items) < min_items:
                    issues.append(f"项目数量不足: 需要{min_items}个，实际{len(items)}个")
                    score -= 2

        passed = score >= 7 and len(issues) == 0
        return {"passed": passed, "score": max(score, 0), "issues": issues}

    async def llm_check(self, agent_name: str, result: Any, provider) -> dict:
        if agent_name not in QUALITY_CHECKS:
            return {"passed": True, "score": 10, "issues": []}

        checks = QUALITY_CHECKS[agent_name]
        content = json.dumps(result, ensure_ascii=False, indent=2) if isinstance(result, (dict, list)) else str(result)

        prompt = checks["quality_prompt"].format(content=content[:3000])

        try:
            import re
            messages = [
                {"role": "system", "content": "你是一个质量检查专家，只输出JSON格式的评分结果。"},
                {"role": "user", "content": prompt},
            ]
            response = await provider.chat_with_retry(messages, temperature=0.3, max_tokens=500)

            json_str = response.strip()
            if json_str.startswith("```"):
                match = re.search(r'```(?:json)?\s*\n?(.*?)\n?\s*```', json_str, re.DOTALL)
                if match:
                    json_str = match.group(1).strip()

            quality_result = json.loads(json_str)
            return {
                "passed": quality_result.get("passed", True),
                "score": quality_result.get("score", 10),
                "issues": quality_result.get("issues", []),
            }
        except Exception as e:
            logger.warning(f"LLM quality check failed for {agent_name}: {e}")
            return {"passed": True, "score": 10, "issues": []}

    def log_quality(self, agent_name: str, check_result: dict, retry_count: int = 0):
        self.quality_log.append({
            "agent": agent_name,
            "score": check_result.get("score", 0),
            "passed": check_result.get("passed", False),
            "issues": check_result.get("issues", []),
            "retry_count": retry_count,
        })
