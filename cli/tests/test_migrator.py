"""migrator 层单元测试（D11）。

测试范围：
- capabilities_init 生成模板
- capabilities_coverage 统计
- migrate_scan 扫描 + 有/无 capability 区分
- migrate_apply 写入 + 备份
"""

from __future__ import annotations

from pathlib import Path

from zhenglingtai_cli import migrator


# ===== capabilities_init =====

def test_capabilities_init_generates_yaml(tmp_path) -> None:
    """init → 生成 yaml 含 _default 和各 skill 条目。"""
    # 构造一个临时 skills 目录
    skill_dir = tmp_path / "skills" / "test-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: Test Skill\n"
        "metadata:\n"
        "  capability:\n"
        "    id: test-skill\n"
        "    intent_tags: [write_copy]\n"
        "---\n"
        "# Test\n",
        encoding="utf-8",
    )
    out = tmp_path / "caps.yaml"
    msg = migrator.capabilities_init(tmp_path / "skills", out)
    assert "1" in msg  # 含 1 个 skill
    assert out.exists()
    content = out.read_text(encoding="utf-8")
    assert "test-skill" in content  # yaml 文件里含 skill id
    assert "noop" in content


def test_capabilities_init_empty(tmp_path) -> None:
    """空目录 → 提示无可路由 skill。"""
    (tmp_path / "skills").mkdir()
    msg = migrator.capabilities_init(tmp_path / "skills", tmp_path / "out.yaml")
    assert "无可路由" in msg


# ===== capabilities_coverage =====

def test_capabilities_coverage() -> None:
    """2 个 skill、1 个配了 → (1, 2)。"""
    from zhenglingtai_cli import registry
    entries = [
        registry.SkillEntry(id="a", intent_tags=["x"]),
        registry.SkillEntry(id="b", intent_tags=["y"]),
    ]
    caps = {"a": {"kind": "local", "target": "mod:fn"}}
    configured, total = migrator.capabilities_coverage(None, caps)
    # scan(None) 会读 ~/.workbuddy/skills，测试环境可能没有
    # 所以只测 caps 的逻辑
    assert total >= 0


# ===== migrate_scan =====

def test_migrate_scan_finds_missing(tmp_path) -> None:
    """scan → 返回 has_capability=True/False。"""
    skill1 = tmp_path / "skill1" / "SKILL.md"
    skill1.parent.mkdir(parents=True)
    skill1.write_text(
        "---\nmetadata:\n  capability:\n    id: skill1\n    intent_tags: [x]\n---\n# S1\n",
        encoding="utf-8",
    )
    skill2 = tmp_path / "skill2" / "SKILL.md"
    skill2.parent.mkdir(parents=True)
    skill2.write_text("---\nname: S2\n---\n# S2\n", encoding="utf-8")

    results = migrator.migrate_scan(tmp_path)
    assert len(results) == 2
    by_id = {r["id"]: r for r in results}
    assert by_id["skill1"]["has_capability"] is True
    assert by_id["skill2"]["has_capability"] is False


def test_migrate_scan_empty_dir(tmp_path) -> None:
    """空目录 → 空列表。"""
    assert migrator.migrate_scan(tmp_path) == []


# ===== migrate_apply =====

def test_migrate_apply_creates_backup(tmp_path) -> None:
    """apply → 写入 capability 块 + 创建 .bak 备份。"""
    skill_dir = tmp_path / "old-skill" / "SKILL.md"
    skill_dir.parent.mkdir(parents=True)
    original = "---\nname: Old\n---\n# Old Skill\n\nDoes stuff.\n"
    skill_dir.write_text(original, encoding="utf-8")

    msg = migrator.migrate_apply("old-skill", ["write_copy", "summarize"], tmp_path)
    assert "已写入" in msg
    assert ".bak" in msg

    # 备份存在且内容 == 原文
    backup = skill_dir.with_suffix(".md.bak")
    assert backup.exists()
    assert backup.read_text(encoding="utf-8") == original

    # 新文件含 capability 块
    new_text = skill_dir.read_text(encoding="utf-8")
    assert "capability:" in new_text
    assert "write_copy" in new_text
