from __future__ import annotations

from agents.base import BaseAgent
from core.blackboard import Blackboard, ArtifactType


class ProductManagerAgent(BaseAgent):
    name = "product_manager"
    display_name = "产品经理"
    description = "分析用户需求，输出PRD文档、功能清单和验收标准"

    def get_dependencies(self) -> list[ArtifactType]:
        return [ArtifactType.USER_REQUIREMENT]

    def get_output_type(self) -> ArtifactType:
        return ArtifactType.PRD

    def get_system_prompt(self, blackboard: Blackboard, **kwargs) -> str:
        return """你是一位资深产品经理，擅长需求分析和产品规划。你的任务是：
1. 深入理解用户需求
2. 输出完整的PRD文档
3. 拆解功能清单并按优先级排序
4. 定义验收标准

请严格按照以下JSON格式输出：
{
    "title": "项目名称",
    "overview": "项目概述",
    "user_stories": [
        {"id": "US001", "story": "作为...我希望...以便...", "priority": "高/中/低", "acceptance": "验收标准"}
    ],
    "features": [
        {"id": "F001", "name": "功能名称", "description": "功能描述", "priority": "高/中/低", "complexity": "高/中/低"}
    ],
    "non_functional": ["非功能需求1", "非功能需求2"],
    "constraints": ["技术约束1", "技术约束2"],
    "acceptance_criteria": ["整体验收标准1", "整体验收标准2"],
    "api_requirements": ["需要的API接口1", "需要的API接口2"],
    "data_requirements": ["数据需求1", "数据需求2"]
}"""

    def get_user_prompt(self, blackboard: Blackboard, **kwargs) -> str:
        requirement = blackboard.get_artifact(ArtifactType.USER_REQUIREMENT)
        return f"""请分析以下用户需求，输出完整的PRD文档：

用户需求：
{requirement}

请确保：
1. 需求分析全面，不遗漏关键功能
2. 用户故事符合INVEST原则
3. 功能优先级合理
4. 验收标准可量化、可测试
5. 考虑边界情况和异常流程"""

    def parse_response(self, response: str, blackboard: Blackboard):
        result = self._extract_json(response)
        if result is None:
            result = {
                "title": "项目需求",
                "overview": response,
                "user_stories": [],
                "features": [],
                "non_functional": [],
                "constraints": [],
                "acceptance_criteria": [],
                "api_requirements": [],
                "data_requirements": [],
            }
        return result
