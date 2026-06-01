from __future__ import annotations

import asyncio
import logging
import random
import time
from typing import AsyncIterator

from openai import AsyncOpenAI, APIError, RateLimitError, APITimeoutError, APIConnectionError

from config import load_llm_configs, get_default_llm

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
        "models": ["glm-4-plus", "glm-4-flash", "glm-4"],
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
        self.max_tokens = config.get("max_tokens", 4096)
        self._client: AsyncOpenAI | None = None
        # 成本追踪
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.total_calls = 0
        self.total_cost_rmb = 0.0

    @property
    def client(self) -> AsyncOpenAI:
        if self._client is None:
            self._client = AsyncOpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
                timeout=120.0,
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

            pricing = MODEL_PRICING.get(self.model, (0, 0))
            cost = (inp / 1_000_000) * pricing[0] + (out / 1_000_000) * pricing[1]
            self.total_cost_rmb += cost

    def get_usage_summary(self) -> dict:
        return {
            "model": self.model,
            "total_calls": self.total_calls,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_tokens": self.total_input_tokens + self.total_output_tokens,
            "estimated_cost_rmb": round(self.total_cost_rmb, 4),
        }

    async def chat(self, messages: list[dict], **kwargs) -> str:
        temperature = kwargs.pop("temperature", self.temperature)
        max_tokens = kwargs.pop("max_tokens", self.max_tokens)
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )
        self._track_usage(response)
        return response.choices[0].message.content or ""

    async def chat_stream(self, messages: list[dict], **kwargs) -> AsyncIterator[str]:
        temperature = kwargs.pop("temperature", self.temperature)
        max_tokens = kwargs.pop("max_tokens", self.max_tokens)
        stream = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
            stream_options={"include_usage": True},
            **kwargs,
        )
        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
            # 流式最后一个 chunk 包含 usage
            if hasattr(chunk, "usage") and chunk.usage:
                # 手动构造一个类似 response 的对象来追踪
                class UsageWrapper:
                    pass
                wrapper = UsageWrapper()
                wrapper.usage = chunk.usage
                self._track_usage(wrapper)

    async def chat_with_retry(self, messages: list[dict], retries: int = MAX_RETRIES, **kwargs) -> str:
        """非流式调用带智能重试"""
        last_error = None
        for attempt in range(retries + 1):
            try:
                return await self.chat(messages, **kwargs)
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
        """流式调用带智能重试"""
        last_error = None
        for attempt in range(retries + 1):
            try:
                async for chunk in self.chat_stream(messages, **kwargs):
                    yield chunk
                return  # 成功
            except Exception as e:
                last_error = e
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
