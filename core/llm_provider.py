from __future__ import annotations

import asyncio
from typing import AsyncIterator

from openai import AsyncOpenAI

from config import load_llm_configs, get_default_llm


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

    @property
    def client(self) -> AsyncOpenAI:
        if self._client is None:
            self._client = AsyncOpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
            )
        return self._client

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
            **kwargs,
        )
        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    async def chat_with_retry(self, messages: list[dict], retries: int = 3, **kwargs) -> str:
        for attempt in range(retries):
            try:
                return await self.chat(messages, **kwargs)
            except Exception as e:
                if attempt == retries - 1:
                    raise
                await asyncio.sleep(2 ** attempt)


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
