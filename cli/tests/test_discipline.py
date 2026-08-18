"""discipline 层单元测试（D11）。

测试范围：
- TaskBook / Procedure / Acceptance dataclass 构造与 JSON 往返
- _parse_taskbook 校验（缺字段 raise）
- _parse_acceptance 的 HARD 约束（未达标但 deviations 空 → 自动补）
- layer2_route_deterministic 各种边界（已在 test_route.py 覆盖 8 个，这里补更多）
"""

from __future__ import annotations

import json

import pytest

from zhenglingtai_cli import discipline


# ===== TaskBook =====

def test_taskbook_required_fields() -> None:
    """TaskBook 必须有 what/why/scope_in/scope_out/accept/unknowns。"""
    tb = discipline.TaskBook(
        what="X", why="Y",
        scope_in=["a"], scope_out=["b"],
        accept=["c"], unknowns=[],
        intent_tags=["t"],
    )
    assert tb.what == "X"
    assert tb.intent_tags == ["t"]


def test_parse_taskbook_missing_what_raises() -> None:
    """缺 what → ValueError。"""
    with pytest.raises(ValueError, match="what"):
        discipline._parse_taskbook({"why": "y", "accept": ["a"], "intent_tags": ["t"]})


def test_parse_taskbook_missing_accept_raises() -> None:
    """缺 accept → ValueError。"""
    with pytest.raises(ValueError, match="accept"):
        discipline._parse_taskbook({"what": "w", "why": "y", "intent_tags": ["t"]})


def test_parse_taskbook_empty_intent_tags_raises() -> None:
    """intent_tags 为空 → ValueError。"""
    with pytest.raises(ValueError, match="intent_tags"):
        discipline._parse_taskbook({"what": "w", "why": "y", "accept": ["a"], "intent_tags": []})


# ===== Procedure =====

def test_parse_procedure_steps_default_index() -> None:
    """steps 缺 index → 自动编号。"""
    data = {"main_skill": "x", "steps": [{"skill_id": "a"}, {"skill_id": "b"}]}
    proc = discipline._parse_procedure(data)
    assert proc.steps[0].index == 1
    assert proc.steps[1].index == 2


def test_parse_procedure_empty_steps() -> None:
    """steps 为空 → 空列表。"""
    proc = discipline._parse_procedure({"main_skill": "x"})
    assert proc.steps == []


# ===== Acceptance =====

def test_parse_acceptance_no_deviation_auto_fill() -> None:
    """HARD: 未达标但 deviations 空 → 自动补说明。"""
    data = {"result": "未达标", "per_item": [], "deviations": []}
    acc = discipline._parse_acceptance(data)
    assert acc.result == "未达标"
    assert len(acc.deviations) == 1
    assert "不合规" in acc.deviations[0]


def test_parse_acceptance_ok_no_deviation() -> None:
    """达标时 deviations 为空 → 不补。"""
    data = {"result": "达标", "per_item": [], "deviations": []}
    acc = discipline._parse_acceptance(data)
    assert acc.result == "达标"
    assert acc.deviations == []


def test_parse_acceptance_default_result() -> None:
    """result 缺失 → 默认"未达标"。"""
    acc = discipline._parse_acceptance({})
    assert acc.result == "未达标"


# ===== Generic mode =====

def test_generic_mode_procedure() -> None:
    """通用模式工序单格式正确。"""
    task = discipline.TaskBook(
        what="test", why="t", scope_in=[], scope_out=[],
        accept=["a"], unknowns=[], intent_tags=[],
    )
    proc = discipline._generic_mode_procedure(task)
    assert proc.main_skill == "(无登记)"
    assert len(proc.steps) == 1
    assert proc.steps[0].skill_id == "(无登记)"


# ===== JSON 往返 =====

def test_taskbook_json_roundtrip() -> None:
    """TaskBook → JSON → TaskBook 不丢字段。"""
    tb = discipline.TaskBook(
        what="清洗", why="汇报",
        scope_in=["表头"], scope_out=["金融"],
        accept=["非空"], unknowns=[],
        intent_tags=["clean_excel"],
    )
    blob = json.dumps(tb.__dict__, ensure_ascii=False)
    restored = discipline.TaskBook(**json.loads(blob))
    assert restored == tb


def test_procedure_json_roundtrip() -> None:
    """Procedure → JSON → Procedure 不丢字段。"""
    proc = discipline.Procedure(
        main_skill="x", cooperative=["y"], meta_delegate="",
        steps=[discipline.Step(index=1, skill_id="x", check="ok")],
        stop_points=[1], fallbacks={"x": "fallback"},
    )
    # dataclass asdict → JSON → Procedure
    from dataclasses import asdict
    blob = json.dumps(asdict(proc), ensure_ascii=False)
    d = json.loads(blob)
    restored = discipline.Procedure(
        main_skill=d["main_skill"],
        cooperative=d["cooperative"],
        meta_delegate=d["meta_delegate"],
        steps=[discipline.Step(**s) for s in d["steps"]],
        stop_points=d["stop_points"],
        fallbacks=d["fallbacks"],
    )
    assert restored.main_skill == proc.main_skill
    assert restored.steps[0].skill_id == "x"
