"""--offline 纯确定性模式测试（v1.1.0）。

覆盖：
- layer1_translate_offline：规则构造任务书的口径（不扩写 / 诚实标注 / 空 tags）
- layer4_verify_deterministic：机器契约全场景
  （空产物 / 缺文件 / 0 字节 / md 字数阈值 / pptx 页数阈值 / xlsx sheet /
    py 语法 / accept 语义条目进 subjective）
- cmd_run --offline 端到端：无 LLM config 也能跑通（这是本模式的核心价值）
- cmd_verify --offline + --produced JSON 字符串解析
"""

from __future__ import annotations

import argparse
import json
import zipfile

import pytest

from zhenglingtai_cli import __main__ as main_mod
from zhenglingtai_cli import discipline, executor


def _proc() -> discipline.Procedure:
    return discipline.Procedure(
        main_skill="(无登记)", cooperative=[], meta_delegate="",
        steps=[discipline.Step(index=1, skill_id="(无登记)")],
        stop_points=[], fallbacks={},
    )


def _make_pptx(path, slides: int) -> None:
    """构造最小可解析 pptx（zip 容器 + N 个 slide xml）。"""
    with zipfile.ZipFile(path, "w") as z:
        for i in range(1, slides + 1):
            z.writestr(f"ppt/slides/slide{i}.xml", "<x/>")


def _make_xlsx(path, sheets: int) -> None:
    with zipfile.ZipFile(path, "w") as z:
        for i in range(1, sheets + 1):
            z.writestr(f"xl/worksheets/sheet{i}.xml", "<x/>")


# ===== L1 offline =====

def test_l1_offline_minimal_taskbook() -> None:
    """offline 任务书：what=原文不扩写，诚实标注，intent_tags 为空（→通用模式）。"""
    task = discipline.layer1_translate_offline("  帮我清洗 Excel  ")
    assert task.what == "帮我清洗 Excel"
    assert task.intent_tags == []
    assert "offline" in task.why
    assert task.unknowns  # 显式标注未经确认
    assert task.accept  # HARD：accept 不可空


# ===== L4 机器契约 =====

def test_l4_offline_empty_produced_fails() -> None:
    """无产物 → 未达标（不产出却宣称达标是幻觉温床）。"""
    task = discipline.layer1_translate_offline("做点什么")
    acc = discipline.layer4_verify_deterministic(task, _proc(), [], ".")
    assert acc.result == "未达标"
    assert acc.deviations
    assert acc.subjective  # accept 条目进了 subjective


def test_l4_offline_md_passes(tmp_path) -> None:
    """md 存在非空 → 达标；证据含字节数与字符数。"""
    (tmp_path / "out.md").write_text("# 正文\n内容", encoding="utf-8")
    task = discipline.layer1_translate_offline("写文档")
    acc = discipline.layer4_verify_deterministic(
        task, _proc(), [{"path": "out.md", "type": "md"}], tmp_path)
    assert acc.result == "达标"
    assert acc.per_item[0]["status"] == "ok"
    assert "字符" in acc.per_item[0]["evidence"]


def test_l4_offline_missing_file_fails(tmp_path) -> None:
    """文件不存在 → 未达标 + 偏差说明。"""
    task = discipline.layer1_translate_offline("写文档")
    acc = discipline.layer4_verify_deterministic(
        task, _proc(), [{"path": "ghost.md", "type": "md"}], tmp_path)
    assert acc.result == "未达标"
    assert any("不存在" in d for d in acc.deviations)


def test_l4_offline_zero_byte_fails(tmp_path) -> None:
    """0 字节 → 未达标。"""
    (tmp_path / "empty.md").write_text("")
    task = discipline.layer1_translate_offline("写文档")
    acc = discipline.layer4_verify_deterministic(
        task, _proc(), [{"path": "empty.md", "type": "md"}], tmp_path)
    assert acc.result == "未达标"
    assert any("为空" in d for d in acc.deviations)


def test_l4_offline_word_count_threshold(tmp_path) -> None:
    """accept 里"字数 ≥ N"被机器提取并对 md 生效。"""
    (tmp_path / "short.md").write_text("太短")
    task = discipline.layer1_translate_offline("写长文")
    task.accept.append("字数 ≥ 100")
    acc = discipline.layer4_verify_deterministic(
        task, _proc(), [{"path": "short.md", "type": "md"}], tmp_path)
    assert acc.result == "未达标"
    assert any("字数" in d for d in acc.deviations)


def test_l4_offline_pptx_slide_threshold(tmp_path) -> None:
    """pptx 页数用 zip 成员数；不足任务书阈值 → 未达标。"""
    _make_pptx(tmp_path / "deck.pptx", slides=5)
    task = discipline.layer1_translate_offline("做 PPT")
    task.accept.append("PPT 页数 ≥ 10")
    acc = discipline.layer4_verify_deterministic(
        task, _proc(), [{"path": "deck.pptx", "type": "pptx"}], tmp_path)
    assert acc.result == "未达标"
    assert any("页数 5" in d for d in acc.deviations)
    # 阈值放宽后达标
    task2 = discipline.layer1_translate_offline("做 PPT")
    task2.accept.append("PPT 页数 ≥ 5")
    acc2 = discipline.layer4_verify_deterministic(
        task2, _proc(), [{"path": "deck.pptx", "type": "pptx"}], tmp_path)
    assert acc2.result == "达标"


def test_l4_offline_xlsx_and_bad_zip(tmp_path) -> None:
    """xlsx 数 sheet；坏 zip → 未达标。"""
    _make_xlsx(tmp_path / "ok.xlsx", sheets=2)
    (tmp_path / "bad.xlsx").write_text("不是 zip")
    task = discipline.layer1_translate_offline("做表格")
    acc = discipline.layer4_verify_deterministic(
        task, _proc(),
        [{"path": "ok.xlsx", "type": "xlsx"}, {"path": "bad.xlsx", "type": "xlsx"}],
        tmp_path)
    assert acc.result == "未达标"
    assert any("无法解析" in d for d in acc.deviations)
    assert "2 个 sheet" in acc.per_item[0]["evidence"]


def test_l4_offline_py_syntax(tmp_path) -> None:
    """py 文件过 py_compile；语法错误 → 未达标。"""
    (tmp_path / "good.py").write_text("x = 1\n")
    (tmp_path / "bad.py").write_text("def broken(:\n")
    task = discipline.layer1_translate_offline("写脚本")
    acc = discipline.layer4_verify_deterministic(
        task, _proc(),
        [{"path": "good.py", "type": "py"}, {"path": "bad.py", "type": "py"}],
        tmp_path)
    assert acc.result == "未达标"
    assert any("语法检查失败" in d for d in acc.deviations)
    assert "语法检查通过" in acc.per_item[0]["evidence"]


def test_l4_offline_accept_goes_subjective(tmp_path) -> None:
    """语义条目（含某段/有出处）→ subjective，不影响机器判定也不被判达标。"""
    (tmp_path / "out.md").write_text("内容")
    task = discipline.layer1_translate_offline("写分析")
    task.accept.extend(["关键数据有出处", "含结论段"])
    acc = discipline.layer4_verify_deterministic(
        task, _proc(), [{"path": "out.md", "type": "md"}], tmp_path)
    assert acc.result == "达标"  # 机器项全过
    assert "关键数据有出处" in acc.subjective
    assert "含结论段" in acc.subjective


# ===== cmd_run --offline 端到端（无 LLM config）=====

def test_cmd_run_offline_no_config_needed(monkeypatch, tmp_path, capsys) -> None:
    """offline 端到端：不调 load_config（无 key 可跑），真产物 → 达标 return 0。"""
    # 故意让 load_config 炸——offline 路径根本不该调它
    monkeypatch.setattr(main_mod.llm, "load_config",
                        lambda path=None: (_ for _ in ()).throw(
                            AssertionError("offline 不该调 LLM config")))
    monkeypatch.setattr(main_mod.registry, "scan", lambda skills_dir=None: [])
    monkeypatch.setattr(executor, "load_capabilities", lambda p=None: {"x": {"kind": "noop"}})
    # 通用模式 noop 无产出 → 未达标 return 3；有产出 → 达标 return 0
    (tmp_path / "artifact.md").write_text("真产物")
    monkeypatch.setattr(executor, "execute", lambda **kw: executor.SubcapabilityResult(
        ok=True, outputs=[{"path": str(tmp_path / "artifact.md"), "type": "md"}], logs=""))
    monkeypatch.setattr(main_mod.Path, "home", classmethod(lambda cls: tmp_path))

    rc = main_mod.cmd_run(argparse.Namespace(
        prompt="做个东西", config=None, skills_dir=None, capabilities=None,
        work_dir=str(tmp_path), route_mode="auto", offline=True))
    out = capsys.readouterr().out
    assert rc == 0
    assert "offline" in out
    assert '"result": "达标"' in out


def test_cmd_run_offline_noop_produces_escalate(monkeypatch, tmp_path, capsys) -> None:
    """offline + noop 无产出 → 机器验收未达标 → 打满 3 轮 ESCALATE return 3。"""
    monkeypatch.setattr(main_mod.llm, "load_config",
                        lambda path=None: (_ for _ in ()).throw(AssertionError("不该调用")))
    monkeypatch.setattr(main_mod.registry, "scan", lambda skills_dir=None: [])
    monkeypatch.setattr(executor, "load_capabilities", lambda p=None: {})
    monkeypatch.setattr(executor, "execute", lambda **kw: executor.SubcapabilityResult(
        ok=True, outputs=[], logs="[noop]"))
    monkeypatch.setattr(main_mod.Path, "home", classmethod(lambda cls: tmp_path))

    rc = main_mod.cmd_run(argparse.Namespace(
        prompt="做个东西", config=None, skills_dir=None, capabilities=None,
        work_dir=str(tmp_path), route_mode="auto", offline=True))
    out = capsys.readouterr().out
    assert rc == 3
    assert "【ESCALATE】" in out
    assert "无产物可供机器验收" in out


# ===== cmd_verify --offline =====

def test_cmd_verify_offline_parses_produced_json(monkeypatch, tmp_path, capsys) -> None:
    """--produced 的 JSON 字符串被正确解析（v1.1.0 修复），机器验收达标。"""
    (tmp_path / "a.md").write_text("内容")
    (tmp_path / "task.json").write_text(json.dumps({
        "what": "w", "why": "y", "scope_in": [], "scope_out": [],
        "accept": ["产物存在"], "unknowns": [], "intent_tags": [],
    }, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "proc.json").write_text(json.dumps({
        "main_skill": "(无登记)", "steps": [],
    }, ensure_ascii=False), encoding="utf-8")
    # load_config 若被调就炸——offline 不需要
    monkeypatch.setattr(main_mod.llm, "load_config",
                        lambda path=None: (_ for _ in ()).throw(AssertionError("不该调用")))

    rc = main_mod.cmd_verify(argparse.Namespace(
        task=str(tmp_path / "task.json"), proc=str(tmp_path / "proc.json"),
        produced=[f'{{"path": "{str(tmp_path / "a.md").replace(chr(92), "/")}", "type": "md"}}'],
        config=None, offline=True))
    out = capsys.readouterr().out
    assert rc == 0
    assert '"result": "达标"' in out


def test_cmd_verify_offline_bare_path_fallback(monkeypatch, tmp_path, capsys) -> None:
    """--produced 传裸路径（非 JSON）→ 按路径包一层，后缀推类型。"""
    (tmp_path / "b.md").write_text("内容")
    (tmp_path / "task.json").write_text(json.dumps({
        "what": "w", "why": "y", "accept": ["产物存在"],
    }, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "proc.json").write_text('{"main_skill": "x", "steps": []}', encoding="utf-8")
    monkeypatch.setattr(main_mod.llm, "load_config",
                        lambda path=None: (_ for _ in ()).throw(AssertionError("不该调用")))
    rc = main_mod.cmd_verify(argparse.Namespace(
        task=str(tmp_path / "task.json"), proc=str(tmp_path / "proc.json"),
        produced=[str(tmp_path / "b.md")], config=None, offline=True))
    assert rc == 0
