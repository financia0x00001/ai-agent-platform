import json
import os
from pathlib import Path
from pydantic_settings import BaseSettings

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

LLM_CONFIG_FILE = DATA_DIR / "llm_configs.json"
PROJECTS_DIR = DATA_DIR / "projects"
PROJECTS_DIR.mkdir(exist_ok=True)


class Settings(BaseSettings):
    app_name: str = "AI智能体协作平台"
    app_version: str = "1.0.0"
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = True
    max_fix_rounds: int = 3

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()


def load_llm_configs() -> list[dict]:
    if LLM_CONFIG_FILE.exists():
        with open(LLM_CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_llm_configs(configs: list[dict]):
    with open(LLM_CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(configs, f, ensure_ascii=False, indent=2)


def get_default_llm() -> dict | None:
    configs = load_llm_configs()
    for c in configs:
        if c.get("is_default"):
            return c
    return configs[0] if configs else None
