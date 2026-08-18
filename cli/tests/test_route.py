"""路由算法测试（D2 修复后）。

测试确定性路由 layer2_route_deterministic：
- score 排序正确
- 冲突消解（output_types 重叠 → 只留最高分）
- 协同编排（output_types 不重叠 → 串行）
- meta-skill 委托
- 空候选 → 通用模式
- 自指排除（D6）
"""

from __future__ import annotations

from zhenglingtai_cli import discipline, registry


def _make_task(tags: list[str]) -> discipline.TaskBook:
    """构造一个测试用 TaskBook。"""
    return discipline.TaskBook(
        what="测试任务",
        why="测试",
        scope_in=["测试"],
        scope_out=["无关"],
        accept=["验收点1"],
        unknowns=[],
        intent_tags=tags,
    )


def _entry(
    id: str,
    tags: list[str],
    outputs: list[str] | None = None,
    is_meta: bool = False,
    priority: int = 0,
) -> registry.SkillEntry:
    """构造一个测试用 SkillEntry。"""
    return registry.SkillEntry(
        id=id,
        intent_tags=tags,
        output_types=outputs or ["md"],
        is_meta=is_meta,
        priority=priority,
    )


# ===== 测试 1：单候选 → main_skill 正确 =====

def test_single_candidate_routes_correctly() -> None:
    """单候选 → main_skill = 该 skill id。"""
    entries = [_entry("skill-a", ["write_copy"], ["md"])]
    task = _make_task(["write_copy"])
    proc = discipline.layer2_route_deterministic(task, entries)
    assert proc.main_skill == "skill-a"
    assert len(proc.steps) == 1


# ===== 测试 2：多候选协同（output_types 不重叠）→ 串行 =====

def test_cooperative_skills_chained() -> None:
    """两个 skill output_types 不重叠 → 协同串行。"""
    entries = [
        _entry("skill-clean", ["clean_excel"], ["xlsx"]),
        _entry("skill-write", ["write_copy"], ["md"]),
    ]
    task = _make_task(["clean_excel", "write_copy"])
    proc = discipline.layer2_route_deterministic(task, entries)
    assert proc.main_skill in ("skill-clean", "skill-write")
    assert len(proc.cooperative) >= 1


# ===== 测试 3：冲突消解（output_types 重叠）→ 只留最高分 =====

def test_conflict_resolution_keeps_top_score() -> None:
    """两个 skill output_types 重叠 → 只留分最高的。"""
    entries = [
        _entry("skill-generic", ["write_copy"], ["md"], priority=0),
        _entry("skill-specific", ["write_copy", "write_copy_sales"], ["md"], priority=10),
    ]
    task = _make_task(["write_copy", "write_copy_sales"])
    proc = discipline.layer2_route_deterministic(task, entries)
    # skill-specific 标签更全 + priority 更高 → 应胜出
    assert proc.main_skill == "skill-specific"


# ===== 测试 4：meta-skill → 整条委托 =====

def test_meta_skill_delegated() -> None:
    """is_meta=true → meta_delegate = 该 skill id。"""
    entries = [_entry("meta-pipeline", ["content_produce"], ["md", "png"], is_meta=True)]
    task = _make_task(["content_produce"])
    proc = discipline.layer2_route_deterministic(task, entries)
    assert proc.meta_delegate == "meta-pipeline"
    assert proc.main_skill == "(meta委托)"


# ===== 测试 5：空候选 → 通用模式 =====

def test_empty_candidates_generic_mode() -> None:
    """无候选 → main_skill = (无登记)。"""
    entries = []
    task = _make_task(["write_copy"])
    proc = discipline.layer2_route_deterministic(task, entries)
    assert proc.main_skill == "(无登记)"
    assert len(proc.steps) == 1


# ===== 测试 6：空 intent_tags → 通用模式 =====

def test_empty_intent_tags_generic_mode() -> None:
    """任务书无 intent_tags → 通用模式。"""
    entries = [_entry("skill-a", ["write_copy"])]
    task = _make_task([])
    proc = discipline.layer2_route_deterministic(task, entries)
    assert proc.main_skill == "(无登记)"


# ===== 测试 7：自指排除（D6）=====

def test_self_id_never_routed() -> None:
    """政令台自身即使 intent_tags 匹配，也不参与路由。"""
    self_entry = _entry("zhenglingtai", ["decree_mode"], ["md"], is_meta=True)
    task = _make_task(["decree_mode"])
    proc = discipline.layer2_route_deterministic(task, [self_entry])
    assert proc.main_skill == "(无登记)"


# ===== 测试 8：确定性路由可复现（跑 10 次结果一致）=====

def test_deterministic_route_is_reproducible() -> None:
    """同一输入跑 10 次，路由结果 100% 一致。"""
    entries = [
        _entry("skill-a", ["write_copy"], ["md"]),
        _entry("skill-b", ["clean_excel"], ["xlsx"]),
    ]
    task = _make_task(["write_copy", "clean_excel"])
    results = [
        discipline.layer2_route_deterministic(task, entries)
        for _ in range(10)
    ]
    main_skills = [r.main_skill for r in results]
    assert len(set(main_skills)) == 1, f"路由不稳定：{main_skills}"
