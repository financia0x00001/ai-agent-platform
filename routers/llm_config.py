from __future__ import annotations

import uuid
import json
import asyncio
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from config import load_llm_configs, save_llm_configs, get_default_llm
from core.llm_provider import KNOWN_PROVIDERS

router = APIRouter(prefix="/api/llm", tags=["LLM配置"])


class LLMConfigCreate(BaseModel):
    name: str
    provider_id: str = "deepseek"
    api_key: str
    base_url: Optional[str] = None
    model: Optional[str] = None
    temperature: float = 0.7
    max_tokens: int = 4096
    is_default: bool = False


class LLMConfigUpdate(BaseModel):
    name: Optional[str] = None
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    model: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    is_default: Optional[bool] = None


@router.get("/providers")
async def list_providers():
    return {"providers": KNOWN_PROVIDERS}


@router.get("/configs")
async def list_configs():
    configs = load_llm_configs()
    masked = []
    for c in configs:
        mc = {**c}
        if mc.get("api_key"):
            key = mc["api_key"]
            mc["api_key_masked"] = key[:8] + "..." + key[-4:] if len(key) > 12 else "***"
            del mc["api_key"]
        masked.append(mc)
    return {"configs": masked}


@router.post("/configs")
async def create_config(data: LLMConfigCreate):
    configs = load_llm_configs()

    provider_info = KNOWN_PROVIDERS.get(data.provider_id, KNOWN_PROVIDERS["custom"])

    new_config = {
        "id": str(uuid.uuid4()),
        "name": data.name,
        "provider_id": data.provider_id,
        "api_key": data.api_key,
        "base_url": data.base_url or provider_info.get("base_url", ""),
        "model": data.model or provider_info.get("default_model", ""),
        "temperature": data.temperature,
        "max_tokens": data.max_tokens,
        "is_default": data.is_default,
    }

    if data.is_default:
        for c in configs:
            c["is_default"] = False

    configs.append(new_config)
    save_llm_configs(configs)
    return {"message": "配置创建成功", "id": new_config["id"]}


@router.put("/configs/{config_id}")
async def update_config(config_id: str, data: LLMConfigUpdate):
    configs = load_llm_configs()
    found = False
    for c in configs:
        if c["id"] == config_id:
            update_data = data.model_dump(exclude_unset=True)
            if data.is_default:
                for other in configs:
                    other["is_default"] = False
            c.update(update_data)
            found = True
            break

    if not found:
        raise HTTPException(status_code=404, detail="配置不存在")

    save_llm_configs(configs)
    return {"message": "配置更新成功"}


@router.delete("/configs/{config_id}")
async def delete_config(config_id: str):
    configs = load_llm_configs()
    new_configs = [c for c in configs if c["id"] != config_id]
    if len(new_configs) == len(configs):
        raise HTTPException(status_code=404, detail="配置不存在")
    save_llm_configs(new_configs)
    return {"message": "配置删除成功"}


@router.get("/default")
async def get_default():
    default = get_default_llm()
    if default:
        return {"has_default": True, "name": default.get("name"), "provider_id": default.get("provider_id"), "model": default.get("model")}
    return {"has_default": False}
