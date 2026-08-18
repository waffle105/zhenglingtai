"""技能登记册（与 A 形态共用 schema，运行时聚合）。

用途：
    把"运行时聚合登记册"在 CLI 形态里落地——读 SKILL.md frontmatter 的 capability 块。
    与 A 形态（WorkBuddy 元 Skill）共用同一份数据 schema（参见 ../SKILL.md §3）。

为什么仍然读 ~/.workbuddy/skills/* 不读它自己的目录：
    用户可能同时装了 A 形态（本 skill）和一堆自己的 skill，
    CLI 形态要无缝接入——它得认得用户在 WB 生态里的所有 skill。
    可以配 --skills-dir 指向自己目录（用于纯 CLI 用户）。

注释规范提示：
    - 每个函数 docstring 三行
    - 关键判定（撞车/打分/降级）显式注释"如果 X 则 Y"
    - HARD: 标记不可绕过的硬约束
    - 跨文件引用 import 写相对路径
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


@dataclass
class SkillEntry:
    """单个 skill 的 capability 声明。

    字段表：
      id            str           ✅   唯一标识
      name          str           ❌   显示名
      intent_tags   list[str]     ✅   该 skill 的能力标签（路由主键）
      input_types   list[str]     ❌
      output_types  list[str]     ❌
      is_meta       bool          ❌   是否 meta-skill
      priority      int           ❌   冲突消解用
      source_path   str           ❌   SKILL.md 路径
    """

    id: str
    intent_tags: list[str]
    name: str = ""
    input_types: list[str] = field(default_factory=list)
    output_types: list[str] = field(default_factory=list)
    is_meta: bool = False
    priority: int = 0
    source_path: str = ""


_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def _parse_simple_yaml_block(text: str) -> dict[str, object]:
    """解析 YAML frontmatter 块。

    Why PyYAML fallback:
        嵌套字典/列表结构很多，用极简正则解析易出错。
        先尝试 PyYAML；解析失败则返回空 dict（不打断整包扫描）。
    """
    import yaml

    try:
        return yaml.safe_load(text) or {}
    except yaml.YAMLError:
        return {}


def _extract_capability(skill_md_path: Path) -> SkillEntry | None:
    """从单个 SKILL.md 抠 capability 块。

    返回 None 当 capability 块不存在 → 标记为"未声明能力"。
    """
    text = skill_md_path.read_text(encoding="utf-8", errors="ignore")
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return None

    fm = _parse_simple_yaml_block(m.group(1))
    meta = fm.get("metadata")
    if not isinstance(meta, dict):
        return None
    cap = meta.get("capability")
    if not isinstance(cap, dict):
        return None

    skill_id = str(cap.get("id") or skill_md_path.parent.name)
    raw_tags = cap.get("intent_tags") or []
    if not isinstance(raw_tags, list) or not raw_tags:
        return None

    return SkillEntry(
        id=skill_id,
        name=str(fm.get("name") or skill_id),
        intent_tags=[str(t) for t in raw_tags],
        input_types=[str(t) for t in (cap.get("input_types") or [])],
        output_types=[str(t) for t in (cap.get("output_types") or [])],
        is_meta=bool(cap.get("is_meta", False)),
        priority=int(cap.get("priority", 0)),
        source_path=str(skill_md_path),
    )


def scan(skills_dir=None) -> list[SkillEntry]:
    """扫描技能目录，返回登记册。

    skills_dir：单路径、多路径、None（默认 ~/.workbuddy/skills）
    """
    if skills_dir is None:
        candidates: list[Path] = [Path.home() / ".workbuddy" / "skills"]
    elif isinstance(skills_dir, (str, Path)):
        candidates = [Path(skills_dir)]
    else:
        candidates = [Path(p) for p in skills_dir]

    by_id: dict[str, SkillEntry] = {}
    for root in candidates:
        if not root.exists():
            continue
        # HARD: 不递归——只看一级子目录的 SKILL.md
        for child in sorted(root.iterdir()):
            if not child.is_dir():
                continue
            skill_md = child / "SKILL.md"
            if not skill_md.exists():
                continue
            entry = _extract_capability(skill_md)
            if entry is None:
                continue
            if entry.id in by_id:
                if entry.source_path > by_id[entry.id].source_path:
                    by_id[entry.id] = entry
            else:
                by_id[entry.id] = entry

    return list(by_id.values())


# HARD: 调度层自身的 id，永不参与路由（避免自指套娃）
# 如果用户说"政令模式做 X"，intent_tags 含 decree_mode，
# 路由会发现政令台自己 → 委托给自己 → 无限递归。
# 因此政令台自身永远被排除，转通用模式。
META_SELF_IDS = {"zhenglingtai"}


def filter_by_intent(entries: list[SkillEntry], query_tags: list[str]) -> list[SkillEntry]:
    """按意图标签粗筛。

    HARD: query 为空 → 返回空（让上层走"通用模式"）。
    HARD: META_SELF_IDS 中的 skill 永不参与路由（防自指套娃）。
    """
    if not query_tags:
        return []
    q = set(query_tags)
    return [
        e for e in entries
        if e.id not in META_SELF_IDS and q & set(e.intent_tags)
    ]


def score(entries, query_tags, expected_outputs):
    """打分排序（参见 ../SKILL.md §3.2）。

    HARD: query 为空 → 直接返回空，不进入打分（避免除零 / 误命）
    HARD: META_SELF_IDS 中的 skill 永不参与打分（防自指套娃）
    """
    if not query_tags:
        return []

    q = set(query_tags)
    exp_out = set(expected_outputs or [])
    scored = []
    for e in entries:
        if e.id in META_SELF_IDS:
            continue
        hits = q & set(e.intent_tags)
        if not hits:
            continue
        base = len(hits) / len(q)
        bonus = 0.3 * len(set(e.output_types) & exp_out)
        scored.append((e, base + bonus + 0.01 * e.priority))

    scored.sort(key=lambda x: x[1], reverse=True)
    return scored
