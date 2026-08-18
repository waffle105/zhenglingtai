"""路由准确率回归基准（v1.0.3，对应评审 P2）。

跑 tests/benchmark_routing.json 里的典型场景，断言 layer2_route_deterministic
的路由结论与期望一致。改路由算法后必须重跑本文件；
期望变更必须同步改 JSON 并说明理由（基准即契约）。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from zhenglingtai_cli import discipline, registry

BENCHMARK = Path(__file__).with_name("benchmark_routing.json")


def _load_cases() -> list[dict]:
    data = json.loads(BENCHMARK.read_text(encoding="utf-8"))
    return data["cases"]


def _build_entries(case: dict) -> list[registry.SkillEntry]:
    return [
        registry.SkillEntry(
            id=e["id"],
            intent_tags=e["intent_tags"],
            output_types=e.get("output_types", ["md"]),
            is_meta=e.get("is_meta", False),
            priority=e.get("priority", 0),
        )
        for e in case["registry"]
    ]


def _build_task(case: dict) -> discipline.TaskBook:
    return discipline.TaskBook(
        what=case["name"], why="基准", scope_in=["a"], scope_out=["b"],
        accept=["c"], unknowns=[], intent_tags=case["task_tags"],
    )


@pytest.mark.parametrize("case", _load_cases(), ids=lambda c: c["name"])
def test_routing_case(case: dict) -> None:
    entries = _build_entries(case)
    task = _build_task(case)
    candidates = registry.filter_by_intent(entries, task.intent_tags)

    # 期望确定性场景：跑 5 次结果必须一致
    if case.get("expect_repeat_stable"):
        results = {discipline.layer2_route_deterministic(task, candidates).main_skill
                   for _ in range(5)}
        assert len(results) == 1, f"路由不稳定：{results}"
        return

    proc = discipline.layer2_route_deterministic(task, candidates)

    if "expect_main" in case:
        assert proc.main_skill == case["expect_main"], (
            f"main_skill 期望 {case['expect_main']}，实际 {proc.main_skill}")
    if "expect_meta" in case:
        assert proc.meta_delegate == case["expect_meta"], (
            f"meta_delegate 期望 {case['expect_meta']!r}，实际 {proc.meta_delegate!r}")
    if "expect_coop" in case:
        assert proc.cooperative == case["expect_coop"]
    if "expect_coop_len" in case:
        assert len(proc.cooperative) == case["expect_coop_len"], (
            f"协同数期望 {case['expect_coop_len']}，实际 {proc.cooperative}")


def test_benchmark_case_count() -> None:
    """基准集规模守卫：不得少于 15 例（删用例要有理由）。"""
    assert len(_load_cases()) >= 15
