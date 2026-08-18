"""可观测性工具（D12）——轻量 JSON Lines 日志。

Why not structlog:
    structlog 需要额外 pip install，增加依赖面。
    本工具用标准库 json + datetime 实现 JSON Lines 输出，
    功能足够用：每条日志一行 JSON，含 timestamp/level/layer/msg/extra。

用法：
    from .logutil import get_logger
    log = get_logger("政令台")
    log.info("layer1_translate_done", decree_id="2026-07-22-xxx", what="竞品分析")
    log.error("exec_failed", step=2, skill_id="x", reason="timeout")

产出：
    1. 控制台：人类可读（[INFO] layer1_translate_done decree_id=...）
    2. run.log：JSON Lines（每行一个 JSON 对象，可被 jq 解析）

注释规范（沿用 ../SKILL.md）：
    - 每个函数三行 docstring
    - 关键判定显式注释
    - HARD: 标记不可绕过的硬约束
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _now_iso() -> str:
    """当前时间 ISO 8601 带时区。"""
    return datetime.now(timezone.utc).astimezone().isoformat()


class JsonLinesLogger:
    """JSON Lines 双通道日志器。

    通道 1：控制台（人类可读，精简）
    通道 2：run.log（JSON Lines，机器可读，可被 jq 解析）

    Why dual-channel:
        控制台给人看（要短、要中文）；
        run.log 给 CI / 事后分析用（要结构化、可 grep / jq）。
    """

    def __init__(self, name: str = "政令台", log_file: Path | None = None):
        self._name = name
        self._log_file = log_file
        self._entries: list[dict[str, Any]] = []

    def _log(self, level: str, msg: str, **extra: Any) -> dict[str, Any]:
        """写一条日志到双通道。"""
        entry: dict[str, Any] = {
            "timestamp": _now_iso(),
            "level": level,
            "logger": self._name,
            "msg": msg,
            **extra,
        }

        # 通道 1：控制台（人类可读）
        extra_str = " ".join(f"{k}={v}" for k, v in extra.items() if k != "timestamp")
        print(f"[{level}] {msg}" + (f" {extra_str}" if extra_str else ""), file=sys.stderr)

        # 通道 2：run.log（JSON Lines）
        if self._log_file:
            with open(self._log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")

        # 内存缓存（给 doctor --verbose 用）
        self._entries.append(entry)
        return entry

    def info(self, msg: str, **extra: Any) -> dict[str, Any]:
        """INFO 级。"""
        return self._log("INFO", msg, **extra)

    def warn(self, msg: str, **extra: Any) -> dict[str, Any]:
        """WARN 级。"""
        return self._log("WARN", msg, **extra)

    def error(self, msg: str, **extra: Any) -> dict[str, Any]:
        """ERROR 级。"""
        return self._log("ERROR", msg, **extra)

    def entries(self) -> list[dict[str, Any]]:
        """返回内存中的日志条目（给 doctor --verbose 用）。"""
        return list(self._entries)


# 模块级默认 logger
_default = JsonLinesLogger()


def get_logger(name: str = "政令台", log_file: Path | None = None) -> JsonLinesLogger:
    """获取一个 logger 实例。

    如果指定了 log_file，日志会追加写入该文件（JSON Lines 格式）。
    否则只输出到控制台 + 内存。
    """
    if log_file is None:
        return _default
    return JsonLinesLogger(name=name, log_file=log_file)


def recent_runs(limit: int = 10) -> list[dict[str, Any]]:
    """读取最近 N 条政令日志（给 doctor --verbose 用）。

    从 ~/.zhenglingtai/runs/ 目录扫描最近的 run.log 文件。
    """
    runs_dir = Path.home() / ".zhenglingtai" / "runs"
    if not runs_dir.exists():
        return []

    logs = sorted(runs_dir.glob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
    results = []
    for log_path in logs[:limit]:
        try:
            lines = log_path.read_text(encoding="utf-8").strip().split("\n")
            entries = [json.loads(l) for l in lines if l.strip()]
            if not entries:
                continue
            first = entries[0]
            last = entries[-1]
            results.append({
                "log_file": str(log_path),
                "started_at": first.get("timestamp", "?"),
                "last_event": last.get("msg", "?"),
                "entry_count": len(entries),
                "levels": {
                    lv: sum(1 for e in entries if e.get("level") == lv)
                    for lv in ("INFO", "WARN", "ERROR")
                },
            })
        except (json.JSONDecodeError, IOError):
            continue
    return results
