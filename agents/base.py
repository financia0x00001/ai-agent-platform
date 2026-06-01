from __future__ import annotations

import json
import time
from abc import ABC, abstractmethod
from typing import Any

from core.blackboard import Blackboard, ArtifactType
from core.llm_provider import LLMProvider


class BaseAgent(ABC):
    name: str = ""
    display_name: str = ""
    description: str = ""

    @abstractmethod
    def get_system_prompt(self, blackboard: Blackboard, **kwargs) -> str:
        pass

    @abstractmethod
    def get_user_prompt(self, blackboard: Blackboard, **kwargs) -> str:
        pass

    @abstractmethod
    def get_dependencies(self) -> list[ArtifactType]:
        pass

    @abstractmethod
    def get_output_type(self) -> ArtifactType:
        pass

    @abstractmethod
    def parse_response(self, response: str, blackboard: Blackboard) -> Any:
        pass

    def can_execute(self, blackboard: Blackboard) -> bool:
        for dep in self.get_dependencies():
            if blackboard.get_artifact(dep) is None:
                return False
        return True

    async def run(self, provider: LLMProvider, blackboard: Blackboard, **kwargs):
        if not self.can_execute(blackboard) and not kwargs.get("feedback"):
            blackboard.update_agent_status(self.name, "skipped", 0, "依赖未就绪")
            return None

        feedback = kwargs.get("feedback", "")
        status_msg = "根据反馈修改中..." if feedback else "正在分析输入..."
        blackboard.update_agent_status(self.name, "running", 10, status_msg)
        await blackboard.emit_event("agent_start", {
            "agent": self.name,
            "display_name": self.display_name,
        })

        try:
            system_prompt = self.get_system_prompt(blackboard, **kwargs)
            user_prompt = self.get_user_prompt(blackboard, **kwargs)

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]

            if feedback:
                messages.append({"role": "assistant", "content": "我已完成工作，请审阅。"})
                messages.append({"role": "user", "content": f"请根据以下反馈意见修改你的输出：\n\n{feedback}"})

            blackboard.update_agent_status(self.name, "running", 30, "正在生成内容...")

            full_response = ""
            async for chunk in provider.chat_stream(messages):
                full_response += chunk
                blackboard.update_agent_status(self.name, "running", 50, "正在接收响应...")

            blackboard.update_agent_status(self.name, "running", 80, "正在解析结果...")

            result = self.parse_response(full_response, blackboard)
            output_type = self.get_output_type()
            blackboard.set_artifact(output_type, result)

            blackboard.update_agent_status(self.name, "completed", 100, "完成")
            await blackboard.emit_event("agent_done", {
                "agent": self.name,
                "display_name": self.display_name,
                "output_type": output_type.value,
            })

            return result

        except Exception as e:
            blackboard.update_agent_status(self.name, "failed", 0, f"执行失败: {str(e)}")
            await blackboard.emit_event("agent_error", {
                "agent": self.name,
                "display_name": self.display_name,
                "error": str(e),
            })
            raise

    def _extract_json(self, text: str) -> dict | list | None:
        json_blocks = []
        in_block = False
        block = ""
        brace_count = 0

        for char in text:
            if char == '{' and not in_block:
                in_block = True
                brace_count = 1
                block = char
            elif in_block:
                block += char
                if char == '{':
                    brace_count += 1
                elif char == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        in_block = False
                        json_blocks.append(block)
                        block = ""

        for block in json_blocks:
            try:
                return json.loads(block)
            except json.JSONDecodeError:
                continue

        start = text.find('[')
        if start != -1:
            try:
                return json.loads(text[start:])
            except json.JSONDecodeError:
                pass

        return None
