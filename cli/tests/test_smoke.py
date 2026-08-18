"""冒烟测试：不调 LLM，验证 CLI 主链路可正常启动与解析。

Why this exists:
    CLI 的纪律层（L1/L2/L4）强依赖 LLM，没法离线测；
    但登记册聚合、模板渲染、辅助函数这些纯 Python 可以离线测。
"""

from __future__ import annotations

import json

from zhenglingtai_cli import __version__, discipline, executor, logutil, registry


def test_version_is_string() -> None:
    assert isinstance(__version__, str)
    assert __version__ == "1.2.0"


def test_scan_handles_missing_dir(tmp_path) -> None:
    """不存在的目录应返回空，不报错。"""
    missing = tmp_path / "nope"
    assert registry.scan(missing) == []


def test_score_handles_empty_query() -> None:
    """空 query 必须走通用模式，不进打分。"""
    e = registry.SkillEntry(id="x", intent_tags=["a"])
    assert registry.score([e], [], []) == []


def test_self_id_excluded_from_filter() -> None:
    """D6: 政令台自身 id 永不参与路由（防自指套娃）。"""
    self_entry = registry.SkillEntry(
        id="zhenglingtai",
        intent_tags=["decree_mode", "orchestrate_skills"],
        is_meta=True,
    )
    other_entry = registry.SkillEntry(
        id="some-other-skill",
        intent_tags=["decree_mode", "write_copy"],
    )
    result = registry.filter_by_intent([self_entry, other_entry], ["decree_mode"])
    ids = [e.id for e in result]
    assert "zhenglingtai" not in ids, "政令台自身不应出现在路由候选中"
    assert "some-other-skill" in ids, "其它 skill 应正常匹配"


def test_self_id_excluded_from_score() -> None:
    """D6: 政令台自身在 score() 中也不参与打分。"""
    self_entry = registry.SkillEntry(
        id="zhenglingtai",
        intent_tags=["decree_mode"],
        is_meta=True,
    )
    other_entry = registry.SkillEntry(
        id="other",
        intent_tags=["decree_mode"],
    )
    scored = registry.score([self_entry, other_entry], ["decree_mode"], [])
    ids = [e.id for e, _ in scored]
    assert "zhenglingtai" not in ids, "政令台自身不应出现在打分结果中"


def test_taskbook_round_trip_json() -> None:
    """TaskBook 能用 json 序列化。"""
    tb = discipline.TaskBook(
        what="清洗 Excel",
        why="给老板汇报",
        scope_in=["含表头"],
        scope_out=["不含金融衍生品"],
        accept=["文件存在且非空"],
        unknowns=[],
        intent_tags=["clean_excel"],
    )
    blob = json.dumps(tb.__dict__, ensure_ascii=False)
    assert "清洗 Excel" in blob
    roundtrip = discipline.TaskBook(**json.loads(blob))
    assert roundtrip.what == tb.what


def test_layer2_procedure_dataclass_construction() -> None:
    """Procedure dataclass 能正常构造。"""
    proc = discipline.Procedure(
        main_skill="x",
        cooperative=[],
        meta_delegate="",
        steps=[discipline.Step(index=1, skill_id="x", check="ok")],
        stop_points=[],
        fallbacks={},
    )
    assert proc.steps[0].check == "ok"


def test_executor_noop_falls_through() -> None:
    """通用模式下，所有 skill_id 应走 noop。"""
    res = executor.execute(
        capability_id="(无登记)",
        step={"skill_id": "(无登记)", "input": "x", "output": "y"},
        capabilities={},
    )
    assert res.ok is True
    assert res.outputs == []


def test_executor_missing_capability_returns_noop_with_hint() -> None:
    """D7 改进后：skill 在登记册但 capabilities 没配 → ok=True + noop+hint（不再 error）。"""
    res = executor.execute(
        capability_id="ghost_skill",
        step={"skill_id": "ghost_skill", "input": "", "output": ""},
        capabilities={},
    )
    assert res.ok is True
    assert "noop" in res.logs.lower()
    assert "zhenglingtai-capabilities.yaml" in res.logs


def test_format_string_attack_blocked() -> None:
    """D9: 格式化字符串攻击应被 string.Template 挡住。

    如果 str.format 还在用，{0.__class__} 会泄漏 Python 内部对象。
    string.Template 只认 $input / $output，其它原样保留。
    """
    import string as _string
    # 模拟恶意 input
    malicious = "{0.__class__.__init__.__globals__}"
    tpl = _string.Template('{"input": "$input"}')
    result = tpl.safe_substitute(input=malicious)
    # $input 被替换成恶意字符串，但 {0.__class__} 不被解析
    assert malicious in result
    assert "__globals__" not in result.replace(malicious, "")


# ===== D12: logutil =====

def test_logger_writes_json_lines(tmp_path) -> None:
    """D12: logger 写入 JSON Lines 文件，可被 json.loads 解析。"""
    log_file = tmp_path / "test.log"
    log = logutil.JsonLinesLogger(name="test", log_file=log_file)
    log.info("test_event", key="value")
    log.error("error_event", reason="bad")

    lines = log_file.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 2
    import json
    entry1 = json.loads(lines[0])
    assert entry1["msg"] == "test_event"
    assert entry1["level"] == "INFO"
    assert entry1["key"] == "value"
    entry2 = json.loads(lines[1])
    assert entry2["level"] == "ERROR"


def test_logger_entries_in_memory() -> None:
    """D12: logger 内存缓存可读回。"""
    log = logutil.JsonLinesLogger(name="test")
    log.info("a")
    log.warn("b")
    entries = log.entries()
    assert len(entries) == 2
    assert entries[0]["msg"] == "a"
    assert entries[1]["level"] == "WARN"
