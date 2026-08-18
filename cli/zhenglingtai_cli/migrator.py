"""技能迁移与配置工具（D7 + D8）。

D7: zhengling capabilities init — 扫描登记册 → 生成 capabilities yaml 模板
D8: zhengling migrate scan/suggest/apply/batch — 给老 skill 补 capability 块

Why this exists:
    用户装完政令台后面临两个门槛：
    1. CLI 形态不知道每个 skill 怎么执行 → D7 生成模板让用户照填
    2. 老 skill 没声明 capability → 路由发现不了 → D8 用 LLM 建议 intent_tags

注释规范（沿用 ../SKILL.md）：
    - 每个函数三行 docstring
    - 关键判定显式注释
    - HARD: 标记不可绕过的硬约束
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

import yaml

from . import llm, registry


# ============ D7: capabilities init ============

def capabilities_init(
    skills_dir: Path | None = None,
    output_path: Path | None = None,
) -> str:
    """扫描登记册 → 生成 capabilities yaml 模板。

    返回生成的文件路径。
    """
    entries = registry.scan(skills_dir)
    if not entries:
        return "(无可路由 skill —— 先给 skill 加 capability 块)"

    caps: dict[str, dict] = {"_default": {"kind": "noop", "hint": "配置此 skill 的真实执行方式"}}
    for e in entries:
        caps[e.id] = {
            "kind": "noop",
            "hint": f"intent_tags={e.intent_tags} → 配置 kind: local/http/cli",
        }

    out = output_path or Path("zhenglingtai-capabilities.yaml")
    with open(out, "w", encoding="utf-8") as f:
        f.write("# 由 zhengling capabilities init 生成——照填 kind/target/url/cmd 即可\n")
        f.write("# 四种 kind: local(模块:函数) / http(POST) / cli(命令行) / noop(不执行)\n\n")
        yaml.dump(caps, f, allow_unicode=True, sort_keys=False, default_flow_style=False)

    return f"已生成 {out}（含 {len(entries)} 个 skill 的 noop 模板）"


def capabilities_coverage(skills_dir: Path | None = None, caps: dict | None = None) -> tuple[int, int]:
    """统计 capabilities 覆盖率：登记册 N 个 skill，capabilities 配了 M 个。

    返回 (已配置数, 总数)。
    """
    entries = registry.scan(skills_dir)
    total = len(entries)
    if caps is None:
        caps = {}
    configured = sum(1 for e in entries if e.id in caps and caps[e.id].get("kind", "noop") != "noop")
    return configured, total


# ============ D8: migrate ============

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)

_SYSTEM_MIGRATE_SUGGEST = """你是政令台的迁移助手。读以下 skill 的 SKILL.md 正文，
从受控意图标签词表里选 1-5 个最匹配的 intent_tags。

只输出 JSON：{"intent_tags": ["tag1", "tag2"], "reason": "一句话说明"}

意图标签词表：
{catalog}
"""


def migrate_scan(skills_dir: Path | None = None) -> list[dict]:
    """扫描所有缺 capability 块的 skill。

    返回 [{"id": skill_id, "path": SKILL.md 路径, "has_capability": False}]。

    v1.0.1 修复：只查 frontmatter（YAML 块），不再裸字符串扫全文——
    旧逻辑下正文里提到 "capability:" 字样也会误判为已声明。
    """
    if skills_dir is None:
        skills_dir = Path.home() / ".workbuddy" / "skills"
    skills_dir = Path(skills_dir)

    if not skills_dir.exists():
        return []

    results = []
    for child in sorted(skills_dir.iterdir()):
        if not child.is_dir():
            continue
        skill_md = child / "SKILL.md"
        if not skill_md.exists():
            continue
        text = skill_md.read_text(encoding="utf-8", errors="ignore")
        m = _FRONTMATTER_RE.match(text)
        fm_text = m.group(1) if m else ""
        has_cap = "capability:" in fm_text and "intent_tags:" in fm_text
        results.append({
            "id": child.name,
            "path": str(skill_md),
            "has_capability": has_cap,
        })
    return results


def migrate_suggest(
    cfg: llm.LLMConfig,
    skill_id: str,
    skills_dir: Path | None = None,
    intent_catalog: list[str] | None = None,
) -> dict:
    """用 LLM 读 SKILL.md 正文 → 建议 intent_tags。

    返回 {"intent_tags": [...], "reason": "..."}。
    """
    if skills_dir is None:
        skills_dir = Path.home() / ".workbuddy" / "skills"
    skills_dir = Path(skills_dir)

    skill_md = skills_dir / skill_id / "SKILL.md"
    if not skill_md.exists():
        return {"intent_tags": [], "reason": f"SKILL.md 不存在：{skill_md}"}

    text = skill_md.read_text(encoding="utf-8", errors="ignore")
    # 去掉 frontmatter，只读正文（让 LLM 集中在能力描述上）
    m = _FRONTMATTER_RE.match(text)
    body = text[m.end():] if m else text
    # 截取前 2000 字（省 token）
    body = body[:2000]

    catalog = intent_catalog or _builtin_catalog()
    catalog_md = "\n".join(f"- {t}" for t in catalog)
    system = _SYSTEM_MIGRATE_SUGGEST.format(catalog=catalog_md)

    data = llm.chat_json(cfg, system, body)
    tags = data.get("intent_tags") or []
    # HARD: 过滤不在词表里的标签
    catalog_set = set(catalog)
    valid_tags = [t for t in tags if t in catalog_set]
    return {
        "intent_tags": valid_tags,
        "reason": str(data.get("reason") or ""),
    }


def migrate_apply(
    skill_id: str,
    intent_tags: list[str],
    skills_dir: Path | None = None,
) -> str:
    """给指定 skill 的 SKILL.md 写入 capability 块。

    HARD: 写入前自动备份到 .bak
    返回备份路径。
    """
    if skills_dir is None:
        skills_dir = Path.home() / ".workbuddy" / "skills"
    skills_dir = Path(skills_dir)

    skill_md = skills_dir / skill_id / "SKILL.md"
    if not skill_md.exists():
        raise FileNotFoundError(f"SKILL.md 不存在：{skill_md}")

    # HARD: 备份
    backup_path = skill_md.with_suffix(".md.bak")
    shutil.copy2(skill_md, backup_path)

    text = skill_md.read_text(encoding="utf-8")

    # 构造 capability YAML 块
    tags_yaml = "\n".join(f"  - {t}" for t in intent_tags)
    cap_block = f"""metadata:
  capability:
    id: {skill_id}
    intent_tags:
{tags_yaml}
"""

    m = _FRONTMATTER_RE.match(text)
    if m:
        # 已有 frontmatter → 在其内部加 metadata.capability
        fm_text = m.group(1)
        if "metadata:" in fm_text:
            # 已有 metadata → 在其后插入 capability
            if "capability:" not in fm_text:
                fm_text = fm_text.replace(
                    "metadata:",
                    f"metadata:\n  capability:\n    id: {skill_id}\n    intent_tags:\n{tags_yaml}",
                    1,
                )
        else:
            # 无 metadata → 追加
            fm_text = fm_text.rstrip() + "\n" + cap_block.rstrip() + "\n"

        text = f"---\n{fm_text}\n---\n" + text[m.end():]
    else:
        # 无 frontmatter → 创建一个
        text = f"---\n{cap_block}---\n\n" + text

    skill_md.write_text(text, encoding="utf-8")
    return f"已写入 {skill_md}（备份：{backup_path}）"


def migrate_batch(
    cfg: llm.LLMConfig,
    skills_dir: Path | None = None,
    intent_catalog: list[str] | None = None,
    dry_run: bool = True,
) -> str:
    """批量扫描 + 建议 + （可选）写入。

    dry_run=True → 只输出 migration_plan.md，不写文件。
    dry_run=False → 逐个 apply（带备份）。
    """
    scan_results = migrate_scan(skills_dir)
    missing = [s for s in scan_results if not s["has_capability"]]

    if not missing:
        return "所有 skill 都已有 capability 块，无需迁移。"

    plan_lines = ["# 迁移计划\n", f"缺 capability 的 skill：{len(missing)}\n"]
    applied = 0
    errors = []

    for s in missing:
        skill_id = s["id"]
        try:
            suggestion = migrate_suggest(cfg, skill_id, skills_dir, intent_catalog)
            tags = suggestion["intent_tags"]
            reason = suggestion.get("reason", "")

            if not tags:
                plan_lines.append(f"## {skill_id}\n- ⚠️ LLM 未能建议标签\n")
                errors.append(f"{skill_id}: 无建议标签")
                continue

            plan_lines.append(f"## {skill_id}\n- 建议标签: {tags}\n- 理由: {reason}\n")

            if not dry_run:
                msg = migrate_apply(skill_id, tags, skills_dir)
                plan_lines.append(f"- ✅ {msg}\n")
                applied += 1

        except Exception as e:
            plan_lines.append(f"## {skill_id}\n- ❌ 失败: {e}\n")
            errors.append(f"{skill_id}: {e}")

    plan_lines.append(f"\n---\n总计: {len(missing)} 待迁移 / {applied} 已写入 / {len(errors)} 失败\n")

    out_path = Path("migration_plan.md")
    out_path.write_text("\n".join(plan_lines), encoding="utf-8")

    mode = "dry-run" if dry_run else "已执行"
    return f"迁移计划已写入 {out_path}（{mode}，{len(missing)} 个 skill，{applied} 已写入）"


def _builtin_catalog() -> list[str]:
    """内置意图标签词表（与 __main__.py 的 _builtin_intent_catalog 同步）。

    v1.0.1：移除废弃别名 slide_deck（规范词为 make_ppt）。
    """
    return [
        "content_produce", "article_pipeline", "video_pipeline",
        "write_copy", "write_copy_sales", "write_novel",
        "long_form_fiction", "write_book",
        "clean_excel", "normalize_table", "dedupe_rows", "data_analysis",
        "competitor_analysis", "market_insight", "web_research", "user_research",
        "training_doc", "courseware", "handbook", "instructional_design", "course_plan",
        "transcript_video", "extract_copy", "make_ppt",
        "poster_prompt", "image_gen", "video_gen", "edit_video",
        "prd", "requirement", "roadmap",
        "knowledge_frame", "kb_fetch",
        "skill_create", "skill_pack", "skill_audit",
        "summarize", "translate", "qa", "decree_mode", "orchestrate_skills",
    ]
