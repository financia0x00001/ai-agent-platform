from __future__ import annotations

import hashlib
import json
import logging
import time
from typing import Any

logger = logging.getLogger(__name__)


class ResponseCache:
    def __init__(self, ttl: int = 3600, max_size: int = 100):
        self.ttl = ttl
        self.max_size = max_size
        self._cache: dict[str, dict] = {}
        self.stats = {"hits": 0, "misses": 0, "evictions": 0}

    def _make_key(self, messages: list[dict], model: str = "", temperature: float = 0.7) -> str:
        content = json.dumps(messages, ensure_ascii=False, sort_keys=True)
        raw = f"{model}:{temperature}:{content}"
        return hashlib.sha256(raw.encode()).hexdigest()

    def get(self, messages: list[dict], model: str = "", temperature: float = 0.7) -> str | None:
        key = self._make_key(messages, model, temperature)
        entry = self._cache.get(key)
        if entry is None:
            self.stats["misses"] += 1
            return None
        if time.time() - entry["timestamp"] > self.ttl:
            del self._cache[key]
            self.stats["misses"] += 1
            return None
        self.stats["hits"] += 1
        logger.info(f"Cache HIT for model={model}, saved tokens")
        return entry["response"]

    def set(self, messages: list[dict], response: str, model: str = "", temperature: float = 0.7):
        key = self._make_key(messages, model, temperature)
        if len(self._cache) >= self.max_size:
            oldest_key = min(self._cache, key=lambda k: self._cache[k]["timestamp"])
            del self._cache[oldest_key]
            self.stats["evictions"] += 1
        self._cache[key] = {
            "response": response,
            "timestamp": time.time(),
        }

    def get_stats(self) -> dict:
        total = self.stats["hits"] + self.stats["misses"]
        hit_rate = (self.stats["hits"] / total * 100) if total > 0 else 0
        return {
            "hits": self.stats["hits"],
            "misses": self.stats["misses"],
            "hit_rate": f"{hit_rate:.1f}%",
            "evictions": self.stats["evictions"],
            "cache_size": len(self._cache),
        }

    def clear(self):
        self._cache.clear()
        self.stats = {"hits": 0, "misses": 0, "evictions": 0}


class ContextCompressor:
    @staticmethod
    def compress_artifact(artifact: Any, max_length: int = 2000) -> str:
        if artifact is None:
            return "无"
        if isinstance(artifact, str):
            if len(artifact) <= max_length:
                return artifact
            return artifact[:max_length] + f"\n... (已压缩，原始长度: {len(artifact)} 字符)"
        if isinstance(artifact, dict):
            compressed = {}
            for key, value in artifact.items():
                if isinstance(value, str) and len(value) > 500:
                    compressed[key] = value[:500] + f"... (已压缩, 原始{len(value)}字符)"
                elif isinstance(value, list) and len(value) > 10:
                    compressed[key] = value[:10] + [f"... (共{len(value)}项，已省略{len(value)-10}项)"]
                else:
                    compressed[key] = value
            result = json.dumps(compressed, ensure_ascii=False, indent=2)
            if len(result) > max_length:
                return result[:max_length] + f"\n... (已压缩，原始长度: {len(result)} 字符)"
            return result
        if isinstance(artifact, list):
            if len(artifact) <= 10:
                result = json.dumps(artifact, ensure_ascii=False, indent=2)
            else:
                result = json.dumps(artifact[:10], ensure_ascii=False, indent=2)
                result += f"\n... (共{len(artifact)}项，已省略{len(artifact)-10}项)"
            if len(result) > max_length:
                return result[:max_length] + f"\n... (已压缩)"
            return result
        return str(artifact)[:max_length]

    @staticmethod
    def summarize_for_fix(artifact: Any) -> str:
        if artifact is None:
            return "无"
        if isinstance(artifact, dict):
            summary_parts = []
            if "files" in artifact:
                file_names = [f.get("path", "?") for f in artifact["files"] if isinstance(f, dict)]
                summary_parts.append(f"文件列表: {', '.join(file_names)}")
            if "api_design" in artifact:
                apis = artifact["api_design"]
                if isinstance(apis, list):
                    api_summary = [f"{a.get('method','?')} {a.get('path','?')}" for a in apis[:5] if isinstance(a, dict)]
                    summary_parts.append(f"API: {', '.join(api_summary)}")
            if "pages" in artifact:
                page_names = [p.get("name", "?") for p in artifact["pages"] if isinstance(p, dict)]
                summary_parts.append(f"页面: {', '.join(page_names)}")
            if "bugs" in artifact:
                bug_titles = [b.get("title", "?") for b in artifact["bugs"][:5] if isinstance(b, dict)]
                summary_parts.append(f"Bug: {', '.join(bug_titles)}")
            if "vulnerabilities" in artifact:
                vuln_titles = [v.get("title", "?") for v in artifact["vulnerabilities"][:5] if isinstance(v, dict)]
                summary_parts.append(f"漏洞: {', '.join(vuln_titles)}")
            if summary_parts:
                return "摘要: " + " | ".join(summary_parts)
        return ContextCompressor.compress_artifact(artifact, max_length=1000)


_global_cache = ResponseCache()


def get_cache() -> ResponseCache:
    return _global_cache
