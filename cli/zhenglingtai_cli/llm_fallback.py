"""LLM 直接干活 fallback（v1.2.0）。

Why this exists:
    原生能力有、用户 cap 也能配——但小白刚装、什么 cap 都没配，
    又不想装 python-pptx 这种三方库。还想让 AI 一句话就出产物。

    第 3 层 fallback 就是：原声+cap 都不接 → 让 LLM 直接动手。
    产物是"文本类（md / txt / code / json / yaml）"。
    二进制产物（pptx/xlsx/图片）回到"让用户装库或人工接手"。

设计约束：
  - 不引入新依赖（复用现有 llm.chat_json）
  - 写入路径从 step['output'] 推断（缺则 noop + 提示）
  - 路径后缀决定文本/代码格式
  - LLM 调用失败同样不硬停——返回 ok=False 让上层 ESCALATE
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import TYPE_CHECKING

from .executor import SubcapabilityResult

if TYPE_CHECKING:
    from .llm import LLMConfig


_TEXT_SUFFIXES = {".md", ".txt", ".markdown", ".rst", ".adoc",
                  ".json", ".yaml", ".yml", ".csv", ".tsv",
                  ".py", ".js", ".ts", ".tsx", ".jsx", ".vue", ".html", ".css",
                  ".sh", ".ps1", ".bat", ".sql", ".xml", ".ini", ".env",
                  ".c", ".cpp", ".h", ".hpp", ".go", ".rs", ".java", ".kt"}


def is_text_output(out_path: str) -> bool:
    """判断 output 后缀是否属于"LLM 能写文本"范畴。"""
    return Path(out_path).suffix.lower() in _TEXT_SUFFIXES


_SYSTEM = """你是一个文本生成助手。用户会让你为某个步骤写一段内容。

约束：
  - 只输出文件正文，不要任何前言/元说明/解释
  - Markdown 文件直接写正文（标题/段落/列表），不必再写"以下是xx"开场
  - 代码文件直接写代码（不要包 markdown 围栏）
  - JSON/YAML 直接写结构化内容，不要包代码围栏
  - 不知道用合理默认填充，不要说"无法回答"
  - 内容长但不要凑字数；目标是有用，不是堆字"""


def invoke_for_step(
    capability_id: str,
    step: dict,
    llm_cfg: "LLMConfig | None" = None,  # noqa: F821 — 类型仅注解，运行时不查
    work_dir: str | Path = ".",
) -> SubcapabilityResult | None:
    """如果 output 后缀在文本范围内，调 LLM 出文本写到该路径。

    返回 None = 这层不管（交给上层）。
    返回 SubcapabilityResult = 已处理（含成功/失败语义）。

    跳过本层的几种情况（全部返回 None 让上层 fallback）：
      - step 没有 output 字段（用户没指明产物路径——不走 LLM 直干）
      - output 后缀不在文本范围（.pptx/.xlsx 等二进制产物）
      - llm_cfg 没配（无 key 也不能硬调）

    Note: 这一层**严格自包含**——遇到拿不准的情况一律返回 None。
    任何"应该做事但做不到"的语义都交还上层（L4 noop + 升级）。
    """
    from .llm import chat_json
    out_rel = step.get("output", "")
    if not out_rel:
        return None
    if not is_text_output(out_rel):
        return None
    if llm_cfg is None:
        return None

    user_prompt = step.get("input", "")
    capability = step.get("skill_id") or capability_id
    user_payload = (
        f"步骤期望产出：{out_rel}\n"
        f"步骤所属能力：{capability}\n"
        f"步骤输入素材：\n{user_prompt}\n"
    )

    # 1. 调 LLM 出正文
    try:
        raw = chat_json(llm_cfg, _SYSTEM, user_payload)
        body = _extract_text(raw)
    except Exception as e:  # noqa: BLE001
        return SubcapabilityResult(
            ok=False, outputs=[], logs="",
            error=f"[llm.fallback] LLM 调用失败：{e}",
        )

    # 2. 落到 work_dir / out_rel
    p = Path(work_dir) / out_rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")

    return SubcapabilityResult(
        ok=True,
        outputs=[{"type": "text", "path": str(p), "bytes": len(body.encode("utf-8"))}],
        logs=f"[llm.fallback] {capability} → {p.name} ({len(body)} chars)",
    )


# chat_json 默认返回 dict；我们要求"只输出正文"——把它当 dict 字符串化、当字符串直接拿
def _extract_text(raw: object) -> str:
    """从 chat_json 返回值里提取正文。

    约定：chat_json 返回 dict；客户端期待"主回答"在某个固定键。
    为简化第一版，只识别：
      - 若返回 dict 且唯一键是 'content'/'text'/'output' → 用它
      - 否则 dump 成 JSON 字符串
      - 若返回的是 str → 直接用
    """
    if isinstance(raw, str):
        return raw.strip()
    if isinstance(raw, dict):
        for k in ("content", "text", "output", "result", "answer"):
            v = raw.get(k)
            if isinstance(v, str):
                return v.strip()
        # 兜底：dump
        return json.dumps(raw, ensure_ascii=False, indent=2)
    return str(raw).strip()
