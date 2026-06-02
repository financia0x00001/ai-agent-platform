from __future__ import annotations

import asyncio
import logging
import random
import time
from typing import AsyncIterator

import httpx
from openai import AsyncOpenAI, APIError, RateLimitError, APITimeoutError, APIConnectionError

from config import load_llm_configs, get_default_llm
from core.cache import get_cache

logger = logging.getLogger("uvicorn")

# 各平台模型定价 (RMB / 1M tokens, 输入 / 输出)
MODEL_PRICING = {
    "deepseek-chat":       (1.0,  2.0),
    "deepseek-reasoner":   (4.0,  16.0),
    "gpt-4o":              (18.0, 54.0),
    "gpt-4o-mini":         (1.05, 4.2),
    "gpt-4-turbo":         (21.8, 65.4),
    "glm-4-plus":          (3.5,  3.5),
    "glm-4-flash":         (0.0,  0.0),   # 免费
    "glm-4":               (3.5,  3.5),
    "moonshot-v1-8k":      (0.84, 0.84),
    "moonshot-v1-32k":     (1.68, 1.68),
    "moonshot-v1-128k":    (4.2,  4.2),
    "qwen-max":            (2.8,  11.2),
    "qwen-plus":           (0.56, 2.24),
    "qwen-turbo":          (0.21, 0.84),
}

RETRYABLE_STATUSES = {429, 500, 502, 503, 504}
MAX_RETRIES = 3
BASE_DELAY = 2.0  # 基础延迟(秒)

# 推理模型：内部推理消耗大量 token，需要更大的 max_tokens 才能有实际输出
REASONING_MODELS = {
    "glm-5", "glm-5-turbo", "glm-5.1",
    "deepseek-reasoner",
    "o1", "o1-mini", "o1-preview",
    "o3", "o3-mini", "o4-mini",
}
REASONING_TOKEN_FACTOR = 3  # 推理模型实际输出约为 max_tokens 的 1/3

# 各模型 max_tokens 上限（防止用户配置过大导致 API 拒绝）
# 不在此列表的模型默认上限 128000
MODEL_MAX_TOKENS: dict[str, int] = {
    "glm-4-plus": 128000,
    "glm-4-flash": 128000,
    "glm-4": 128000,
    "glm-4.5": 128000,
    "glm-4.5-air": 128000,
    "glm-4.6": 128000,
    "glm-4.7": 128000,
    "glm-5": 65536,
    "glm-5-turbo": 65536,
    "glm-5.1": 65536,
    "deepseek-chat": 65536,
    "deepseek-reasoner": 65536,
    "gpt-4o": 16384,
    "gpt-4o-mini": 16384,
    "gpt-4-turbo": 4096,
    "o1": 100000,
    "o1-mini": 65536,
    "o3-mini": 100000,
    "qwen-max": 8192,
    "qwen-plus": 8192,
    "qwen-turbo": 8192,
}
DEFAULT_MAX_TOKENS_CAP = 128000


KNOWN_PROVIDERS = {
    "deepseek": {
        "name": "DeepSeek",
        "base_url": "https://api.deepseek.com",
        "default_model": "deepseek-chat",
        "models": ["deepseek-chat", "deepseek-reasoner"],
    },
    "openai": {
        "name": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "default_model": "gpt-4o",
        "models": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "o1", "o1-mini"],
    },
    "zhipu": {
        "name": "智谱AI",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "default_model": "glm-4-plus",
        "models": ["glm-4-plus", "glm-4-flash", "glm-4", "glm-4.5", "glm-4.5-air", "glm-4.6", "glm-4.7", "glm-5", "glm-5-turbo", "glm-5.1"],
    },
    "moonshot": {
        "name": "Moonshot",
        "base_url": "https://api.moonshot.cn/v1",
        "default_model": "moonshot-v1-128k",
        "models": ["moonshot-v1-8k", "moonshot-v1-32k", "moonshot-v1-128k"],
    },
    "qwen": {
        "name": "通义千问",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "default_model": "qwen-max",
        "models": ["qwen-max", "qwen-plus", "qwen-turbo"],
    },
    "custom": {
        "name": "自定义",
        "base_url": "",
        "default_model": "",
        "models": [],
    },
}


class LLMProvider:
    def __init__(self, config: dict):
        self.config = config
        self.provider_id = config.get("provider_id", "custom")
        self.api_key = config.get("api_key", "")
        self.base_url = config.get("base_url", "")
        self.model = config.get("model", "")
        self.temperature = config.get("temperature", 0.7)
        # 强制上限保护，防止用户误配过大值导致 API 拒绝
        raw_max = config.get("max_tokens", 4096)
        model_cap = MODEL_MAX_TOKENS.get(self.model, DEFAULT_MAX_TOKENS_CAP)
        self.max_tokens = min(raw_max, model_cap)
        if raw_max > model_cap:
            logger.warning(
                f"模型 {self.model} max_tokens={raw_max} 超出上限，已自动截断为 {model_cap}"
            )
        self._client: AsyncOpenAI | None = None
        # 推理模型检测
        self.is_reasoning_model = self.model in REASONING_MODELS
        # 成本追踪
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.total_reasoning_tokens = 0
        self.total_calls = 0
        self.total_cost_rmb = 0.0

    @property
    def client(self) -> AsyncOpenAI:
        if self._client is None:
            http_client = httpx.AsyncClient(
                trust_env=False,  # 绕过系统代理，避免代理不稳定导致连接失败
                timeout=120.0,
            )
            self._client = AsyncOpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
                http_client=http_client,
                max_retries=0,  # 我们自己做重试
            )
        return self._client

    def _is_retryable(self, exc: Exception) -> bool:
        if isinstance(exc, RateLimitError):
            return True
        if isinstance(exc, APITimeoutError) or isinstance(exc, APIConnectionError):
            return True
        if isinstance(exc, APIError):
            return getattr(exc, "status_code", 500) in RETRYABLE_STATUSES
        return False

    def _track_usage(self, response):
        """追踪 token 用量和成本"""
        if hasattr(response, "usage") and response.usage:
            inp = response.usage.prompt_tokens or 0
            out = response.usage.completion_tokens or 0
            self.total_input_tokens += inp
            self.total_output_tokens += out
            self.total_calls += 1

            # 跟踪推理 token
            if hasattr(response.usage, "completion_tokens_details") and response.usage.completion_tokens_details:
                reasoning = getattr(response.usage.completion_tokens_details, "reasoning_tokens", 0) or 0
                self.total_reasoning_tokens += reasoning

            pricing = MODEL_PRICING.get(self.model, (0, 0))
            cost = (inp / 1_000_000) * pricing[0] + (out / 1_000_000) * pricing[1]
            self.total_cost_rmb += cost

    def get_usage_summary(self) -> dict:
        cache = get_cache()
        summary = {
            "model": self.model,
            "is_reasoning_model": self.is_reasoning_model,
            "total_calls": self.total_calls,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_tokens": self.total_input_tokens + self.total_output_tokens,
            "estimated_cost_rmb": round(self.total_cost_rmb, 4),
            "cache_stats": cache.get_stats(),
        }
        if self.total_reasoning_tokens > 0:
            summary["total_reasoning_tokens"] = self.total_reasoning_tokens
            summary["reasoning_ratio"] = round(self.total_reasoning_tokens / max(self.total_output_tokens, 1) * 100, 1)
        return summary

    def _effective_max_tokens(self, requested: int) -> int:
        """推理模型自动放大 max_tokens，但不超过模型硬上限"""
        model_cap = MODEL_MAX_TOKENS.get(self.model, DEFAULT_MAX_TOKENS_CAP)
        if self.is_reasoning_model and requested < self.max_tokens * REASONING_TOKEN_FACTOR:
            return min(self.max_tokens * REASONING_TOKEN_FACTOR, model_cap)
        return min(requested, model_cap)

    async def chat(self, messages: list[dict], **kwargs) -> str:
        temperature = kwargs.pop("temperature", self.temperature)
        max_tokens = self._effective_max_tokens(kwargs.pop("max_tokens", self.max_tokens))
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )
        self._track_usage(response)
        message = response.choices[0].message
        content = message.content or ""

        # 推理模型：content 为空但 reasoning_content 有内容时给出警告
        if not content and hasattr(message, "reasoning_content") and message.reasoning_content:
            logger.warning(
                f"推理模型 {self.model} 全部 token 用于推理，无实际输出。"
                f"当前 max_tokens={max_tokens}，建议增大。"
            )
            # 返回推理摘要作为降级输出
            reasoning = message.reasoning_content
            content = reasoning[-500:] if len(reasoning) > 500 else reasoning

        return content

    async def chat_stream(self, messages: list[dict], **kwargs) -> AsyncIterator[str]:
        temperature = kwargs.pop("temperature", self.temperature)
        max_tokens = self._effective_max_tokens(kwargs.pop("max_tokens", self.max_tokens))
        stream = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
            stream_options={"include_usage": True},
            **kwargs,
        )
        yielded_any = False
        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yielded_any = True
                yield chunk.choices[0].delta.content
            # 流式最后一个 chunk 包含 usage
            if hasattr(chunk, "usage") and chunk.usage:
                # 手动构造一个类似 response 的对象来追踪
                class UsageWrapper:
                    pass
                wrapper = UsageWrapper()
                wrapper.usage = chunk.usage
                self._track_usage(wrapper)
                if not yielded_any and self.is_reasoning_model:
                    logger.warning(
                        f"推理模型 {self.model} 流式输出中全部 token 用于推理，无实际输出。"
                        f"max_tokens={max_tokens}"
                    )

    async def chat_with_retry(self, messages: list[dict], retries: int = MAX_RETRIES, **kwargs) -> str:
        cache = get_cache()
        temperature = kwargs.get("temperature", self.temperature)

        if temperature <= 0.3:
            cached = cache.get(messages, self.model, temperature)
            if cached is not None:
                return cached

        last_error = None
        for attempt in range(retries + 1):
            try:
                result = await self.chat(messages, **kwargs)
                if temperature <= 0.3:
                    cache.set(messages, result, self.model, temperature)
                return result
            except Exception as e:
                last_error = e
                if attempt < retries and self._is_retryable(e):
                    delay = BASE_DELAY * (2 ** attempt) + random.uniform(0, 1)
                    logger.warning(
                        f"LLM retry {attempt+1}/{retries} for model={self.model}: "
                        f"{type(e).__name__}, waiting {delay:.1f}s"
                    )
                    await asyncio.sleep(delay)
                else:
                    break
        raise last_error

    async def chat_stream_with_retry(self, messages: list[dict], retries: int = MAX_RETRIES, **kwargs) -> AsyncIterator[str]:
        cache = get_cache()
        temperature = kwargs.get("temperature", self.temperature)

        if temperature <= 0.3:
            cached = cache.get(messages, self.model, temperature)
            if cached is not None:
                yield cached
                return

        full_response_parts = []
        last_error = None
        for attempt in range(retries + 1):
            try:
                async for chunk in self.chat_stream(messages, **kwargs):
                    full_response_parts.append(chunk)
                    yield chunk
                if temperature <= 0.3:
                    full_text = "".join(full_response_parts)
                    cache.set(messages, full_text, self.model, temperature)
                return
            except Exception as e:
                last_error = e
                full_response_parts = []
                if attempt < retries and self._is_retryable(e):
                    delay = BASE_DELAY * (2 ** attempt) + random.uniform(0, 1)
                    logger.warning(
                        f"LLM stream retry {attempt+1}/{retries} for model={self.model}: "
                        f"{type(e).__name__}, waiting {delay:.1f}s"
                    )
                    await asyncio.sleep(delay)
                else:
                    break
        raise last_error


def get_provider(config: dict | None = None) -> LLMProvider:
    if config is None:
        config = get_default_llm()
    if config is None:
        raise ValueError("未配置任何LLM提供商，请先在设置中添加API配置")
    return LLMProvider(config)


def get_provider_by_id(provider_id: str) -> LLMProvider | None:
    configs = load_llm_configs()
    for c in configs:
        if c.get("id") == provider_id:
            return LLMProvider(c)
    return None
