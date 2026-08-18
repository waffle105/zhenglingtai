"""LLM 调用层（openai 兼容协议）。

用途：
    给 CLI 的"通译/流转/验收"三个层提供 LLM 调用能力。
    默认走 openai Chat Completions 协议（绝大多数 LLM 厂商都兼容：
    OpenAI / Azure / DeepSeek / 智谱 / Groq / 各种 Anthropic proxy）。

为什么不用厂商 SDK：
    绑死厂商会让分享包失去通用性。
    让用户在 config.yaml 里填 base_url / api_key / model 就能接任何兼容协议的 LLM。

注释规范提示：
    - 函数 docstring 三行：用途 / Why / 契约
    - 关键判断点（重试/降级）显式注释
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import yaml


@dataclass
class LLMConfig:
    """LLM 配置。

    字段表（键名 / 类型 / 必填 / 含义）：
      base_url        str   ✅   OpenAI 兼容服务的 base_url
      api_key         str   ✅   从环境变量或 config 读取
      model           str   ✅   模型名
      timeout_seconds int   ❌   默认 60
      max_retries     int   ❌   默认 3
    """

    base_url: str
    api_key: str
    model: str
    timeout_seconds: int = 60
    max_retries: int = 3


def load_config(path: str | os.PathLike[str] | None = None) -> LLMConfig:
    """从 YAML 加载 LLM 配置。

    Why this exists:
        让用户把厂商信息（api_key、base_url、model）放在一个简单的 yaml 里，
        比 hardcode 在代码里好得多——分享包也不会泄露 key。

    优先级：环境变量 > config.yaml 默认值

    HARD: api_key 永远不落代码，只走 env 或外部 yaml
    """
    if path is None:
        candidates = [
            Path("zlt.config.yaml"),
            Path.home() / ".config" / "zhenglingtai" / "config.yaml",
        ]
        for c in candidates:
            if c.exists():
                path = c
                break
        if path is None:
            raise FileNotFoundError(
                "未找到 LLM 配置。可通过 --config 指定，或在以下位置之一创建：\n"
                "  ./zlt.config.yaml\n"
                "  ~/.config/zhenglingtai/config.yaml\n"
                "示例见 ../config.example.yaml"
            )

    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    # env 优先覆盖
    return LLMConfig(
        base_url=os.environ.get("ZLT_BASE_URL", raw.get("base_url", "")),
        api_key=os.environ.get("ZLT_API_KEY", raw.get("api_key", "")),
        model=os.environ.get("ZLT_MODEL", raw.get("model", "gpt-4o-mini")),
        timeout_seconds=int(raw.get("timeout_seconds", 60)),
        max_retries=int(raw.get("max_retries", 3)),
    )


def chat(
    cfg: LLMConfig,
    system: str,
    user: str,
    *,
    temperature: float = 0.2,
    response_format: str | None = None,
) -> str:
    """发一次对话请求，返回模型文本输出。

    Why temperature=0.2:
        政令台要求输出稳定可复现（验收单要能对得上任务书），
        温度高会让 AI 在两次调用间偷偷改结论，破坏纪律性。
    """
    url = cfg.base_url.rstrip("/") + "/chat/completions"
    headers = {
        "Authorization": f"Bearer {cfg.api_key}",
        "Content-Type": "application/json",
    }
    payload: dict[str, Any] = {
        "model": cfg.model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": temperature,
    }
    if response_format == "json":
        payload["response_format"] = {"type": "json_object"}

    last_err: Exception | None = None
    for attempt in range(cfg.max_retries + 1):
        try:
            with httpx.Client(timeout=cfg.timeout_seconds) as client:
                resp = client.post(url, headers=headers, json=payload)
                resp.raise_for_status()
                data = resp.json()
                return str(data["choices"][0]["message"]["content"])
        except httpx.HTTPError as e:
            last_err = e
            if attempt >= cfg.max_retries:
                break
            # HARD: 重试不能写成死循环，最多重 max_retries 次
            time.sleep(2**attempt)

    assert last_err is not None
    raise last_err


def chat_json(cfg: LLMConfig, system: str, user: str) -> dict[str, Any]:
    """发对话并把结果解析为 dict（流程单/任务书/验收单都用这接口）。

    退路策略：
      1) 先尝试 response_format=json（要求模型严格 JSON）
      2) 解析失败时，退而求其次用 markdown 代码块围栏的 JSON
      3) 再失败则抛 ValueError
    """
    raw = chat(cfg, system, user, response_format="json")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    if "```" in raw:
        for fence in ("```json", "```JSON", "```"):
            idx = raw.find(fence)
            if idx >= 0:
                start = idx + len(fence)
                end = raw.find("```", start)
                if end > start:
                    try:
                        return json.loads(raw[start:end].strip())
                    except json.JSONDecodeError:
                        continue
    raise ValueError(f"LLM 输出无法解析为 JSON：\n{raw[:500]}")
