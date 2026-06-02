from __future__ import annotations

import json
import logging
import re
import time
from abc import ABC, abstractmethod
from typing import Any

from core.blackboard import Blackboard, ArtifactType
from core.llm_provider import LLMProvider

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    name: str = ""
    display_name: str = ""
    description: str = ""
    required_fields: dict[str, Any] = {}
    can_negotiate: bool = False
    enable_llm_quality_check: bool = False
    # 默认温度：创意类Agent用0.7，分析类用≤0.3以启用缓存
    default_temperature: float = 0.7

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
            async for chunk in provider.chat_stream_with_retry(messages, temperature=self.default_temperature):
                full_response += chunk
                blackboard.update_agent_status(self.name, "running", 50, "正在接收响应...")

            blackboard.update_agent_status(self.name, "running", 80, "正在解析结果...")

            result = self.parse_response(full_response, blackboard)

            if not self._validate_output(result):
                logger.warning(f"Agent {self.name} 输出验证失败，缺少必要字段，已尝试填充默认值")

            if isinstance(result, dict) and "negotiations" in result:
                self._process_negotiations(result, blackboard)

            quality_result = self._check_quality(result)
            if not quality_result["passed"] and not kwargs.get("is_fix") and not feedback:
                retry_count = 0
                max_quality_retries = 1
                while not quality_result["passed"] and retry_count < max_quality_retries:
                    retry_count += 1
                    blackboard.update_agent_status(self.name, "running", 85, f"质量检查未通过(评分:{quality_result['score']}),自动重试...")
                    issues_text = "\n".join(quality_result.get("issues", []))
                    retry_messages = messages + [
                        {"role": "assistant", "content": full_response},
                        {"role": "user", "content": f"你的输出质量检查未通过(评分:{quality_result['score']}/10)，存在以下问题：\n{issues_text}\n\n请修正这些问题并重新输出完整的JSON。"}
                    ]
                    full_response = ""
                    async for chunk in provider.chat_stream_with_retry(retry_messages, temperature=self.default_temperature):
                        full_response += chunk
                    result = self.parse_response(full_response, blackboard)
                    if not self._validate_output(result):
                        logger.warning(f"Agent {self.name} 重试后输出验证仍失败")
                    if isinstance(result, dict) and "negotiations" in result:
                        self._process_negotiations(result, blackboard)
                    quality_result = self._check_quality(result)

            if self.enable_llm_quality_check and quality_result.get("passed", True):
                try:
                    llm_quality = await self._llm_quality_check(result, provider)
                    if not llm_quality.get("passed", True) and not kwargs.get("is_fix") and not feedback:
                        logger.warning(f"Agent {self.name} LLM质量检查未通过: {llm_quality.get('issues', [])}")
                except Exception as e:
                    logger.warning(f"Agent {self.name} LLM质量检查异常: {e}")

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

    def _process_negotiations(self, result: dict, blackboard: Blackboard):
        negotiations = result.pop("negotiations", [])
        if not isinstance(negotiations, list):
            return
        for neg in negotiations:
            if isinstance(neg, dict) and "to_agent" in neg and "issue" in neg and "suggestion" in neg:
                blackboard.add_negotiation(
                    from_agent=self.name,
                    to_agent=neg["to_agent"],
                    issue=neg["issue"],
                    suggestion=neg["suggestion"],
                )

    def _check_quality(self, result: Any) -> dict:
        from core.quality import QualityChecker
        if not hasattr(self, '_quality_checker'):
            self._quality_checker = QualityChecker()
        return self._quality_checker.check_structure(self.name, result)

    async def _llm_quality_check(self, result: Any, provider) -> dict:
        from core.quality import QualityChecker
        if not hasattr(self, '_quality_checker'):
            self._quality_checker = QualityChecker()
        return await self._quality_checker.llm_check(self.name, result, provider)

    def _auto_repair_json(self, text: str) -> str:
        repaired = re.sub(r',\s*([}\]])', r'\1', text)
        in_string = False
        escape_next = False
        result = []
        for ch in repaired:
            if escape_next:
                result.append(ch)
                escape_next = False
                continue
            if ch == '\\' and in_string:
                result.append(ch)
                escape_next = True
                continue
            if ch == '"':
                in_string = not in_string
                result.append(ch)
                continue
            if not in_string:
                if ch == "'":
                    result.append('"')
                    continue
            result.append(ch)
        repaired = ''.join(result)
        repaired = re.sub(r'//.*?$', '', repaired, flags=re.MULTILINE)
        repaired = re.sub(r'/\*.*?\*/', '', repaired, flags=re.DOTALL)
        repaired = re.sub(r'(?<=[{\[,])\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*:', r'"\1":', repaired)
        return repaired

    @staticmethod
    def _is_file_path(path: str) -> bool:
        """判断路径是否为文件系统路径（而非 API 端点等）"""
        if not path or not isinstance(path, str):
            return False
        # API endpoint 特征：以 / 开头且不包含文件扩展名
        if path.startswith('/') and '.' not in path.split('/')[-1]:
            return False
        # 必须包含文件扩展名或为已知配置文件名
        return '.' in path or path in ('requirements.txt', '.env.example', 'Dockerfile', 'Makefile')

    def _unwrap_nested_files(self, result: dict) -> dict:
        """解嵌套：如果 files[0].content 本身是代码块包裹的JSON，递归展开"""
        if not isinstance(result, dict):
            return result
        files = result.get("files", [])
        if not isinstance(files, list) or len(files) == 0:
            return result

        # 检查是否有文件 content 以代码块开头（嵌套JSON）
        first_content = files[0].get("content", "") if isinstance(files[0], dict) else ""
        if not isinstance(first_content, str) or not first_content.strip().startswith('```'):
            return result

        inner_result = self._extract_json(first_content)
        if inner_result and isinstance(inner_result, dict):
            inner_files = inner_result.get("files", [])
            # 过滤：保留文件系统路径，排除API端点
            inner_files = [f for f in inner_files if self._is_file_path(f.get('path', ''))]
            if inner_files:
                logger.info(
                    f"Agent {self.name}: 检测到嵌套JSON，已展开 "
                    f"{len(inner_files)} 个代码文件"
                )
                result["api_design"] = inner_result.get("api_design", result.get("api_design", []))
                result["db_schema"] = inner_result.get("db_schema", result.get("db_schema", ""))
                result["files"] = inner_files
                if "tech_stack" in inner_result:
                    result["tech_stack"] = inner_result["tech_stack"]
                if "notes" in inner_result:
                    result["notes"] = inner_result["notes"]
        return result

    def _extract_json(self, text: str) -> dict | list | None:
        fence_pattern = re.compile(r'```(?:json)?\s*\n?(.*?)\n?\s*```', re.DOTALL)
        for match in fence_pattern.finditer(text):
            block = match.group(1).strip()
            try:
                result = json.loads(block)
            except json.JSONDecodeError:
                try:
                    result = json.loads(self._auto_repair_json(block))
                except json.JSONDecodeError:
                    continue

            # 递归解嵌套：检查 files[].content 是否包含嵌套的代码块JSON
            result = self._unwrap_nested_files(result)
            return result

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
                result = json.loads(block)
                result = self._unwrap_nested_files(result)
                return result
            except json.JSONDecodeError:
                try:
                    result = json.loads(self._auto_repair_json(block))
                    result = self._unwrap_nested_files(result)
                    return result
                except json.JSONDecodeError:
                    continue

        first_brace = text.find('{')
        last_brace = text.rfind('}')
        if first_brace != -1 and last_brace > first_brace:
            candidate = text[first_brace:last_brace + 1]
            try:
                result = json.loads(candidate)
                result = self._unwrap_nested_files(result)
                return result
            except json.JSONDecodeError:
                try:
                    result = json.loads(self._auto_repair_json(candidate))
                    result = self._unwrap_nested_files(result)
                    return result
                except json.JSONDecodeError:
                    pass

        first_bracket = text.find('[')
        last_bracket = text.rfind(']')
        if first_bracket != -1 and last_bracket > first_bracket:
            candidate = text[first_bracket:last_bracket + 1]
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                try:
                    return json.loads(self._auto_repair_json(candidate))
                except json.JSONDecodeError:
                    pass

        # 终极兜底：代码文件级提取（不需要合法JSON）
        salvaged = self._salvage_code_files(text)
        if salvaged:
            logger.info(f"Agent {self.name}: JSON解析失败，已通过代码文件提取兜底恢复 {len(salvaged.get('files',[]))} 个文件")
            return salvaged

        return None

    def _salvage_code_files(self, text: str) -> dict | None:
        """终极兜底：从格式损坏的JSON中提取 path/content 文件对，不依赖 JSON 解析"""
        import re as _re
        files = []
        api_design = []
        db_schema = ""

        # 1. 提取 api_design 数组（在顶层，通常较短且格式正确）
        api_match = _re.search(r'"api_design"\s*:\s*(\[.*?\])', text, _re.DOTALL)
        if api_match:
            try: api_design = json.loads(api_match.group(1))
            except: pass

        # 2. 提取 db_schema
        db_match = _re.search(r'"db_schema"\s*:\s*"([^"]*)"', text)
        if db_match: db_schema = db_match.group(1)

        # 3. 用状态机提取 files 数组中的 path/content 对
        # 找 "path": "xxx" 然后找紧跟的 "content": "..." (跨行)
        path_pattern = _re.compile(r'"path"\s*:\s*"([^"]+)"')
        content_start = _re.compile(r'"content"\s*:\s*"')

        # 分段：每次找到一个 path，扫描后续内容直到遇到下一个 path 或 files 数组结束
        paths = list(path_pattern.finditer(text))
        content_starts = list(content_start.finditer(text))

        for i, pm in enumerate(paths):
            path = pm.group(1)
            # 找到这个 path 之后最近的 content start
            cs = None
            for c in content_starts:
                if c.start() > pm.end():
                    cs = c
                    break
            if not cs:
                continue

            # 从 content 开始位置扫描，找字符串结束
            pos = cs.end()
            content_chars = []
            escape_next = False
            in_str = True
            depth = 0
            found_end = False

            while pos < len(text) and not found_end:
                ch = text[pos]
                if escape_next:
                    content_chars.append(ch)
                    escape_next = False
                elif ch == '\\':
                    content_chars.append(ch)
                    escape_next = True
                elif ch == '"':
                    # 可能是 content 字符串结束，检查后面是否跟 , 或 ] 或 }
                    after = text[pos+1:pos+20].lstrip()
                    if after.startswith(',') or after.startswith(']') or after.startswith('}'):
                        found_end = True
                    elif after.startswith('"') and ('path' in text[pos+1:pos+50] or 'description' in text[pos+1:pos+50]):
                        found_end = True
                    else:
                        content_chars.append(ch)
                else:
                    content_chars.append(ch)
                pos += 1

            content = ''.join(content_chars)
            # 还原 JSON 转义
            content = content.replace('\\n', '\n').replace('\\t', '\t').replace('\\"', '"').replace('\\\\', '\\')

            if content.strip() and self._is_file_path(path):
                files.append({"path": path, "content": content})

        if not files:
            return None

        result = {
            "api_design": api_design,
            "db_schema": db_schema,
            "files": files,
            "tech_stack": [],
            "notes": [],
        }
        return result

    def _validate_output(self, result: Any) -> bool:
        if not self.required_fields or not isinstance(result, dict):
            return True
        all_valid = True
        for field, default in self.required_fields.items():
            if field not in result:
                result[field] = default
                all_valid = False
        return all_valid
